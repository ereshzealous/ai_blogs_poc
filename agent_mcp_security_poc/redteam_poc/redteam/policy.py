"""The policy decision point (Authorization & Policy, T2). Deterministic, evaluated in code, outside the model. The model
cannot name its own role or an approval: the PDP reads identity and the capability tier, never a claim in content.

It returns ALLOW, DENY or REQUIRE_APPROVAL. Unknown capability or any evaluation error is DENY (fail closed).
"""
from __future__ import annotations

from redteam.base import Decision, GateEvent, load_yaml
from redteam.identity import Context


class PolicyEngine:
    def __init__(self) -> None:
        cfg = load_yaml("policy.yaml")
        self.caps = load_yaml("capabilities.yaml")["capabilities"]
        self.tiers = cfg["tiers"]
        self.limits = cfg["limits"]
        self.approval = cfg["approval"]

    def tier(self, tool: str) -> str | None:
        return (self.caps.get(tool) or {}).get("tier")

    def decide(self, tool: str, args: dict, ctx: Context, principals: dict) -> GateEvent:
        tier = self.tier(tool)
        if tier is None:
            return GateEvent("policy", Decision.DENY, "unknown capability (fail closed)", {"tool": tool})
        rule = self.tiers.get(tier, {})
        base = rule.get("decision")

        if base == "DENY":
            return GateEvent("policy", Decision.DENY, f"capability tier '{tier}' is prohibited for this agent",
                             {"tool": tool, "tier": tier})
        if base in ("ALLOW",):
            return GateEvent("policy", Decision.ALLOW, f"tier '{tier}' allowed", {"tool": tool, "tier": tier})
        if base == "ALLOW_IF_WITHIN_LIMIT":
            spec = self.limits.get(tool)
            if not spec:
                return GateEvent("policy", Decision.REQUIRE_APPROVAL, "high_write without a limit rule (fail safe)")
            amount = float(args.get(spec["field"], 0.0) or 0.0)
            limit = ctx.limit(spec["limit_from"], principals)
            if amount <= limit:
                return GateEvent("policy", Decision.ALLOW,
                                 f"{spec['field']} {amount:.2f} within the acting human's {spec['limit_from']} {limit:.2f}",
                                 {"amount": amount, "limit": limit})
            return GateEvent("policy", Decision.REQUIRE_APPROVAL,
                             f"{spec['field']} {amount:.2f} over {spec['limit_from']} {limit:.2f}: supervisor approval required",
                             {"amount": amount, "limit": limit})
        return GateEvent("policy", Decision.DENY, "no decision mapping (fail closed)", {"tier": tier})
