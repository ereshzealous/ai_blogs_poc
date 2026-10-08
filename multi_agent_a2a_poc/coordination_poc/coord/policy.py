"""Policy decision point: config/policies.yaml evaluated top to bottom, first match wins.  Identical for every architecture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from coord.util import load_config


@dataclass(frozen=True)
class Decision:
    effect: str          # ALLOW | DENY | REQUIRE_APPROVAL
    rule: str
    reason: str
    required_role: str | None = None


class PolicyEngine:
    def __init__(self) -> None:
        self.rules = load_config("policies.yaml")["rules"]
        self.registry = load_config("capabilities.yaml")["capabilities"]

    def evaluate(self, capability: str, args: dict[str, Any], scopes: list[str], incident_environment: str) -> Decision:
        meta = self.registry.get(capability)
        facts: dict[str, Any] = {
            "registered": meta is not None,
            "capability": capability,
            "kind": meta["kind"] if meta else None,
            "scope_missing": bool(meta) and meta["scope"] not in scopes,
            "environment": args.get("environment"),
            "environment_mismatch": bool(meta) and meta["kind"] == "write" and args.get("environment") != incident_environment,
        }
        for rule in self.rules:
            if all(facts.get(k) == v for k, v in rule["when"].items()):
                return Decision(rule["effect"], rule["id"], rule["reason"], rule.get("required_role"))
        raise AssertionError("policy has no default rule")
