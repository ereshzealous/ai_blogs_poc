"""The INC remediation workflow: what happens, in which order, and where a human decides.

    intake -> investigate -> propose -> authorize -> [WAITING_APPROVAL] -> execute -> verify -> record -> complete

Orchestration coordinates.  It selects agents and capabilities, sequences the steps, turns a policy decision into a
transition (continue / wait for a human / escalate), and assembles the report.  It never calls a model provider or MCP
directly: models are reached through the runtime's agent loop, systems through the action gateway.
"""

from __future__ import annotations

from typing import Any

from layered_platform.context.assembler import ContextAssembler
from layered_platform.contracts import ActionContext, DiagnosisReport, ModelPort, RemediationProposal
from layered_platform.orchestration.agents import DIAGNOSTICIAN, DIAGNOSTICIAN_TOOLS, REMEDIATOR
from layered_platform.policy.approvals import Approvals
from layered_platform.runtime.agent_loop import AgentFailed, run_agent
from layered_platform.runtime.executor import StepResult
from layered_platform.tools.gateway import ActionDenied, ActionFailed, ActionGateway, ApprovalRequired
from layered_platform.tools.toolbox import ReadOnlyToolbox

FIRST_STEP = "intake"
ACTION_TO_CAPABILITY = {"rollback_release": "deploy.rollback", "restart_service": "deploy.restart", "scale_service": "deploy.scale"}


class IncidentWorkflow:
    def __init__(self, gateway: ActionGateway, model: ModelPort, context: ContextAssembler, approvals: Approvals):
        self.gateway, self.model, self.context, self.approvals = gateway, model, context, approvals

    def steps(self) -> dict[str, Any]:
        return {"intake": self.intake, "investigate": self.investigate, "propose": self.propose, "authorize": self.authorize,
                "execute": self.execute, "verify": self.verify, "record": self.record, "complete": self.complete}

    def _ctx(self, wf: str, step: str, state: dict[str, Any], approval_id: str | None = None) -> ActionContext:
        return ActionContext(workflow_id=wf, step=step, principal=state["requested_by"],
                             incident_environment=state.get("incident", {}).get("environment", "production"), approval_id=approval_id)

    # ---- steps ---------------------------------------------------------------------------------------------------
    async def intake(self, wf: str, s: dict[str, Any]) -> StepResult:
        inc = await self.gateway.execute("incident.get", {"incident_id": s["incident_id"]}, self._ctx(wf, "intake", s))
        facts = {k: inc[k] for k in ("id", "title", "service", "environment", "severity", "status", "opened", "customer_impact") if k in inc}
        return StepResult("investigate", updates={"incident": facts})

    async def investigate(self, wf: str, s: dict[str, Any]) -> StepResult:
        inc = s["incident"]
        messages, manifest = self.context.build(DIAGNOSTICIAN.instructions, s["instructions"] + " Diagnose it first.", {"incident": inc},
                                                query=f"{inc['service']} latency triage {inc['title']}", subject=inc["service"])
        tools = ReadOnlyToolbox(self.gateway, DIAGNOSTICIAN_TOOLS, self._ctx(wf, "investigate", s))
        try:
            report, stats = await run_agent(DIAGNOSTICIAN, messages, self.model, tools, DiagnosisReport, wf)
        except AgentFailed as exc:
            return StepResult("investigate", status="FAILED", updates={"error": str(exc)})
        return StepResult("propose", updates={"diagnosis": report.model_dump(), "context_manifest": {"investigate": manifest},
                                              "agent_stats": {**s.get("agent_stats", {}), "diagnostician": stats}})

    async def propose(self, wf: str, s: dict[str, Any]) -> StepResult:
        inc, dx = s["incident"], s["diagnosis"]
        messages, manifest = self.context.build(REMEDIATOR.instructions, "Propose the remediation.", {"incident": inc, "diagnosis": dx},
                                                query=f"{inc['service']} remediation rollback restart scale", subject=inc["service"])
        try:
            proposal, stats = await run_agent(REMEDIATOR, messages, self.model, None, RemediationProposal, wf)
        except AgentFailed as exc:
            return StepResult("propose", status="FAILED", updates={"error": str(exc)})
        return StepResult("authorize", updates={"proposal": proposal.model_dump(),
                                                "context_manifest": {**s.get("context_manifest", {}), "propose": manifest},
                                                "agent_stats": {**s.get("agent_stats", {}), "remediator": stats}})

    def _action(self, s: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        p = s["proposal"]
        cap = ACTION_TO_CAPABILITY.get(p["action"], p["action"])
        args: dict[str, Any] = {"service": p["service"], "environment": p["environment"]}
        if p["action"] == "rollback_release":
            args["to_release"] = p["target_release"]
        return cap, args

    async def authorize(self, wf: str, s: dict[str, Any]) -> StepResult:
        if s["proposal"]["action"] == "none":
            return StepResult("record", updates={"policy": {"effect": "NONE", "rule": "-", "reason": "no action proposed"}})
        cap, args = self._action(s)
        decision = self.gateway.authorize(cap, args, self._ctx(wf, "authorize", s))
        policy = decision.model_dump()
        if decision.effect == "DENY":
            return StepResult("record", updates={"policy": policy, "outcome": "escalated"})
        if decision.effect == "REQUIRE_APPROVAL":
            req = self.approvals.request(wf, cap, args, s["requested_by"], decision.required_role or "")
            return StepResult("execute", status="WAITING_APPROVAL", updates={"policy": policy, "approval": {"id": req["id"], "status": "PENDING",
                                                                                                              "required_role": req["required_role"]}})
        return StepResult("execute", updates={"policy": policy})

    async def execute(self, wf: str, s: dict[str, Any]) -> StepResult:
        cap, args = self._action(s)
        approval_id = (s.get("approval") or {}).get("id")
        try:
            result = await self.gateway.execute(cap, args, self._ctx(wf, "execute", s, approval_id))
        except ApprovalRequired as exc:
            return StepResult("execute", status="WAITING_APPROVAL", updates={"last_error": str(exc)})
        except (ActionDenied, ActionFailed) as exc:
            return StepResult("record", updates={"action": {"capability": cap, "args": args, "error": str(exc)}, "outcome": "action_failed"})
        return StepResult("verify", updates={"action": {"capability": cap, "args": args, "result": result}})

    async def verify(self, wf: str, s: dict[str, Any]) -> StepResult:
        inc = s["incident"]
        m = await self.gateway.execute("telemetry.metrics", {"service": inc["service"], "environment": inc["environment"],
                                                             "metric": "latency_p95_ms", "minutes": 3}, self._ctx(wf, "verify", s))
        ok = m.get("slo_p95_ms") is not None and m["max"] < m["slo_p95_ms"]
        return StepResult("record", updates={"verification": {"metric": "latency_p95_ms", "window_min": 3, "max": m["max"], "slo": m.get("slo_p95_ms"), "ok": ok},
                                             "outcome": "mitigated" if ok else "not_recovered"})

    async def record(self, wf: str, s: dict[str, Any]) -> StepResult:
        inc, dx = s["incident"], s.get("diagnosis") or {}
        act, ver = s.get("action") or {}, s.get("verification") or {}
        status = "mitigated" if s.get("outcome") == "mitigated" else "investigating"
        note = (f"[{wf}] Root cause: {dx.get('root_cause', 'unknown')} (suspect release {dx.get('suspect_release')}). "
                f"Action: {act.get('capability', 'none')} {act.get('args', {})} -> {('ok' if act.get('result') else act.get('error', 'not executed'))}. "
                f"Verification: {('p95 max ' + str(ver.get('max')) + ' ms vs SLO ' + str(ver.get('slo')) + ' ms') if ver else 'not run'}. "
                f"Policy: {(s.get('policy') or {}).get('rule')}; approval: {(s.get('approval') or {}).get('id', '-')}.")
        await self.gateway.execute("incident.update", {"incident_id": inc["id"], "status": status, "note": note}, self._ctx(wf, "record", s))
        return StepResult("complete", updates={"recorded_status": status})

    async def complete(self, wf: str, s: dict[str, Any]) -> StepResult:
        dx, act, ver = s.get("diagnosis") or {}, s.get("action") or {}, s.get("verification") or {}
        report = "\n".join([
            f"Root cause: {dx.get('root_cause', 'unknown')} (release {dx.get('suspect_release')})",
            f"Action: {act.get('capability', 'none')} {act.get('args', {})} {'executed' if act.get('result') else '- ' + str(act.get('error', 'not executed'))}",
            f"Verification: {('p95 max ' + str(ver.get('max')) + ' ms over the last 3 min, SLO ' + str(ver.get('slo')) + ' ms, ' + ('recovered' if ver.get('ok') else 'NOT recovered')) if ver else 'not run'}",
            f"Incident: {s.get('recorded_status')} · policy {(s.get('policy') or {}).get('rule')} · approval {(s.get('approval') or {}).get('id', '-')}",
        ])
        final = "COMPLETED" if s.get("outcome") == "mitigated" else ("ESCALATED" if s.get("outcome") == "escalated" else "COMPLETED")
        return StepResult("done", status=final, updates={"report": report})

    # ---- human in the loop -----------------------------------------------------------------------------------------
    def decide(self, wf: str, s: dict[str, Any], decided_by: str, approve: bool, reason: str) -> dict[str, Any]:
        apr = s.get("approval") or {}
        rec = self.approvals.decide(apr["id"], decided_by, approve, reason)
        return {"id": rec["id"], "status": rec["status"], "decided_by": rec["decided_by"], "required_role": rec["required_role"]}
