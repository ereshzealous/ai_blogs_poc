"""The action gateway: the only path from the platform to an enterprise system.

    registry lookup -> policy -> approval grant (if required) -> operation identity -> adapter -> MCP call -> audit

Reads and writes both pass through it.  A write is retried after a timeout only because it carries an idempotency key
the backend honours; a read is retried because it has no side effect.  Every attempt is written to `tool_calls` and
every policy decision to `policy_events`, with the workflow id and trace id.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any

import crashpoints
from layered_platform.contracts import ActionContext, PolicyDecision
from layered_platform.policy.approvals import Approvals, ApprovalError
from layered_platform.policy.engine import PolicyEngine
from layered_platform.telemetry.tracing import annotate, current_ids, span
from layered_platform.tools import adapters
from layered_platform.tools.idempotency import Operations, op_id
from layered_platform.tools.mcp_client import McpClientPool, ToolFailed, ToolTimeout
from layered_platform.tools.registry import Registry


class ActionDenied(PermissionError):
    def __init__(self, decision: PolicyDecision):
        super().__init__(f"{decision.rule}: {decision.reason}")
        self.decision = decision


class ApprovalRequired(PermissionError):
    def __init__(self, decision: PolicyDecision, detail: str):
        super().__init__(f"{decision.rule}: {detail}")
        self.decision = decision


class ActionFailed(RuntimeError):
    pass


class ActionGateway:
    def __init__(self, db: sqlite3.Connection, registry: Registry, policy: PolicyEngine, approvals: Approvals, mcp: McpClientPool):
        self.db, self.registry, self.policy, self.approvals, self.mcp = db, registry, policy, approvals, mcp
        self.ops = Operations(db)
        t = registry.spec.get("timeouts", {})
        r = registry.spec.get("retries", {})
        self.timeout = {"read": float(t.get("read_s", 5)), "write": float(t.get("write_s", 5))}
        self.retries = {"read": int(r.get("read", 2)), "write": int(r.get("write_with_key", 2))}

    def authorize(self, capability: str, args: dict[str, Any], ctx: ActionContext) -> PolicyDecision:
        meta = self.registry.get(capability)
        with span("policy.evaluate", **{"f2.workflow_id": ctx.workflow_id, "f2.capability": capability, "f2.principal": ctx.principal}):
            decision = self.policy.evaluate(capability, meta, args, ctx.incident_environment)
            annotate(**{"f2.policy.effect": decision.effect, "f2.policy.rule": decision.rule})
        trace_id, _ = current_ids()
        self.db.execute("INSERT INTO policy_events (workflow_id, capability, args, principal, effect, rule, reason, trace_id, ts) VALUES (?,?,?,?,?,?,?,?,?)",
                        (ctx.workflow_id, capability, json.dumps(args, sort_keys=True), ctx.principal, decision.effect, decision.rule, decision.reason, trace_id, time.time()))
        return decision

    async def execute(self, capability: str, args: dict[str, Any], ctx: ActionContext) -> Any:
        decision = self.authorize(capability, args, ctx)
        if decision.effect == "DENY":
            raise ActionDenied(decision)
        if decision.effect == "REQUIRE_APPROVAL":
            try:
                self.approvals.verify_grant(ctx.approval_id, ctx.workflow_id, capability, args, decision.required_role)
            except ApprovalError as exc:
                raise ApprovalRequired(decision, str(exc)) from None
        meta = self.registry.get(capability)
        assert meta is not None  # P0 denies unregistered capabilities
        kind = meta["kind"]
        to_tool, from_tool = adapters.get(meta.get("adapter", "passthrough"))
        tool_args = to_tool(dict(args))
        op = None
        if kind == "write":
            op = op_id(ctx.workflow_id, ctx.step, capability, args)
            stored = self.ops.begin(op, ctx.workflow_id, capability, args)
            if stored is not None:
                self._audit(ctx, op, capability, meta, tool_args, 0, "deduplicated_by_platform", None, 0.0)
                return stored
            tool_args[meta["key_param"]] = op
        attempts = 1 + self.retries[kind]
        last: Exception | None = None
        for attempt in range(attempts):
            t0 = time.perf_counter()
            with span("execute_tool", **{"f2.workflow_id": ctx.workflow_id, "f2.capability": capability, "f2.op_id": op,
                                         "f2.attempt": attempt, "gen_ai.tool.name": meta["tool"], "f2.mcp.server": meta["server"]}):
                try:
                    raw = await self.mcp.call(meta["server"], meta["tool"], tool_args, self.timeout[kind])
                except ToolTimeout as exc:
                    last = exc
                    annotate(**{"f2.outcome": "timeout"})
                    self._audit(ctx, op, capability, meta, tool_args, attempt, "timeout", str(exc), time.perf_counter() - t0)
                    if op:
                        self.ops.finish(op, "UNKNOWN", error=str(exc))
                    continue
                except ToolFailed as exc:
                    annotate(**{"f2.outcome": "error"})
                    self._audit(ctx, op, capability, meta, tool_args, attempt, "error", str(exc), time.perf_counter() - t0)
                    if op:
                        self.ops.finish(op, "FAILED", error=str(exc))
                    raise ActionFailed(str(exc)) from None
                annotate(**{"f2.outcome": "ok"})
            crashpoints.hit(f"after_tool_result:{capability}")
            result = from_tool(raw)
            self._audit(ctx, op, capability, meta, tool_args, attempt, "ok", None, time.perf_counter() - t0)
            if op:
                self.ops.finish(op, "COMPLETED", result=result)
            return result
        raise ActionFailed(f"{capability}: gave up after {attempts} attempts ({last})")

    def _audit(self, ctx: ActionContext, op: str | None, capability: str, meta: dict[str, Any], args: dict[str, Any], attempt: int,
               outcome: str, error: str | None, wall_s: float) -> None:
        trace_id, _ = current_ids()
        self.db.execute("INSERT INTO tool_calls (workflow_id, op_id, capability, server, tool, args, attempt, outcome, error, wall_s, trace_id, pid, ts) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (ctx.workflow_id, op, capability, meta["server"], meta["tool"], json.dumps(args, sort_keys=True), attempt, outcome, error,
                         round(wall_s, 3), trace_id, os.getpid(), time.time()))

    def describe(self, capability: str) -> tuple[str, dict[str, Any]]:
        """What a model is shown: the capability's platform-owned contract when it has one, else the tool's schema."""
        meta = self.registry.get(capability)
        assert meta is not None
        contract = self.registry.contract(capability)
        if contract:
            return contract["description"], {"type": "object", "properties": contract["properties"], "required": contract["required"]}
        desc, schema = self.mcp.describe(meta["server"], meta["tool"])
        schema = json.loads(json.dumps(schema))
        key = meta.get("key_param")
        if key:  # the model never sees, and so can never invent, an idempotency key
            schema.get("properties", {}).pop(key, None)
        return meta.get("description") or desc, schema
