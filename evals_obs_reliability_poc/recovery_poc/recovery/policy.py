"""The recovery policy: config/recovery-matrix.toml [[rules]], first match wins.  No rule consults a model.

    failure class + execution certainty + side-effect semantics (tool contract) + persisted state (counters, key age)
                                                 -> action, the rule that chose it, a terminal status if any
"""

from __future__ import annotations

from dataclasses import dataclass

from .common import matrix

COUNTERS = {"retries_lt": "retries", "repairs_lt": "repairs", "reconciles_lt": "reconciles"}
SEMANTIC = ("effect", "idempotency", "status_query", "compensation")


@dataclass
class Decision:
    action: str
    rule: str
    why: str
    status: str | None = None


def matches(rule: dict, s: dict) -> bool:
    if "class" in rule and s["class"] not in rule["class"]:
        return False
    if "certainty" in rule and s.get("certainty") not in rule["certainty"]:
        return False
    for k in SEMANTIC:
        if k in rule:
            v = s.get(k, "NONE")
            if rule[k] == "ANY":
                if v in (None, "NONE"):
                    return False
            elif v != rule[k]:
                return False
    for k in ("key_fresh", "fallback_available"):
        if k in rule and bool(s.get(k)) != rule[k]:
            return False
    for k, field in COUNTERS.items():
        if k in rule and not s.get(field, 0) < rule[k]:
            return False
    return True


def decide(situation: dict, m: dict | None = None) -> Decision:
    m = m or matrix()
    for rule in m["rules"]:
        if matches(rule, situation):
            return Decision(rule["action"], rule["id"], rule["why"], rule.get("status"))
    raise AssertionError("the matrix ends in a catch-all rule")


def situation(failure_class: str, certainty: str | None, contract: dict | None, counters: dict, *, key_fresh: bool = False,
              fallback_available: bool = False) -> dict:
    c = contract or {}
    return {"class": failure_class, "certainty": certainty, **{k: c.get(k, "NONE") for k in SEMANTIC},
            "key_fresh": key_fresh, "fallback_available": fallback_available, **counters}
