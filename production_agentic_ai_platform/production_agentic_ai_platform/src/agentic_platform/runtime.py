"""The runtime: request boundary + durable orchestration, wired to every other plane.

    request boundary   authenticate the user, resolve tenant and incident, open a session, attest the workload, create the
                       delegation, compute effective authority, start the trace
    orchestration      intake -> context -> investigate -> propose -> authorize -> await_approval -> execute -> verify
                       -> record -> complete, one checkpoint after every step, parked while a human decides, resumable in
                       another process after a SIGKILL
    agent runtime      agent.py (reasoning only), given a model port and the capabilities discovery offered
    enforcement        policy, approval, budget, capability issuance (tools.py, approval.py, budget.py, capability.py)
    control plane      the signed bundle, re-read before every decision (control_plane.py)
    evidence           trace.jsonl (OpenTelemetry) + audit.jsonl (hash-chained) + category files (observability.py)

This module is the only place the planes are wired together.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import yaml
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from agentic_platform import control_plane as cpm
from agentic_platform.agent import IncidentAgent
from agentic_platform.approval import ApprovalService
from agentic_platform.budget import Budget, BudgetExceeded
from agentic_platform.canonical import invocation_digest, stable_id
from agentic_platform.context import ContextGateway
from agentic_platform.evaluation import evaluate_workflow
from agentic_platform.guardrails import ContextGuard, OutputGuard
from agentic_platform.identity import Delegation, IdentityService
from agentic_platform.memory import MemoryService
from agentic_platform.models import ModelGateway, NoEligibleModel
from agentic_platform.observability import Evidence, JsonlSpanExporter, context_from_traceparent, span, traceparent
from agentic_platform.store import Store
from agentic_platform.tools import ActionDenied, McpPool, ToolPlatform, crash_point, unfinished_attempt

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "scenarios" / "inc_4917" / "seed.yaml"
AGENT_SRC = Path(__file__).with_name("agent.py")
STEPS = ["intake", "context", "investigate", "propose", "authorize", "await_approval", "execute", "verify", "record", "complete"]
TERMINAL = {"COMPLETED", "DENIED", "REJECTED", "BUDGET_EXCEEDED", "FAILED_CLOSED"}


def agent_code_sha256() -> str:
    return hashlib.sha256(AGENT_SRC.read_bytes()).hexdigest()


class Runtime:
    def __init__(self, exp_dir: Path, *, config_dir: Path, keys: dict[str, str], agent_id: str = "agent:incident-remediator",
                 mcp_env: dict[str, str] | None = None, guard_enabled: bool | None = None):
        self.dir, self.config_dir, self.agent_id = Path(exp_dir), Path(config_dir), agent_id
        self.keys = {k: v.encode() for k, v in keys.items()}
        self.cap_key = self.keys["capability"]
        self.mcp_env, self.guard_override = mcp_env or {}, guard_enabled
        self.world_seed = yaml.safe_load(SEED.read_text())
        self.wf_id: str | None = None

    # ---- lifecycle -------------------------------------------------------------------------------------------------------
    async def __aenter__(self) -> Runtime:
        b = self.bundle()
        self.store = Store(self.dir / "platform.db")
        self.provider = TracerProvider(resource=Resource.create({"service.name": "agent-runtime", "service.version": "1.0.0",
                                                                 "deployment.environment": "production-simulated", "process.pid": os.getpid()}))
        self.provider.add_span_processor(SimpleSpanProcessor(JsonlSpanExporter(self.dir / "trace.jsonl")))
        self.t = self.provider.get_tracer("agentic_platform")
        self.ev = Evidence(self.dir, self.dir.name)
        self.mcp = McpPool(ROOT, self.dir / "world.db", self.cap_key, self.mcp_env)
        await self.mcp.start()
        self.ids = IdentityService(b, self.keys["attestor"])
        self.approvals = ApprovalService(self.store, self.keys["approval"], b.policy, b.doc["identity"]["users"])
        self.tools = ToolPlatform(self)
        return self

    async def __aexit__(self, *exc) -> None:
        await self.mcp.close()
        self.provider.shutdown()

    def bundle(self) -> cpm.Bundle:
        """Re-read and verify the control plane's bundle before every decision."""
        return cpm.load(self.config_dir, self.keys["control_plane"])

    # ---- request boundary --------------------------------------------------------------------------------------------------
    async def submit(self, *, user_id: str, channel: str, text: str, incident_id: str) -> str:
        n = self.store.q("SELECT COUNT(*) FROM workflows")[0][0]
        self.wf_id = stable_id("wf", self.dir.name, user_id, incident_id, n, n=10)
        with self.t.start_as_current_span("request INC", attributes={"platform.channel": channel, "enduser.id": user_id}) as root:
            root.update_name(f"request {incident_id}")
            tp = traceparent(root)
            incident = await self.mcp.call("incident", "get_incident", {"incident_id": incident_id}, {"traceparent": tp})
            user = self.ids.user(user_id)
            sid = stable_id("sess", self.wf_id, channel, n=8)
            self.store.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?)", (sid, user_id, channel, user.tenant, time.time(), json.dumps([{"role": "user", "text": text}])))
            self.store.db.execute("INSERT INTO workflows VALUES (?,?,?,?,?,?,?,?,?,?)",
                                  (self.wf_id, sid, self.agent_id, user_id, user.tenant, incident_id, "RUNNING", tp, time.time(), time.time()))
            d = self.ids.delegate(user, self.agent_id, incident, stable_id("dlg", self.wf_id, user_id, n=8))
            state = {"workflow_id": self.wf_id, "status": "RUNNING", "done": [], "session_id": sid, "user_id": user_id, "channel": channel,
                     "request": text, "incident": incident, "traceparent": tp,
                     "delegation": {"id": d.id, "scope": sorted(d.scope), "requested": sorted(d.requested), "issued_at": d.issued_at, "expires_at": d.expires_at},
                     "context": [], "observations": [], "offered": []}
            self._bind(state)
            b = self.bundle()
            agent = b.agent(self.agent_id)
            self.ev.record("request.received", {"channel": channel, "user": user_id, "text": text, "incident": incident_id, "session_id": sid},
                           workflow_id=self.wf_id)
            self.ev.record("identity.resolved", {
                "user": {"id": user.id, "tenant": user.tenant, "groups": user.groups, "clearance": user.clearance, "roles": user.roles},
                "agent": {"id": agent["id"], "version": agent["version"], "prompt_config": agent["prompt_config"], "code_sha256": agent_code_sha256()},
                "workload": {k: v for k, v in self.workload.document.items() if k != "sig"} | {"doc_signed": True},
                "delegation": state["delegation"] | {"user": user_id, "agent": self.agent_id, "incident": incident_id},
                "effective_authority": self.effective, "bundle_version": b.version, "bundle_digest": b.digest,
            }, workflow_id=self.wf_id)
            self.store.checkpoint(self.wf_id, "submitted", state, os.getpid())
        return self.wf_id

    def _bind(self, state: dict[str, Any]) -> None:
        """(Re)establish identity for this process from durable state; effective authority is recomputed under the current bundle."""
        self.wf_id = state["workflow_id"]
        self.user = self.ids.user(state["user_id"])
        self.tenant = self.user.tenant
        self.incident = state["incident"]
        b = self.bundle()
        self.workload = self.ids.attest_workload(b.agent(self.agent_id)["workload"])
        dd = state["delegation"]
        self.delegation = Delegation(dd["id"], self.user.id, self.agent_id, self.incident["id"], set(dd["scope"]), dd["issued_at"], dd["expires_at"], set(dd["requested"]))
        self.effective = self.ids.effective(self.user, self.agent_id, self.delegation, self.workload)
        self.budget = Budget(self.store, self.wf_id, b.budget(b.agent(self.agent_id)["budget"]))
        g = b.doc["guardrails"]
        self.guard = ContextGuard(g["context_guard"], self.guard_override)
        self.out_guard = OutputGuard(g["output_guard"])
        self.context = ContextGateway(self.store, b.doc["data"], self.guard)
        self.memory = MemoryService(self.store, b.doc["data"], self.ev)
        residency = self.world_seed["tenants"][self.tenant]["residency"]
        self.models = ModelGateway(ROOT, b.doc["models"], self.dir / "faults.json", self.t, self.ev, self.budget, residency)
        mc = b.agent(self.agent_id)["model_capability"]
        self.agent = IncidentAgent(self._model_port, mc["class"], mc["quality"])

    def _model_port(self, *, purpose: str, cls: str, quality: str, prompt: str, round_: int | None = None) -> dict[str, Any]:
        order = self.bundle().doc["data"]["classification_order"]
        classification = max((c.get("classification", "internal") for c in self._state.get("context", [])), key=order.index, default="internal")
        return self._await(self.models.complete(workflow_id=self.wf_id, purpose=purpose, cls=cls, quality=quality, classification=classification,
                                                order=order, prompt=prompt, round_=round_))

    @staticmethod
    def _await(value):
        return value   # the model gateway is synchronous; kept as a seam for an async provider

    # ---- orchestration -----------------------------------------------------------------------------------------------------
    async def run(self, wf_id: str, *, recovery: str | None = None) -> dict[str, Any]:
        state = self.store.latest(wf_id)
        self._state = state
        self._bind(state)
        parent = context_from_traceparent(state["traceparent"])
        with self.t.start_as_current_span("workflow.run", context=parent, attributes={"platform.workflow_id": wf_id, "process.pid": os.getpid()}):
            self.ev.event("process.started", workflow_id=wf_id, resumed_from=state["done"][-1] if state["done"] else "submitted",
                          status=state["status"], pid=os.getpid())
            for step in STEPS:
                if step in state["done"] or state["status"] in TERMINAL:
                    continue
                try:
                    self.budget.charge("workflow_step", 1, step)
                    with span(self.t, f"workflow.step {step}", **{"platform.step": step}):
                        parked = await getattr(self, f"_step_{step}")(state, recovery)
                except BudgetExceeded as exc:
                    state["status"], state["error"] = "BUDGET_EXCEEDED", {"code": exc.code, "limit": exc.limit, "used": exc.used, "cap": exc.cap, "on": exc.attempted}
                    self.ev.record("budget.exceeded", state["error"] | {"usage": self.budget.usage()}, workflow_id=wf_id)
                except ActionDenied as exc:
                    state["status"], state["error"] = "DENIED", {"code": exc.code, "detail": exc.detail, "step": step}
                    self.ev.record("workflow.denied", state["error"], workflow_id=wf_id)
                except NoEligibleModel as exc:
                    state["status"], state["error"] = "FAILED_CLOSED", {"code": "NO_ELIGIBLE_MODEL", "detail": str(exc), "step": step}
                    self.ev.record("workflow.failed_closed", state["error"], workflow_id=wf_id)
                else:
                    if parked:
                        state["status"] = "WAITING_APPROVAL"
                        self.store.checkpoint(wf_id, step + ":parked", state, os.getpid())
                        self.ev.event("workflow.parked", workflow_id=wf_id, step=step)
                        return state
                    state["done"].append(step)
                    if step == "complete":
                        state["status"] = "COMPLETED"
                    elif state["status"] not in TERMINAL:
                        state["status"] = "RUNNING"
                self.store.checkpoint(wf_id, step, state, os.getpid())
                self.ev.event("checkpoint", workflow_id=wf_id, step=step, status=state["status"])
            self.ev.event("process.finished", workflow_id=wf_id, status=state["status"])
            return state

    def task(self, state) -> dict[str, Any]:
        inc = state["incident"]
        return {"tenant": self.tenant, "request": state["request"], "incident": inc["id"], "service": inc["service"], "environment": inc["environment"]}

    async def _step_intake(self, state, _):
        state["observations"].append(self.context.admit_observation("incident.get_incident",
                                                                    await self.tools.read("incident.get_incident", {"incident_id": state["incident"]["id"]})))

    async def _step_context(self, state, _):
        inc = state["incident"]
        r = self.context.retrieve(tenant=self.tenant, environment=inc["environment"], groups=self.user.groups, clearance=self.user.clearance,
                                  query=f"{inc['service']} {inc['title']} {inc['description']}")
        cls = {k["id"]: k["classification"] for k in self.world_seed["knowledge"]}
        state["context"] = [{**i, "classification": cls.get(i["id"], "internal")} for i in r["selected"]]
        self.ev.record("context.assembled", {"selected": [i["id"] for i in r["selected"]], "excluded": r["excluded"], "predicates": r["predicates"],
                                             "guard": [{"id": i["id"], "action": i["guard"]} for i in r["selected"]]},
                       workflow_id=self.wf_id, category="context", detail=r)

    async def _step_investigate(self, state, _):
        inc = state["incident"]
        state["offered"] = self.tools.discover(f"{inc['title']} {inc['service']} latency release rollback")
        for rnd in range(1, 50):
            plan = self.agent.plan(self.task(state), state["context"], state["observations"], state["offered"], rnd)
            for intent in plan.get("intents", []):
                try:
                    res = await self.tools.read(intent["capability"], intent["arguments"])
                    obs = self.context.admit_observation(intent["capability"], res)
                    if obs["guard"]:
                        self.ev.record("guardrail.context", {"capability": intent["capability"], "events": obs["guard"]}, workflow_id=self.wf_id)
                except ActionDenied as exc:
                    obs = {"capability": intent["capability"], "result": {"refused": exc.code}, "guard": []}
                state["observations"].append(obs)
            self.store.checkpoint(self.wf_id, f"investigate:round{rnd}", state, os.getpid())
            if plan.get("done"):
                return

    async def _step_propose(self, state, _):
        out = self.agent.propose(self.task(state), state["context"], state["observations"], state["offered"])
        problems = self.out_guard.check(out.get("proposal"))
        if problems:
            raise ActionDenied("PROPOSAL_MALFORMED", "; ".join(problems))
        state["proposal"] = out["proposal"]
        state["diagnosis"] = out.get("diagnosis")
        self.ev.record("action.proposed", {"capability": out["proposal"]["capability"], "arguments": out["proposal"]["arguments"],
                                           "rationale": out["proposal"]["rationale"], "evidence": out["proposal"]["evidence"],
                                           "diagnosis": out.get("diagnosis"), "agent_code_sha256": agent_code_sha256()}, workflow_id=self.wf_id)

    async def _step_authorize(self, state, _):
        p = state["proposal"]
        az = await self.tools.authorize(p["capability"], p["arguments"])
        state["invocation"], state["digest"], state["decision"] = az["invocation"], az["digest"], az["decision"]
        d = az["decision"]
        if d["decision"] == "DENY":
            raise ActionDenied(d["code"], "; ".join(d["reasons"]), d)
        if d["decision"] == "REQUIRE_APPROVAL":
            req = self.approvals.request(self.wf_id, az["invocation"], self.user.id, d["decision_id"])
            state["approval_id"] = req["approval_id"]
            self.ev.record("approval.requested", {"approval_id": req["approval_id"], "digest": req["digest"], "canonical": req["canonical"],
                                                  "approver_role": self.bundle().policy["approval"]["approver_role"], "decision_id": d["decision_id"]},
                           workflow_id=self.wf_id, category="approvals")

    async def _step_await_approval(self, state, _):
        if not state.get("approval_id"):
            return False
        a = self.approvals.get(state["approval_id"])
        if a["status"] == "PENDING":
            return True
        self.ev.record("approval.observed", {"approval_id": a["id"], "status": a["status"], "approver": a["approver"], "digest": a["digest"]},
                       workflow_id=self.wf_id, category="approvals")
        if a["status"] != "APPROVED":
            state["status"] = "REJECTED"
        return False

    async def _step_execute(self, state, _recovery):
        crash_point("after_approval_checkpoint")
        inv = state["invocation"]
        approval = self.approvals.get(state["approval_id"]) if state.get("approval_id") else None
        recovery = None
        if unfinished_attempt(self.store, self.wf_id, invocation_digest(inv) if inv else ""):
            recovery = os.environ.get("PAP_RECOVERY", "lookup")
            self.ev.record("recovery.detected", {"reason": "journal has a STARTED attempt with no outcome (ambiguous failure)", "mode": recovery,
                                                 "pid": os.getpid()}, workflow_id=self.wf_id)
        self.ev.record("invocation.restored", {"digest_in_checkpoint": state["digest"], "digest_recomputed": invocation_digest(inv),
                                               "arguments": inv["arguments"]}, workflow_id=self.wf_id)
        state["result"] = await self.tools.execute(inv, approval, recovery=recovery)

    async def _step_verify(self, state, _):
        a = state["invocation"]["arguments"]
        st = await self.tools.read("release.get_deployment_status", {"service": a["service"], "environment": a["environment"]})
        m = await self.tools.read("incident.get_metrics", {"service": a["service"], "environment": a["environment"]})
        state["verification"] = {"running_version": st["running_version"], "target_version": a["target_version"],
                                 "p95_ms": m["latency_p95_ms"], "slo_p95_ms": m["slo_p95_ms"],
                                 "verified": st["running_version"] == a["target_version"] and not m["breaching_slo"]}
        self.ev.record("effect.verified", state["verification"], workflow_id=self.wf_id)

    async def _step_record(self, state, _):
        outcome = {"result": state["result"], "verification": state["verification"]}
        note = self.agent.summarize(self.task(state), outcome)
        state["note"] = note
        self.memory.write(tenant=self.tenant, kind="incident_outcome", text=note.get("memory", ""), workflow_id=self.wf_id,
                          provenance={"verified_outcome": state["verification"]["verified"], "workflow_id": self.wf_id, "trace_id": state["traceparent"].split("-")[1],
                                      "source_evidence": [state["result"].get("rollback_id"), state["digest"]]})

    async def _step_complete(self, state, _):
        ev = evaluate_workflow(self.dir, self.wf_id, state)
        state["evaluation"] = {"passed": ev["passed"], "total": ev["total"]}
        self.ev.record("evaluation.recorded", ev, workflow_id=self.wf_id)
