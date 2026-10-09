"""Deterministic action policy: ALLOW, DENY or REQUIRE_APPROVAL, computed as code from a structured input.

The input names the user, agent, workload, tenant, environment, capability (with its registry facts: enabled, trust,
lifecycle), operation, arguments, delegation, effective authority, risk, budget state and authoritative context (the
release history, read from the release system, never from the model).  The rules are evaluated in order; the first DENY
stops evaluation; otherwise the strictest outcome wins.  Unknown or missing input fails closed.

A custom engine keeps the POC dependency-free, as in T2 and T4.  The same input document is what you would send to OPA or
Cedar; nothing here depends on the engine being in-process.
"""

from __future__ import annotations

from typing import Any

from agentic_platform.canonical import canonical_json, sha256
from agentic_platform.control_plane import Bundle

LEVEL = {"low": 0, "medium": 1, "high": 2}


def classify_risk(bundle: Bundle, cap: dict[str, Any] | None, environment: str, service_tier: int | None) -> dict[str, Any]:
    r = bundle.policy["risk"]
    parts = {"tool": (cap or {}).get("risk", "high"), "environment": r["environment_floor"].get(environment, "high"),
             "tier": r["tier_floor"].get(service_tier, "high") if service_tier else "low"}
    level = max(parts.values(), key=lambda v: LEVEL[v])
    if (cap or {}).get("side_effect") == "read":
        level = "low"   # reads carry data risk, handled by context policy; they are not consequential actions
    return {"level": level, "parts": parts}


def evaluate(bundle: Bundle, inp: dict[str, Any]) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []

    def rule(rid: str, ok: bool, code: str, detail: str = "", outcome: str = "DENY") -> bool:
        rules.append({"rule": rid, "passed": ok, "code": None if ok else code, "detail": detail if not ok else ""})
        if not ok and outcome == "DENY":
            raise _Deny(code, detail)
        return ok

    decision, code, reasons = "ALLOW", "ALLOWED", []
    try:
        cap = inp.get("capability")
        rule("P01-registered", cap is not None, "CAPABILITY_NOT_REGISTERED", f"{inp.get('capability_name')} is not in the capability registry")
        rule("P02-trusted", cap.get("trust") == "trusted", "TOOL_UNTRUSTED", f"trust state {cap.get('trust')!r}, owner {cap.get('owner')!r}")
        rule("P03-lifecycle", cap.get("lifecycle") == "active", "TOOL_LIFECYCLE", f"lifecycle {cap.get('lifecycle')!r}")
        rule("P04-enabled", cap.get("enabled") is True, "CAPABILITY_DISABLED", f"{inp['capability_name']} disabled by the control plane ({inp['bundle_version']})")
        rule("P05-agent-allowlist", inp["capability_name"] in inp["agent"]["capabilities"], "CAPABILITY_NOT_ALLOWED_FOR_AGENT",
             f"{inp['agent']['id']} is not registered for {inp['capability_name']}")
        rule("P06-agent-lifecycle", inp["agent"]["lifecycle"] == "active", "AGENT_SUSPENDED", inp["agent"]["lifecycle"])
        rule("P07-environment", inp["environment"] in cap.get("environments", []), "ENVIRONMENT_NOT_PERMITTED", inp["environment"])
        rule("P08-tenant", inp["tenant"] == inp["resource_tenant"], "TENANT_MISMATCH", f"request tenant {inp['tenant']}, resource tenant {inp['resource_tenant']}")
        rule("P09-delegation", bool(inp["delegation"]["valid"]) and inp["delegation"]["incident"] == inp["incident"], "DELEGATION_INVALID",
             "delegation expired or issued for another incident")
        perm = inp["required_permission"]
        rule("P10-effective-authority", perm in inp["effective_authority"], "OUTSIDE_EFFECTIVE_AUTHORITY",
             f"{perm} not granted by: {', '.join(inp['removed_by']) or '?'}")
        rule("P11-budget", not inp["budget"]["exhausted"], "BUDGET_EXCEEDED", inp["budget"].get("limit_hit") or "")
        if cap.get("validate") == "previous_release":
            dep = inp.get("authoritative_context", {}).get("deployment")
            tv = inp["arguments"].get("target_version")
            # Must be a release that shipped before the latest deployment: an earlier release, not the one under incident.
            ok = bool(dep) and tv in [h["version"] for h in dep["history"][:-1]]
            rule("P12-arguments", ok, "ARGUMENT_INVALID", f"target_version {tv!r} is not an earlier release of {inp['arguments'].get('service')}")
        risk = inp["risk"]["level"]
        env = bundle.policy["environments"][inp["environment"]]
        if cap.get("side_effect") == "write" and (env["agent_writes_need_approval"] or risk == "high"):
            rule("P13-approval", False, "APPROVAL_REQUIRED", f"{risk}-risk write in {inp['environment']}", outcome="REQUIRE_APPROVAL")
            decision, code = "REQUIRE_APPROVAL", "APPROVAL_REQUIRED"
            reasons.append(f"{risk}-risk write in {inp['environment']} requires {bundle.policy['approval']['approver_role']} approval")
        else:
            rules.append({"rule": "P13-approval", "passed": True, "code": None, "detail": ""})
    except _Deny as d:
        decision, code, reasons = "DENY", d.code, [d.detail]
    except (KeyError, TypeError, AttributeError) as exc:   # malformed or missing input
        decision, code, reasons = "DENY", "POLICY_INPUT_INVALID", [f"fail closed: {type(exc).__name__}: {exc}"]
    return {"decision_id": "pd-" + sha256(canonical_json(inp))[:12], "decision": decision, "code": code, "reasons": reasons, "rules": rules,
            "policy_version": bundle.policy_version, "bundle_version": bundle.version, "bundle_digest": bundle.digest,
            "input_digest": sha256(canonical_json(inp))}


class _Deny(Exception):
    def __init__(self, code: str, detail: str):
        self.code, self.detail = code, detail
