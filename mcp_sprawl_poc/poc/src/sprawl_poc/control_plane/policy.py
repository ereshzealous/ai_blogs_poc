"""Deterministic, ordered execution policy over a concrete invocation.

The first matching rule wins; if nothing matches the result is DENY.  Inputs are the
canonical (already bound, schema-validated) invocation, the platform registry,
authoritative entity facts from systems of record, and the call context.  Nothing here
calls a model.

    effective_scopes = user_scopes ∩ agent_scopes
    required         = registry.required_scopes(implementation)
    environment      = session environment must equal implementation environment
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..registry.model import Registry
from .invocation import Invocation

ALLOW = "ALLOW"
REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
DENY = "DENY"


@dataclass(frozen=True)
class PolicyDecision:
    decision: str
    rule: str
    reason: str
    policy_version: str
    effective_scopes: tuple[str, ...] = ()

    def as_record(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "rule": self.rule,
            "reason": self.reason,
            "policy_version": self.policy_version,
            "effective_scopes": list(self.effective_scopes),
        }


RULES = (
    "P1_UNREGISTERED",
    "P2_RETIRED",
    "P3_ENVIRONMENT",
    "P4_REGION",
    "P5_NOT_AUTHORITATIVE",
    "P6_SCOPE",
    "P7_APPROVAL",
    "P8_ALLOW",
    "P9_DEFAULT_DENY",
)


class Policy:
    def __init__(self, registry: Registry):
        self.registry = registry
        self.version = f"policy-v1+registry-{registry.version}"

    def evaluate(self, inv: Invocation, entity_facts: dict[str, Any], approval_valid: bool = False) -> PolicyDecision:
        v = self.version
        rec = self.registry.get(inv.implementation)
        effective = inv.context.user_scopes & inv.context.agent_scopes

        # P1 — the platform does not know this implementation.
        if rec is None:
            return PolicyDecision(DENY, "P1_UNREGISTERED", f"{inv.implementation} is not in the governance registry", v)
        # P2 — lifecycle.
        if rec.lifecycle == "retired":
            hint = f"; replaced by {rec.replaced_by}" if rec.replaced_by else ""
            return PolicyDecision(DENY, "P2_RETIRED", f"{inv.implementation} is retired{hint}", v)
        # P3 — environment.
        if rec.environment != inv.context.environment:
            return PolicyDecision(
                DENY, "P3_ENVIRONMENT", f"{inv.implementation} runs in {rec.environment}; session is {inv.context.environment}", v
            )
        # P4 — region of the implementation vs region of the entity it acts on.
        region = entity_facts.get("region")
        if rec.region != "global" and region and rec.region != region:
            return PolicyDecision(DENY, "P4_REGION", f"{inv.implementation} serves {rec.region}; entity is in {region}", v)
        # P5 — authority: a registered, active, in-env implementation may still not be the one the organisation uses.
        if not self.registry.is_authoritative(inv.implementation, region):
            auth = self.registry.authoritative_for(rec.capability, region)
            return PolicyDecision(
                DENY, "P5_NOT_AUTHORITATIVE", f"{inv.implementation} is not authoritative for {rec.capability} (use {auth})", v
            )
        # P6 — effective authority.
        missing = [s for s in rec.required_scopes if s not in effective]
        if missing:
            return PolicyDecision(
                DENY, "P6_SCOPE", f"effective scopes lack {', '.join(missing)}", v, tuple(sorted(effective))
            )
        # P7 — risk requires human approval for this exact invocation.
        needs, why = rec.approval.requires(inv.arguments)
        if not needs and rec.side_effect == "financial_write" and entity_facts.get("prior_financial_writes", 0) >= 1:
            needs, why = True, "a second money-moving action in the same request needs supervisor approval"
        if needs and not approval_valid:
            return PolicyDecision(REQUIRE_APPROVAL, "P7_APPROVAL", why, v, tuple(sorted(effective)))
        # P8 — safe and permitted.
        if rec.lifecycle == "active":
            return PolicyDecision(ALLOW, "P8_ALLOW", "registered, active, in environment, authoritative, in scope", v, tuple(sorted(effective)))
        # P9 — nothing matched.
        return PolicyDecision(DENY, "P9_DEFAULT_DENY", "no rule allowed this invocation", v)
