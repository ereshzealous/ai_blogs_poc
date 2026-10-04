"""Deterministic execution policy (config/policies.yaml). Discovery can be heuristic; authorization is not."""

from __future__ import annotations

from typing import Any

from agent_platform.actions.registry import CapabilityRegistry, ToolRecord
from agent_platform.actions.types import ActionContext, Decision, Invocation, PolicyResult, canonical, digest
from agent_platform.config import policies
from agent_platform.telemetry.tracing import span


class PolicyEngine:
    def __init__(self, registry: CapabilityRegistry, rules: list[dict[str, Any]] | None = None):
        self.registry = registry
        self.rules = rules or policies()["rules"]

    def evaluate(self, inv: Invocation, ctx: ActionContext) -> PolicyResult:
        record = self.registry.get(inv.tool_id)
        env = inv.arguments.get("environment")
        bound = digest(inv.tool_id, canonical(inv.arguments), ctx.workflow_id)
        with span("policy.evaluate", **{"gen_ai.tool.name": inv.tool_id, "lap.workflow.id": ctx.workflow_id,
                                        "lap.step": ctx.step, "enduser.id": ctx.user_id}) as s:
            for rule in self.rules:
                if self._matches(rule.get("when", {}), record, inv, ctx):
                    result = PolicyResult(Decision(rule["decision"]), rule["id"], rule["reason"].strip(), bound, env,
                                          rule.get("approver_role"))
                    s.set_attribute("lap.policy.decision", result.decision.value)
                    s.set_attribute("lap.policy.rule", result.rule_id)
                    return result
        raise AssertionError("policy has no fallback rule")

    def _matches(self, when: dict[str, Any], record: ToolRecord | None, inv: Invocation, ctx: ActionContext) -> bool:
        if "registered" in when:
            return (record is not None) == when["registered"]
        if record is None:
            return False
        if "risk" in when and record.risk not in when["risk"]:
            return False
        if "tool_prefix" in when and not inv.tool_id.startswith(when["tool_prefix"]):
            return False
        if "environment" in when and inv.arguments.get("environment") not in when["environment"]:
            return False
        if "service_managed_by" in when:
            meta = self.registry.service(inv.arguments.get("service"))
            if meta.get("managed_by") != when["service_managed_by"]:
                return False
        if when.get("environment_differs_from_incident"):
            env = inv.arguments.get("environment")
            if env is None or ctx.incident_environment is None or env == ctx.incident_environment:
                return False
        return True
