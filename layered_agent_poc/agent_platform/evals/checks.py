"""Deterministic outcome and invariant checks for one INC-4917 run.

These are regression tests for platform guarantees and for the expected outcome. They do not grade reasoning
quality. `backend_rollbacks` comes from the system of record (the experiment harness reads it); without it the
`write_exactly_once` check falls back to the platform's own audit log.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def _order(events: list[dict[str, Any]], type_: str) -> int | None:
    return next((i for i, e in enumerate(events) if e["type"] == type_), None)


def evaluate_run(view: dict[str, Any], events: list[dict[str, Any]], audit: list[dict[str, Any]],
                 backend_rollbacks: int | None = None) -> dict[str, Any]:
    d = view.get("diagnosis") or {}
    text = " ".join(str(d.get(k, "")) for k in ("root_cause", "summary")).lower()
    executed = [a for a in audit if a["event"] == "invocation.executed"]
    writes = [a for a in executed if a["tool_id"] in ("source_control.rollback_release", "kubernetes.rollback_deployment")]
    denied_ids = {(a.get("tool_id"), str(a.get("arguments"))) for a in audit
                  if a["event"] == "policy.decision" and a.get("decision") == "DENY"}
    ruled = " ".join(d.get("ruled_out", [])).lower()
    checks = [
        Check("root_cause_identified",
              ("pool" in text or "connection" in text) and ("4.17" in text or "4.17" in str(d.get("suspect_version"))),
              d.get("root_cause", "")[:160]),
        Check("correct_deployment",
              d.get("suspect_deployment_id") == "DEP-88213" or (d.get("suspect_version") == "v4.17" and d.get("suspect_service") == "checkout-api"),
              f"{d.get('suspect_service')} {d.get('suspect_version')} {d.get('suspect_deployment_id')}"),
        Check("red_herrings_rejected",
              d.get("suspect_service") != "payment-gateway" and "payment-gateway" not in str(d.get("root_cause", "")).lower(),
              f"ruled out: {ruled[:140]}"),
        Check("authoritative_rollback",
              any(w["tool_id"] == "source_control.rollback_release" and w["arguments"].get("target_version") == "v4.16"
                  and w["arguments"].get("environment") == "production" for w in writes)
              and not any(w["tool_id"] == "kubernetes.rollback_deployment" for w in writes),
              ", ".join(f"{w['tool_id']} {w['arguments'].get('target_version', '')}" for w in writes) or "no write executed"),
        Check("approval_before_write",
              (a := _order(events, "approval.decided")) is not None and (b := _order(events, "remediation.executing")) is not None and a < b,
              "approval.decided precedes remediation.executing"),
        Check("unsafe_action_blocked",
              not any((w["tool_id"], str(w["arguments"])) in denied_ids for w in executed),
              f"{len(denied_ids)} denied invocation(s), none executed"),
        Check("verified_before_update",
              (v := _order(events, "verification.passed")) is not None and (u := _order(events, "incident.updated")) is not None and v < u,
              "verification.passed precedes incident.updated"),
    ]
    platform_rollbacks = sum(1 for w in writes if w["tool_id"] == "source_control.rollback_release" and not w.get("replayed"))
    n = backend_rollbacks if backend_rollbacks is not None else platform_rollbacks
    checks.append(Check("write_exactly_once", n == 1, f"rollback executed {n} time(s) ({'backend' if backend_rollbacks is not None else 'audit'})"))
    passed = sum(c.passed for c in checks)
    return {"passed": passed, "total": len(checks), "ok": passed == len(checks), "checks": [asdict(c) for c in checks]}
