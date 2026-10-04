"""Deterministic authorization.  Reasoning may be probabilistic; this is not.

`evaluate` is a pure function of (capability metadata, arguments, principal, incident environment) and the rules in
config/policies.yaml.  First matching rule wins.  Nothing the model says can reach it except the arguments of the
action it proposed, and those are checked, not trusted.
"""

from __future__ import annotations

from typing import Any

from layered_platform.config import load
from layered_platform.contracts import PolicyDecision


class PolicyEngine:
    def __init__(self, rules: list[dict[str, Any]] | None = None):
        self.rules = rules if rules is not None else load("policies.yaml")["rules"]

    def evaluate(self, capability: str, meta: dict[str, Any] | None, args: dict[str, Any], incident_environment: str) -> PolicyDecision:
        facts = {
            "registered": meta is not None,
            "kind": (meta or {}).get("kind"),
            "risk": (meta or {}).get("risk"),
            "environment": args.get("environment"),
            "environment_mismatch": args.get("environment") is not None and args.get("environment") != incident_environment,
            "capability": capability,
        }
        for rule in self.rules:
            if all(facts.get(k) == v for k, v in rule.get("when", {}).items()):
                return PolicyDecision(effect=rule["effect"], rule=rule["id"], reason=rule["reason"], required_role=rule.get("required_role"))
        return PolicyDecision(effect="DENY", rule="P-none", reason="no rule matched")
