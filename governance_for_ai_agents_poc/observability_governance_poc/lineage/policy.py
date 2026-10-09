"""A small deterministic policy engine with versioned policy documents.

    evaluate("prod-rollback@42", action, attributes) -> decision

The decision names the policy id, version and the sha256 of the exact document evaluated, the rule that matched, the
obligations it imposes and the attributes it read.  That is what lets an investigator say which policy governed an
execution, not just which policy is published today.
"""

from __future__ import annotations

import tomllib

from .common import CONFIG, file_digest, short


def document(ref: str) -> tuple[dict, str]:
    pid, ver = ref.split("@")
    path = CONFIG / "policies" / f"{pid}-v{ver}.toml"
    return tomllib.loads(path.read_text()), file_digest(path)


def evaluate(ref: str, action: dict, attrs: dict, execution_id: str) -> dict:
    doc, digest = document(ref)
    evaluated = {"capability": action.get("capability"), "environment": action.get("environment"), "service": action.get("service"),
                 "agent": attrs["agent"], "severity": attrs["severity"]}
    decision, rule, obligations, reason = doc["default"]["decision"], None, {}, doc["default"]["reason"]
    for r in doc.get("rule", []):
        if (evaluated["capability"] == r["capability"] and evaluated["environment"] == r["environment"]
                and evaluated["agent"] in r["agents"] and evaluated["severity"] in r["severities"] and evaluated["service"] in r["services"]):
            decision, rule, obligations, reason = r["decision"], r["id"], dict(r.get("obligations", {})), f"matched {r['id']}"
            break
    return {"policy_evaluation_id": "pe-" + short([execution_id, ref, evaluated], 8), "policy_id": doc["id"], "policy_version": doc["version"],
            "policy_digest": digest, "decision": decision, "rule": rule, "reason": reason, "obligations": obligations,
            "attributes": evaluated}
