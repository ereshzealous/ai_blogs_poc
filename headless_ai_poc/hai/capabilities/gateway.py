"""The capability gateway: the policy enforcement point and the only path to an enterprise system.

For every call:  identity still valid -> registered -> contract (schema) -> policy decision -> approval bound to the
exact call -> idempotency key -> execute with timeout and bounded retries -> audit -> span.

The gateway holds the one credential per backend system.  Agents and heads hold none.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from hai.capabilities.registry import Registry, SchemaError
from hai.config import Clock, digest
from hai.contracts import CapabilityCall, CapabilityResult, ExecutionIdentity, PolicyDecision
from hai.control.approvals import Approvals
from hai.control.audit import AuditLog
from hai.control.identity import Directory
from hai.control.policy import PolicyEngine
from hai.control.telemetry import Telemetry
from hai.world import World

MAX_CALLS_PER_EXECUTION = 40      # a runaway-loop budget, enforced here rather than trusted to the reasoner


@dataclass
class CallContext:
    execution_id: str
    correlation_id: str
    environment: str
    identity: ExecutionIdentity


def adapters(world: World) -> dict[str, Callable[..., Any]]:
    """Capability -> backend.  In production each backend is an MCP server or an API; here, the simulated world."""
    return {
        "getServiceHealth": world.service_health, "getLogs": world.logs, "getTraceSummary": world.trace_summary,
        "getRecentDeployments": world.deployments, "getKnownIncidents": world.known_incidents, "suggestRollback": world.suggest_rollback,
        "createIncident": world.create_incident, "postIncidentUpdate": world.post_update, "notifyChannel": world.notify,
        "rollbackDeployment": world.rollback, "deleteDeployment": world.delete_deployment,
    }


class CapabilityGateway:
    def __init__(self, db, world: World, registry: Registry, policy: PolicyEngine, approvals: Approvals, directory: Directory,
                 audit: AuditLog, telemetry: Telemetry, clock: Clock):
        self.db, self.world, self.registry, self.policy, self.approvals = db, world, registry, policy, approvals
        self.directory, self.audit, self.tel, self.clock = directory, audit, telemetry, clock
        self.backends = adapters(world)
        self.calls_by_execution: dict[str, int] = {}

    def call(self, ctx: CallContext, call: CapabilityCall, approval_id: str | None = None) -> CapabilityResult:
        cap = self.registry.get(call.capability)
        kind = cap["kind"] if cap else "unknown"
        with self.tel.span("action" if kind == "write" else "tool", ctx.correlation_id, call.capability, step=call.step,
                           execution=ctx.execution_id) as span:
            res = self._call(ctx, call, cap, approval_id)
            span["attrs"].update(status=res.status, rule=res.decision.rule if res.decision else None, attempts=res.attempts)
            self.tel.count(f"capability.{res.status}")
        return res

    def _call(self, ctx: CallContext, call: CapabilityCall, cap: dict[str, Any] | None, approval_id: str | None) -> CapabilityResult:
        n = self.calls_by_execution.get(ctx.execution_id, 0) + 1
        self.calls_by_execution[ctx.execution_id] = n
        if n > MAX_CALLS_PER_EXECUTION:
            return self._done(ctx, call, cap, CapabilityResult(capability=call.capability, status="denied", error="call budget exhausted",
                              decision=PolicyDecision(effect="DENY", rule="B1-budget", reason="call budget exhausted")))
        if not self.directory.valid(ctx.identity):
            return self._done(ctx, call, cap, CapabilityResult(capability=call.capability, status="error", error="execution identity expired"))
        if cap is None:
            d = self.policy.decide({"registered": False})
            return self._done(ctx, call, cap, CapabilityResult(capability=call.capability, status="denied", decision=d))
        try:
            self.registry.validate(cap, call.arguments)
        except SchemaError as e:
            return self._done(ctx, call, cap, CapabilityResult(capability=call.capability, status="error", error=f"schema: {e}"))
        env = call.arguments.get("environment", ctx.environment)
        facts = {"registered": True, "kind": cap["kind"], "risk": cap.get("risk", "none"), "environment": env,
                 "environment_mismatch": env != ctx.environment, "scope_granted": cap["scope"] in ctx.identity.scopes}
        d = self.policy.decide(facts)
        authorized_by = None
        if d.effect == "DENY":
            return self._done(ctx, call, cap, CapabilityResult(capability=call.capability, status="denied", decision=d))
        if d.effect == "APPROVAL_REQUIRED":
            want = Approvals.call_digest(ctx.execution_id, call.capability, call.arguments)
            a = self.approvals.get(approval_id) if approval_id else None
            if not a or a["status"] != "APPROVED" or a["digest"] != want:
                req = self.approvals.request(ctx.execution_id, call.capability, call.arguments, d.required_role or "", d.required_scope,
                                             ctx.identity.agent)
                return self._done(ctx, call, cap, CapabilityResult(capability=call.capability, status="approval_required", decision=d,
                                                                   approval_id=req["id"]), audit_kind="approval.requested",
                                  extra={"approval_id": req["id"], "digest": req["digest"], "required_role": d.required_role})
            authorized_by = a["decided_by"]
        key = digest({"execution": ctx.execution_id, "capability": call.capability, "arguments": call.arguments}) if cap["kind"] == "write" else None
        if key:
            seen = self.db.execute("SELECT response FROM calls WHERE key=?", (key,)).fetchone()
            if seen:  # already executed for this execution: answer from the platform's record, touch nothing
                return self._done(ctx, call, cap, CapabilityResult(capability=call.capability, status="ok", decision=d,
                                                                   output=json.loads(seen["response"]), attempts=0),
                                  extra={"replayed": True, "authorized_by": authorized_by, "approval_id": approval_id})
        args = dict(call.arguments) | ({"idempotency_key": key} if key and cap.get("idempotent") else {})
        attempts, last_err = 0, None
        retries = cap.get("retries", 0) if (cap["kind"] == "read" or cap.get("idempotent")) else 0
        while attempts <= retries:
            attempts += 1
            try:
                out = self._invoke(call.capability, args)
                if key:
                    self.db.execute("INSERT OR REPLACE INTO calls VALUES (?,?,?,?)", (key, ctx.execution_id, call.capability, json.dumps(out)))
                    self.db.commit()
                if approval_id and authorized_by:
                    self.approvals.consume(approval_id)
                return self._done(ctx, call, cap, CapabilityResult(capability=call.capability, status="ok", decision=d, output=out,
                                                                   attempts=attempts, untrusted=bool(cap.get("untrusted_output"))),
                                  extra={"authorized_by": authorized_by, "approval_id": approval_id, "idempotency_key": key})
            except TimeoutError as e:
                last_err = f"timeout: {e}"
                self.clock.advance(cap.get("timeout_s", 2))
            except ValueError as e:
                last_err = f"backend rejected: {e}"
                break
        return self._done(ctx, call, cap, CapabilityResult(capability=call.capability, status="error", decision=d, error=last_err, attempts=attempts))

    def _invoke(self, capability: str, args: dict[str, Any]) -> Any:
        faults = self.world.faults.get(capability) or []
        fault = faults.pop(0) if faults else None
        if fault == "timeout":
            raise TimeoutError(f"{capability} did not answer")
        out = self.backends[capability](**args)
        if fault == "lost_response":  # the backend did the work; the answer never arrived
            raise TimeoutError(f"{capability} response lost after the backend committed")
        return out

    def _done(self, ctx: CallContext, call: CapabilityCall, cap: dict[str, Any] | None, res: CapabilityResult,
              audit_kind: str = "capability.call", extra: dict[str, Any] | None = None) -> CapabilityResult:
        self.clock.advance(1)
        rec = {"capability": call.capability, "version": cap["version"] if cap else None, "system": cap["system"] if cap else None,
               "kind": cap["kind"] if cap else "unregistered", "risk": cap.get("risk", "none") if cap else None, "step": call.step,
               "arguments": call.arguments, "status": res.status, "rule": res.decision.rule if res.decision else None,
               "error": res.error, "attempts": res.attempts, "invoker": ctx.identity.invoker, "on_behalf_of": ctx.identity.on_behalf_of,
               "agent": ctx.identity.agent, "workload": ctx.identity.workload,
               "output": res.output if cap and cap["kind"] == "write" else None} | (extra or {})
        self.audit.record(audit_kind if audit_kind != "capability.call" else "capability.call", ctx.execution_id, ctx.correlation_id, **rec)
        return res
