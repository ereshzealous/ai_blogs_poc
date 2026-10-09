"""Deterministic gates between a model's proposal and any execution: parsing, selection, arguments, authorization.

Every gate is the same in all three runtimes.  What differs is what a runtime does when a gate says no.
"""

from __future__ import annotations

import json

from .common import det_id, load_toml

DECISION_TOOLS = ("issue_credit", "create_ticket", "escalate_to_human", "no_action")
KEYS = {"tool", "arguments", "requires_approval", "citations", "reply"}


class GateError(Exception):
    def __init__(self, cls: str, detail: str):
        super().__init__(f"{cls}: {detail}")
        self.cls, self.detail = cls, detail


def parse(text: str) -> dict:
    try:
        d = json.loads(text)
    except json.JSONDecodeError as e:
        raise GateError("MODEL_OUTPUT_INVALID", f"not JSON ({e.msg})")
    if not isinstance(d, dict) or not KEYS <= set(d):
        raise GateError("MODEL_OUTPUT_INVALID", f"missing keys {sorted(KEYS - set(d if isinstance(d, dict) else {}))}")
    return d


def validate(p: dict, charges: list[dict]) -> None:
    """Selection, schema and semantic argument checks for the proposal the runtime is about to act on."""
    if p["tool"] not in DECISION_TOOLS:
        raise GateError("TOOL_SELECTION_INVALID", f"{p['tool']!r} is not an action this task allows")
    if p["tool"] != "issue_credit":
        return
    a = p.get("arguments") or {}
    if set(a) != {"charge_id", "amount"} or not isinstance(a.get("charge_id"), str) or not isinstance(a.get("amount"), (int, float)):
        raise GateError("ARGUMENT_VALIDATION", "issue_credit needs exactly {charge_id: string, amount: number}")
    ch = next((c for c in charges if c["id"] == a["charge_id"]), None)
    if ch is None:
        raise GateError("ARGUMENT_VALIDATION", f"charge {a['charge_id']} is not on this account")
    if abs(a["amount"] - ch["amount"]) > 0.001:
        raise GateError("ARGUMENT_VALIDATION", f"amount {a['amount']:.2f} != charge amount {ch['amount']:.2f}")
    if not ch.get("duplicate_of"):
        raise GateError("ARGUMENT_VALIDATION", f"charge {ch['id']} is not the duplicate of a pair")


class Policy:
    def __init__(self):
        self.p = load_toml("config/policy.toml")

    def authorize(self, run_id: str, attempt: int, tool: str, args: dict, customer: str, charges: list[dict]) -> dict:
        """ALLOW or DENY, with a decision id and the rule.  Same input, same answer: never a candidate for retry."""
        rule, effect = None, "ALLOW"
        if tool not in self.p["allowed_tools"]:
            rule, effect = "P3", "DENY"
        elif tool == "issue_credit":
            ch = next((c for c in charges if c["id"] == args.get("charge_id")), None)
            if args.get("amount", 0) > 200.00:
                rule, effect = "P1", "DENY"
            elif ch is None or ch["customer"] != customer:
                rule, effect = "P2", "DENY"
        reason = next((r["reason"] for r in self.p["rules"] if r["id"] == rule), "within the agent's grant")
        return {"decision_id": det_id("pd", run_id, tool, attempt), "effect": effect, "rule": rule, "reason": reason,
                "policy_version": self.p["version"], "tool": tool}
