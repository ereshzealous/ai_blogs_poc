"""Action gateway: the only path from reasoning to an enterprise system.

    intended action -> registry -> policy -> (approval grant check) -> idempotency -> bounded retry -> MCP

This layer, and only this layer, retries tool calls. Reads retry on timeout. Writes retry only when they carry an
idempotency key, because a timed-out write may already have happened.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any

from agent_platform.actions.audit import AuditLog
from agent_platform.actions.idempotency import IdempotencyStore
from agent_platform.actions.mcp_pool import McpPool, ToolFailed, ToolTimeout
from agent_platform.actions.policy import PolicyEngine
from agent_platform.actions.registry import CapabilityRegistry
from agent_platform.actions.types import (ActionContext, ActionResult, ApprovalGrant, Decision, Invocation, PolicyResult,
                                          canonical)
from agent_platform.faults import maybe_crash
from agent_platform.telemetry.tracing import set_attrs, span


class ActionGateway:
    def __init__(self, registry: CapabilityRegistry, policy: PolicyEngine, pool: McpPool,
                 idempotency: IdempotencyStore, audit: AuditLog):
        self.registry = registry
        self.policy = policy
        self.pool = pool
        self.idempotency = idempotency
        self.audit = audit

    # -------------------------------------------------------------- what a model may see
    def definition(self, tool_id: str) -> dict[str, Any]:
        record = self.registry.get(tool_id)
        assert record is not None, tool_id
        schema = json.loads(json.dumps(self.pool.schema(tool_id)))
        schema.get("properties", {}).pop("idempotency_key", None)  # the platform owns keys, not the model
        schema.pop("title", None)
        return {"type": "function", "function": {"name": record.exposed_name, "description": self.pool.description(tool_id),
                                                 "parameters": schema}}

    def toolbox(self, ctx: ActionContext, tool_ids: list[str]) -> AgentToolbox:
        return AgentToolbox(self, ctx, tool_ids)

    # -------------------------------------------------------------- decisions
    def evaluate(self, inv: Invocation, ctx: ActionContext) -> PolicyResult:
        result = self.policy.evaluate(inv, ctx)
        self.audit.write("policy.decision", ctx.workflow_id, step=ctx.step, tool_id=inv.tool_id,
                         arguments=inv.arguments, user=ctx.user_id, agent=ctx.agent_id, **result.to_dict())
        return result

    # -------------------------------------------------------------- execution
    async def execute(self, inv: Invocation, ctx: ActionContext, *, operation_id: str | None = None,
                      grant: ApprovalGrant | None = None) -> ActionResult:
        record = self.registry.get(inv.tool_id)
        with span(f"execute_tool {inv.tool_id}", **{"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": inv.tool_id,
                                                    "lap.workflow.id": ctx.workflow_id, "lap.step": ctx.step,
                                                    "enduser.id": ctx.user_id, "gen_ai.agent.id": ctx.agent_id,
                                                    "lap.operation_id": operation_id}) as s:
            decision = self.evaluate(inv, ctx)
            set_attrs(s, **{"lap.policy.decision": decision.decision.value, "lap.policy.rule": decision.rule_id})
            if record is None or inv.tool_id not in self.pool.tools:
                return ActionResult(inv.tool_id, "unknown_tool", error=f"unknown tool {inv.tool_id}", policy=decision)
            if decision.decision is Decision.DENY:
                return ActionResult(inv.tool_id, "denied", error=decision.reason, policy=decision)
            if decision.decision is Decision.REQUIRE_APPROVAL:
                if grant is None or grant.digest != decision.digest or grant.role != decision.approver_role:
                    self.audit.write("approval.missing", ctx.workflow_id, tool_id=inv.tool_id, digest=decision.digest)
                    return ActionResult(inv.tool_id, "approval_required", policy=decision,
                                        error="approval required for this exact invocation")
                self.audit.write("approval.verified", ctx.workflow_id, tool_id=inv.tool_id, digest=decision.digest,
                                 approver=grant.approver)

            args = dict(inv.arguments)
            if record.idempotency_key and operation_id:
                prior = self.idempotency.begin(operation_id, inv.tool_id, canonical(inv.arguments))
                if prior and prior["status"] == "COMPLETED":
                    set_attrs(s, **{"lap.idempotency.replayed": True, "lap.idempotency.source": "platform"})
                    self.audit.write("invocation.replayed", ctx.workflow_id, tool_id=inv.tool_id, operation_id=operation_id)
                    return ActionResult(inv.tool_id, "executed", result=prior["result"], policy=decision,
                                        replayed=True, operation_id=operation_id)
                args["idempotency_key"] = operation_id
            elif record.is_write and record.idempotency_key:
                raise ValueError(f"{inv.tool_id} requires an operation id")

            attempts = record.retry.attempts if (not record.is_write or "idempotency_key" in args) else 1
            t0 = time.perf_counter()
            last_error = ""
            for attempt in range(1, attempts + 1):
                if "idempotency_key" in args:
                    self.idempotency.attempt(operation_id or "")
                with span("mcp.call", **{"lap.attempt": attempt, "gen_ai.tool.name": inv.tool_id,
                                         "lap.timeout_s": record.retry.timeout_s}) as call_span:
                    try:
                        payload = await self.pool.call(inv.tool_id, args, record.retry.timeout_s)
                    except ToolTimeout as exc:
                        last_error = str(exc)
                        set_attrs(call_span, **{"lap.outcome": "timeout"})
                        self.audit.write("invocation.timeout", ctx.workflow_id, tool_id=inv.tool_id, attempt=attempt,
                                         operation_id=operation_id)
                        maybe_crash(f"timeout:{inv.tool_id}")
                        if attempt < attempts:
                            await asyncio.sleep(record.retry.backoff_ms * (2 ** (attempt - 1)) * random.uniform(0.8, 1.2) / 1000)
                        continue
                    except ToolFailed as exc:
                        last_error = str(exc)
                        set_attrs(call_span, **{"lap.outcome": "error"})
                        break
                replayed = isinstance(payload, dict) and bool(payload.get("replayed"))
                latency = (time.perf_counter() - t0) * 1000
                set_attrs(s, **{"lap.retry.attempts": attempt, "lap.idempotency.replayed": replayed,
                                "lap.latency_ms": round(latency, 1)})
                if operation_id and "idempotency_key" in args:
                    self.idempotency.complete(operation_id, payload)
                self.audit.write("invocation.executed", ctx.workflow_id, step=ctx.step, tool_id=inv.tool_id,
                                 arguments=inv.arguments, attempts=attempt, replayed=replayed, operation_id=operation_id)
                maybe_crash(f"executed:{inv.tool_id}")
                return ActionResult(inv.tool_id, "executed", result=payload, policy=decision, attempts=attempt,
                                    replayed=replayed, latency_ms=latency, operation_id=operation_id)

            if operation_id and "idempotency_key" in args:
                self.idempotency.fail(operation_id, last_error)
            set_attrs(s, **{"lap.retry.attempts": attempts, "lap.outcome": "failed"})
            self.audit.write("invocation.failed", ctx.workflow_id, step=ctx.step, tool_id=inv.tool_id, error=last_error,
                             operation_id=operation_id)
            return ActionResult(inv.tool_id, "failed", error=last_error, policy=decision, attempts=attempts,
                                latency_ms=(time.perf_counter() - t0) * 1000, operation_id=operation_id)


class AgentToolbox:
    """A `ToolPort` bound to one agent, one workflow step and an allow-list of read tools."""

    def __init__(self, gateway: ActionGateway, ctx: ActionContext, tool_ids: list[str], observation_chars: int = 2400):
        self.gateway = gateway
        self.ctx = ctx
        self.tool_ids = tool_ids
        self.observation_chars = observation_chars
        self.calls: list[dict[str, Any]] = []

    def definitions(self) -> list[dict[str, Any]]:
        return [self.gateway.definition(t) for t in self.tool_ids]

    async def call(self, exposed_name: str, arguments: dict[str, Any]) -> str:
        record = self.gateway.registry.by_exposed_name(exposed_name)
        tool_id = record.tool_id if record else exposed_name.replace("__", ".", 1)
        if record is None or tool_id not in self.tool_ids:
            # Never executed, but still evaluated and audited: an unexpected tool call is a policy event.
            decision = self.gateway.evaluate(Invocation(tool_id, arguments), self.ctx)
            self.gateway.audit.write("invocation.not_offered", self.ctx.workflow_id, step=self.ctx.step,
                                     tool_id=tool_id, policy_decision=decision.decision.value)
            result = ActionResult(tool_id, "denied", policy=decision, extra={"not_offered": True},
                                  error=f"{tool_id} is not available to this agent in step {self.ctx.step}")
        else:
            result = await self.gateway.execute(Invocation(tool_id, arguments), self.ctx)
        self.calls.append({"tool_id": tool_id, "arguments": arguments, "status": result.status,
                           "decision": result.policy.decision.value if result.policy else None})
        if result.status == "executed":
            return json.dumps(result.result, separators=(",", ":"))[: self.observation_chars]
        if result.status == "denied":
            rule = "agent-allow-list" if result.extra.get("not_offered") else (result.policy.rule_id if result.policy else "?")
            return f"DENIED by policy {rule}: {result.error}"
        return f"ERROR ({result.status}): {result.error}"
