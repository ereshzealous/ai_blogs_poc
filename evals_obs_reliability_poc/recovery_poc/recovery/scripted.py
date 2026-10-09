"""Scripted (deterministic) models: the decision step for the fault scenarios and the deterministic model change (H9).

SIMULATED.  These are not language models.  They implement the support policy as fixed rules, so that every fault
scenario sees the same decision and the recovery layer, not the model, is what varies.  The real-model slice
(modelslice.py) measures actual models against the same output contract.

  scripted-v1         the baseline: credits the later duplicate
  scripted-v2         the candidate with a behaviour regression: credits the EARLIER (original) charge of a duplicate pair
  scripted-fallback   the fallback model: same rules as v1, a different deployment
"""

from __future__ import annotations

import json

LIMIT = 200.00
TICKET_WORDS = ("address", "moved", "cancel", "invoice", "copy")


def duplicate_pair(charges: list[dict]) -> tuple[dict, dict] | None:
    """(original, duplicate): same amount and description, the second within 60 s of the first; pending holds excluded."""
    real = sorted((c for c in charges if not c.get("pending")), key=lambda c: c["date"])
    for i, a in enumerate(real):
        for b in real[i + 1:]:
            if a["amount"] == b["amount"] and a["description"] == b["description"] and _seconds(a["date"], b["date"]) <= 60:
                return a, b
    return None


def _seconds(a: str, b: str) -> float:
    from datetime import datetime
    f = "%Y-%m-%dT%H:%M:%SZ"
    return abs((datetime.strptime(b, f) - datetime.strptime(a, f)).total_seconds())


def decide(model: str, message: str, charges: list[dict], docs: list[dict], policy_aware: bool = True) -> dict:
    """The decision as a dict (the output contract of experiments/model_slice/prompt.md).

    policy_aware=False is the agent of the fault scenarios: it proposes, and the deterministic policy engine and the
    provider decide (S07 needs an over-limit proposal for the policy to deny; S13 a disputed charge for the provider to
    reject).  The slice cases (H9) use policy_aware=True, the contract the prompt states.
    """
    msg = message.lower()
    cite = lambda *ids: [d for d in ids if d in {x["id"] for x in docs}] or list(ids)   # noqa: E731
    pair = duplicate_pair(charges)
    if any(c.get("pending") for c in charges) and (pair is None):
        return _d("no_action", {}, False, cite("kb-auth-holds"), "The second item is a pending authorization that is released automatically.")
    if pair is None:
        if any(w in msg for w in TICKET_WORDS):
            kb = next((k for w, k in (("address", "kb-address-change"), ("moved", "kb-address-change"), ("cancel", "kb-cancellation"),
                                       ("invoice", "kb-invoice-copy"), ("copy", "kb-invoice-copy")) if w in msg))
            return _d("create_ticket", {"summary": "customer request routed to accounts"}, False, cite(kb), "We've passed this to the right team.")
        if len([c for c in charges if not c.get("pending")]) >= 2:
            return _d("create_ticket", {"summary": "charges with different amounts: billing review"}, False, cite("kb-price-difference"),
                      "These charges have different amounts; billing will review them.")
        return _d("no_action", {}, False, [], "There is nothing to correct on this account.")
    original, dup = pair
    target = original if model == "scripted-v2" else dup
    if policy_aware and (dup.get("disputed") or original.get("disputed")):
        return _d("escalate_to_human", {"reason": "charge under dispute"}, False, cite("kb-disputes"), "A specialist will review this charge.")
    if policy_aware and dup["amount"] > LIMIT:
        return _d("escalate_to_human", {"reason": "credit above the agent limit"}, True, cite("kb-credit-limits"), "A colleague will approve this credit.")
    return _d("issue_credit", {"charge_id": target["id"], "amount": target["amount"]}, False, cite("kb-duplicate-v3"),
              f"We've credited {target['amount']:.2f} for the duplicate charge to your account.")


def _d(tool, args, approval, cites, reply) -> dict:
    return {"tool": tool, "arguments": args, "requires_approval": approval, "citations": cites, "reply": reply}


def render(decision: dict, fault: str | None = None) -> str:
    """The model's raw text, with an injected output fault where the scenario asks for one."""
    d = json.loads(json.dumps(decision))
    if fault == "invalid_json":
        return '{"tool": "issue_credit", "arguments": {"charge_id": '        # truncated: not JSON
    if fault == "wrong_tool":
        d["tool"] = "delete_customer_account"
    if fault == "bad_args" and d["tool"] == "issue_credit":
        d["arguments"]["amount"] = round(d["arguments"]["amount"] * 10, 2)
    return json.dumps(d)


def usage(prompt: str, completion: str) -> dict:
    """Deterministic token counts (characters / 4), so cost telemetry is reproducible."""
    return {"input_tokens": max(1, len(prompt) // 4), "output_tokens": max(1, len(completion) // 4)}
