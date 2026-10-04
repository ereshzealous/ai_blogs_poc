"""The `incident-remediation` workflow: what must happen, in which order, and where it is now.

    intake → investigate → propose_remediation → await_approval → remediate → verify → record → complete

Orchestration coordinates. Agents reason inside `investigate`, `propose_remediation` and `record`; the action layer
executes. After every step the engine commits a checkpoint, so any process can resume the workflow.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from agent_platform.actions.gateway import ActionGateway
from agent_platform.actions.types import ActionContext, ApprovalGrant, Decision, Invocation, canonical, digest
from agent_platform.agents.contracts import AgentTask, DiagnosisReport, RemediationProposal
from agent_platform.agents.incident_agents import DiagnosisAgent, RemediationAgent, SummaryAgent
from agent_platform.context.session import SessionStore
from agent_platform.faults import maybe_crash
from agent_platform.identity.principals import agent_id, require_role, resolve_user
from agent_platform.memory.store import MemoryStore
from agent_platform.orchestration.store import WorkflowStore, now
from agent_platform.telemetry.tracing import continue_trace, current_ids, set_attrs, span

NAME = "incident-remediation"
STEPS = ["intake", "investigate", "propose_remediation", "await_approval", "remediate", "verify", "record", "complete"]
CONTINUE, PAUSE, STOP = "continue", "pause", "stop"


class WorkflowBusy(RuntimeError):
    """Another live worker holds this workflow's lease."""


@dataclass
class WorkflowDeps:
    store: WorkflowStore
    actions: ActionGateway
    sessions: SessionStore
    memory: MemoryStore
    diagnosis: DiagnosisAgent
    remediation: RemediationAgent
    summary: SummaryAgent
    tokens_used: Callable[[str], int]
    settings: dict[str, Any]


class WorkflowEngine:
    def __init__(self, deps: WorkflowDeps):
        self.d = deps
        self.store = deps.store
        self._locks: dict[str, asyncio.Lock] = {}
        self.handlers: dict[str, Callable[[str, dict[str, Any]], Awaitable[str]]] = {
            "intake": self._intake, "investigate": self._investigate, "propose_remediation": self._propose,
            "await_approval": self._await_approval, "remediate": self._remediate, "verify": self._verify,
            "record": self._record, "complete": self._complete,
        }

    # ================================================================ public API
    async def start(self, *, incident_id: str, request: str, user_id: str, channel: str,
                    session_id: str | None = None, run_until: str | None = None) -> dict[str, Any]:
        wf_id, state = self.prepare(incident_id=incident_id, request=request, user_id=user_id, channel=channel,
                                    session_id=session_id)
        return await self.run_new(wf_id, state, run_until)

    async def run_new(self, wf_id: str, state: dict[str, Any], run_until: str | None = None) -> dict[str, Any]:
        return await self._drive(wf_id, state, "intake", run_until)

    def prepare(self, *, incident_id: str, request: str, user_id: str, channel: str,
                session_id: str | None = None) -> tuple[str, dict[str, Any]]:
        """Create the workflow record and its first state; running it is a separate call."""
        resolve_user(user_id)
        wf_id = f"wf-{uuid.uuid4().hex[:10]}"
        sid = self.d.sessions.open(channel, user_id, session_id)
        self.d.sessions.append(sid, "user", request)
        self.store.create({"id": wf_id, "name": NAME, "incident_id": incident_id, "status": "RUNNING",
                           "current_step": "intake", "channel": channel, "requested_by": user_id, "session_id": sid})
        state = {"workflow_id": wf_id, "incident_id": incident_id, "request": request, "user_id": user_id,
                 "channel": channel, "session_id": sid}
        self.store.event(wf_id, "workflow.started", channel=channel, user=user_id, incident=incident_id)
        self.store.save_checkpoint(wf_id, "created", "intake", state, "RUNNING", traced=False)
        return wf_id, state

    async def resume(self, workflow_id: str, run_until: str | None = None) -> dict[str, Any]:
        wf = self.store.get(workflow_id)
        if wf is None:
            raise KeyError(workflow_id)
        if wf["status"] in ("COMPLETED", "REJECTED"):
            return self.view(workflow_id)
        cp = self.store.latest_checkpoint(workflow_id)
        if cp is None:
            raise RuntimeError(f"{workflow_id} has no checkpoint")
        if cp["next_step"] is None:
            return self.view(workflow_id)
        state = cp["state"]
        state.pop("final_status", None)
        self.store.event(workflow_id, "workflow.resumed", from_checkpoint=cp["seq"], next_step=cp["next_step"],
                         previous_pid=cp["pid"])
        return await self._drive(workflow_id, state, cp["next_step"], run_until)

    async def decide(self, workflow_id: str, approver_id: str, approve: bool, comment: str = "") -> dict[str, Any]:
        approval = self.store.open_approval(workflow_id)
        if approval is None or approval["status"] != "PENDING":
            raise ValueError(f"{workflow_id} has no pending approval")
        approver = resolve_user(approver_id)
        require_role(approver, approval["required_role"])
        wf = self.store.get(workflow_id) or {}
        with continue_trace(wf.get("trace_id"), wf.get("root_span_id")), \
                span("approval.decide", **{"lap.workflow.id": workflow_id, "enduser.id": approver_id,
                                           "lap.approval.decision": "APPROVED" if approve else "REJECTED",
                                           "lap.approval.digest": approval["digest"]}):
            self.store.decide(approval["id"], approver_id, approve, comment)
            self.store.event(workflow_id, "approval.decided", approver=approver_id, approved=approve,
                             digest=approval["digest"], tool_id=approval["tool_id"])
        return await self.resume(workflow_id)

    async def recover(self) -> list[dict[str, Any]]:
        """Resume every workflow a dead worker left in RUNNING."""
        out = []
        for wf in self.store.list("RUNNING"):
            try:
                out.append(await self.resume(wf["id"]))
            except WorkflowBusy:
                continue
        return out

    # ================================================================ the driver
    async def _drive(self, wf_id: str, state: dict[str, Any], from_step: str, run_until: str | None) -> dict[str, Any]:
        lock = self._locks.setdefault(wf_id, asyncio.Lock())
        async with lock:
            if not self.store.acquire(wf_id, os.getpid()):
                raise WorkflowBusy(wf_id)
            try:
                wf = self.store.get(wf_id) or {}
                segment = self.store.next_segment(wf_id)
                with continue_trace(wf.get("trace_id"), wf.get("root_span_id")), \
                        span(f"invoke_workflow {NAME}", **{"gen_ai.operation.name": "invoke_workflow",
                                                          "gen_ai.workflow.name": NAME, "lap.workflow.id": wf_id,
                                                          "lap.segment": segment, "lap.resumed_at_step": from_step,
                                                          "enduser.id": state["user_id"], "lap.pid": os.getpid()}) as root:
                    if segment == 1:
                        trace_id, span_id = current_ids()
                        self.store.set_trace(wf_id, trace_id, span_id)
                    await self._run_steps(wf_id, state, from_step, run_until)
                    set_attrs(root, **{"lap.status": (self.store.get(wf_id) or {}).get("status")})
            finally:
                self.store.release(wf_id, os.getpid())
        return self.view(wf_id)

    async def _run_steps(self, wf_id: str, state: dict[str, Any], from_step: str, run_until: str | None) -> None:
        for step in STEPS[STEPS.index(from_step):]:
            with span(f"workflow.step {step}", **{"lap.workflow.id": wf_id, "lap.step": step}) as s:
                self.store.set_status(wf_id, "RUNNING", step)
                try:
                    outcome = await self.handlers[step](wf_id, state)
                except Exception as exc:
                    self.store.event(wf_id, "step.failed", step=step, error=f"{type(exc).__name__}: {exc}")
                    self.store.save_checkpoint(wf_id, step, step, state, "FAILED")
                    raise
                set_attrs(s, **{"lap.step.outcome": outcome})
            idx = STEPS.index(step)
            if outcome == PAUSE:
                self.store.save_checkpoint(wf_id, step, step, state, "WAITING_APPROVAL")
                maybe_crash(f"after_step:{step}")
                return
            if outcome == STOP:
                final = state.get("final_status", "FAILED")
                # A failed step stays resumable (e.g. after an outage); a rejection is final.
                self.store.save_checkpoint(wf_id, step, step if final == "FAILED" else None, state, final)
                return
            nxt = STEPS[idx + 1] if idx + 1 < len(STEPS) else None
            self.store.save_checkpoint(wf_id, step, nxt, state, "COMPLETED" if nxt is None else "RUNNING")
            self.store.event(wf_id, "step.completed", step=step)
            maybe_crash(f"after_step:{step}")
            if run_until == step:
                return

    # ================================================================ helpers
    def _task(self, wf_id: str, state: dict[str, Any], step: str, feedback: list[str] | None = None) -> AgentTask:
        inc = state.get("incident", {})
        view = {"workflow_id": wf_id, "workflow": NAME, "step": step, "incident_id": state["incident_id"],
                "severity": inc.get("severity"), "service": inc.get("service"), "environment": inc.get("environment"),
                "opened_at": inc.get("opened_at"), "completed_steps": STEPS[:STEPS.index(step)]}
        return AgentTask(wf_id, step, state["incident_id"], inc.get("service", ""), inc.get("environment", ""),
                         state["request"], state["user_id"], state.get("session_id"), view, feedback or [])

    def _ctx(self, wf_id: str, state: dict[str, Any], step: str) -> ActionContext:
        return ActionContext(state["user_id"], agent_id(), wf_id, step, state.get("incident", {}).get("environment"))

    # ================================================================ steps
    async def _intake(self, wf_id: str, state: dict[str, Any]) -> str:
        res = await self.d.actions.execute(Invocation("itsm.get_incident", {"incident_id": state["incident_id"]}),
                                           self._ctx(wf_id, state, "intake"))
        if not res.ok:
            raise RuntimeError(f"cannot load incident: {res.error}")
        inc = res.result
        state["incident"] = {k: inc[k] for k in ("id", "title", "severity", "service", "environment", "opened_at", "status")}
        return CONTINUE

    async def _investigate(self, wf_id: str, state: dict[str, Any]) -> str:
        tools = [r.tool_id for r in self.d.actions.registry.discover(tags={"diagnosis"})]
        toolbox = self.d.actions.toolbox(self._ctx(wf_id, state, "investigate"), tools)
        outcome = await self.d.diagnosis.run(self._task(wf_id, state, "investigate"), toolbox)
        report: DiagnosisReport = outcome.output
        state["diagnosis"] = report.model_dump()
        state["investigation"] = {"steps": outcome.steps, "tool_calls": toolbox.calls, "context": outcome.context_manifest}
        self.store.event(wf_id, "diagnosis.completed", suspect=report.suspect_deployment_id, version=report.suspect_version,
                         tool_calls=len(toolbox.calls), confidence=report.confidence)
        return CONTINUE

    async def _propose(self, wf_id: str, state: dict[str, Any]) -> str:
        diagnosis = DiagnosisReport.model_validate(state["diagnosis"])
        ctx = self._ctx(wf_id, state, "propose_remediation")
        feedback: list[str] = []
        proposals = []
        for _ in range(int(self.d.settings.get("max_remediation_proposals", 2))):
            outcome = await self.d.remediation.run(self._task(wf_id, state, "propose_remediation", feedback), diagnosis)
            p: RemediationProposal = outcome.output
            inv = Invocation(p.tool_id, p.arguments())
            decision = self.d.actions.evaluate(inv, ctx)
            proposals.append({"proposal": p.model_dump(), "decision": decision.to_dict(), "context": outcome.context_manifest})
            self.store.event(wf_id, "remediation.proposed", tool_id=p.tool_id, arguments=inv.arguments,
                             decision=decision.decision.value, rule=decision.rule_id)
            if decision.decision is Decision.DENY:
                feedback.append(f"{p.tool_id} {inv.arguments} was DENIED by {decision.rule_id}: {decision.reason}")
                continue
            state["proposal"] = p.model_dump()
            state["invocation"] = {"tool_id": inv.tool_id, "arguments": inv.arguments}
            state["policy"] = decision.to_dict()
            state["proposals"] = proposals
            return CONTINUE
        state["proposals"] = proposals
        state["final_status"] = "FAILED"
        self.store.event(wf_id, "remediation.no_allowed_proposal", attempts=len(proposals))
        return STOP

    async def _await_approval(self, wf_id: str, state: dict[str, Any]) -> str:
        policy = state["policy"]
        if policy["decision"] == Decision.ALLOW.value:
            return CONTINUE
        inv = state["invocation"]
        approval = self.store.approval_for(wf_id, policy["digest"])
        if approval is None:
            with span("approval.request", **{"lap.workflow.id": wf_id, "lap.approval.digest": policy["digest"],
                                             "lap.approval.role": policy["approver_role"], "gen_ai.tool.name": inv["tool_id"]}):
                approval = self.store.request_approval(wf_id, policy["digest"], inv["tool_id"], inv["arguments"],
                                                       policy["approver_role"], policy["reason"])
                self.store.event(wf_id, "approval.requested", approval_id=approval["id"], digest=policy["digest"],
                                 tool_id=inv["tool_id"], arguments=inv["arguments"], role=policy["approver_role"])
                if state.get("session_id"):
                    self.d.sessions.append(state["session_id"], "assistant",
                                           f"Approval needed: {inv['tool_id']} {inv['arguments']} ({approval['id']}).")
        if approval["status"] == "PENDING":
            return PAUSE
        if approval["status"] == "REJECTED":
            state["final_status"] = "REJECTED"
            self.store.event(wf_id, "workflow.rejected", approver=approval["decided_by"])
            return STOP
        state["grant"] = {"digest": approval["digest"], "approver": approval["decided_by"],
                          "role": approval["required_role"], "approved_at": approval["decided_at"]}
        return CONTINUE

    async def _remediate(self, wf_id: str, state: dict[str, Any]) -> str:
        inv = Invocation(state["invocation"]["tool_id"], state["invocation"]["arguments"])
        grant = ApprovalGrant(**state["grant"]) if state.get("grant") else None
        op_id = digest(wf_id, "remediate", inv.tool_id, canonical(inv.arguments))
        self.store.event(wf_id, "remediation.executing", tool_id=inv.tool_id, operation_id=op_id)
        res = await self.d.actions.execute(inv, self._ctx(wf_id, state, "remediate"), operation_id=op_id, grant=grant)
        state["remediation"] = res.to_dict()
        self.store.event(wf_id, "remediation.result", tool_id=inv.tool_id, status=res.status, attempts=res.attempts,
                         replayed=res.replayed, operation_id=op_id, error=res.error)
        if not res.ok:
            state["final_status"] = "FAILED"
            return STOP
        return CONTINUE

    async def _verify(self, wf_id: str, state: dict[str, Any]) -> str:
        inc = state["incident"]
        attempts = int(self.d.settings.get("verify_attempts", 3))
        for i in range(1, attempts + 1):
            res = await self.d.actions.execute(
                Invocation("observability.query_latency", {"service": inc["service"], "environment": inc["environment"]}),
                self._ctx(wf_id, state, "verify"))
            if res.ok and not res.result.get("breaching_slo"):
                state["verification"] = {"ok": True, "p95_ms": res.result["p95_ms"], "slo_p95_ms": res.result["slo_p95_ms"],
                                         "running_version": res.result["running_version"], "checks": i, "at": now()}
                self.store.event(wf_id, "verification.passed", p95_ms=res.result["p95_ms"], checks=i)
                return CONTINUE
            await asyncio.sleep(float(self.d.settings.get("verify_interval_s", 0.5)))
        state["verification"] = {"ok": False, "checks": attempts}
        state["final_status"] = "FAILED"
        self.store.event(wf_id, "verification.failed", checks=attempts)
        return STOP

    async def _record(self, wf_id: str, state: dict[str, Any]) -> str:
        if not state.get("verification", {}).get("ok"):
            raise RuntimeError("refusing to update the incident before verification")
        facts = {"incident": state["incident"], "diagnosis": {k: state["diagnosis"][k] for k in ("root_cause", "suspect_version",
                                                                                             "suspect_deployment_id")},
                 "action": state["invocation"], "approved_by": (state.get("grant") or {}).get("approver"),
                 "result": (state["remediation"].get("result") or {}), "verification": state["verification"]}
        outcome = await self.d.summary.run(self._task(wf_id, state, "record"), facts)
        note = outcome.output
        inv = Invocation("itsm.update_incident", {"incident_id": state["incident_id"], "status": note.status, "note": note.note})
        op_id = digest(wf_id, "record", inv.tool_id, canonical(inv.arguments))
        res = await self.d.actions.execute(inv, self._ctx(wf_id, state, "record"), operation_id=op_id)
        state["note"] = {**note.model_dump(), "status_result": res.status}
        self.store.event(wf_id, "incident.updated", status=note.status, result=res.status)
        if not res.ok:
            state["final_status"] = "FAILED"
            return STOP
        return CONTINUE

    async def _complete(self, wf_id: str, state: dict[str, Any]) -> str:
        d, inc = state["diagnosis"], state["incident"]
        content = (f"{state['incident_id']} ({inc['opened_at'][:10]}): {d['root_cause']} Fixed by "
                   f"{state['invocation']['tool_id']} to {state['invocation']['arguments'].get('target_version')}; "
                   f"p95 back to {state['verification']['p95_ms']} ms.")
        mem_id = self.d.memory.remember(inc["service"], content[:500], source=f"workflow:{wf_id}", confidence=0.7)
        state["memory_written"] = mem_id
        if state.get("session_id"):
            self.d.sessions.append(state["session_id"], "assistant", f"Resolved: {state['note']['note']}")
        state["tokens_used"] = self.d.tokens_used(wf_id)
        self.store.event(wf_id, "workflow.completed", memory_id=mem_id, tokens=state["tokens_used"])
        return CONTINUE

    # ================================================================ read model
    def view(self, wf_id: str) -> dict[str, Any]:
        wf = self.store.get(wf_id)
        if wf is None:
            raise KeyError(wf_id)
        cp = self.store.latest_checkpoint(wf_id)
        st = cp["state"] if cp else {}
        approval = self.store.open_approval(wf_id)
        return {
            "workflow_id": wf_id, "name": wf["name"], "incident_id": wf["incident_id"], "status": wf["status"],
            "current_step": wf["current_step"], "channel": wf["channel"], "requested_by": wf["requested_by"],
            "session_id": wf["session_id"], "trace_id": wf["trace_id"], "segments": wf["segments"],
            "created_at": wf["created_at"], "updated_at": wf["updated_at"],
            "incident": st.get("incident"), "diagnosis": st.get("diagnosis"), "proposal": st.get("proposal"),
            "policy": st.get("policy"), "approval": approval and {k: approval[k] for k in (
                "id", "status", "tool_id", "arguments", "required_role", "reason", "decided_by", "decided_at", "digest")},
            "remediation": st.get("remediation"), "verification": st.get("verification"), "note": st.get("note"),
            "tokens_used": self.d.tokens_used(wf_id), "checkpoints": len(self.store.checkpoints(wf_id)),
        }
