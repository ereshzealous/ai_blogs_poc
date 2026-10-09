"""Policy decision point: ordered rules, first match wins, default deny.  Pure function of facts about one call."""

from __future__ import annotations

from typing import Any

from hai.config import load
from hai.contracts import PolicyDecision


class PolicyEngine:
    def __init__(self) -> None:
        cfg = load("policies.yaml")
        self.rules: list[dict[str, Any]] = cfg["rules"]
        self.approval_ttl_s = float(cfg["approvals"]["ttl_s"])

    def decide(self, facts: dict[str, Any]) -> PolicyDecision:
        for r in self.rules:
            if all(facts.get(k) == v for k, v in r["when"].items()):
                return PolicyDecision(effect=r["effect"], rule=r["id"], reason=r["reason"],
                                      required_role=r.get("required_role"), required_scope=r.get("required_scope"))
        return PolicyDecision(effect="DENY", rule="P9-default", reason="no rule matched")
