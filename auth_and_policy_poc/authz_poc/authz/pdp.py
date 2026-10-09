"""Policy decision point: one function, three layers, one decision.

    0. Default    unknown principal, action, resource or environment → DENY; writes need known incident context
    1. RBAC       does any role the agent holds normally permit this action?          (deny by default)
    2. ReBAC      for writes: whose authority is borrowed, is it delegated, does that principal own the resource?
    3. ABAC       given the context, do any guard rules deny, require approval, or add constraints?

The PDP decides. It never executes, never asks a human, and never trusts the agent to enforce anything.
In production, stage 2 is typically a relationship graph (Zanzibar-style: OpenFGA, SpiceDB) and stages 1 and 3 a
policy evaluator (Cedar, OPA). They answer different parts of the question; this POC keeps both in one small file.
"""

from __future__ import annotations

from typing import Any

from .model import ALLOW, DENY, STRICTNESS, Decision, Request, digest
from .pip import PIP, load, ts

OPS = {
    "lt": lambda a, b: a < b,
    "gte": lambda a, b: a >= b,
    "ne": lambda a, b: a != b,
    "not_in": lambda a, b: a not in b,
}

# Built-in denials: (audit reason template, agent-facing code, message, next step)
BUILTIN = {
    "default.unknown-principal": ("{principal} is not a registered principal", "UNKNOWN_PRINCIPAL",
                                  "This caller is not recognised", None),
    "default.unknown-action": ("{action} is not in the action catalog", "UNKNOWN_ACTION",
                               "This action is not recognised", None),
    "default.unknown-resource": ("{resource} is not in the resource catalog", "UNKNOWN_RESOURCE",
                                 "This resource is not recognised", None),
    "default.unknown-environment": ("Environment '{environment}' is not in the catalog", "UNKNOWN_ENVIRONMENT",
                                    "This environment is not recognised", None),
    "default.unknown-incident-context": ("Writes need a known incident severity; the incident system returned none",
                                         "CONTEXT_UNAVAILABLE", "Required incident context is unavailable",
                                         "Retry when the incident record is available"),
    "rbac.no-grant": ("No role held by {principal} grants {action}", "ACTION_NOT_PERMITTED",
                      "This action is not permitted for this agent", "Escalate to a human operator"),
    "rebac.no-principal": ("Writes need an acting-for principal; the agent has no write authority of its own",
                           "NO_ACTING_PRINCIPAL", "Writes need a principal to act for", "Invoke on behalf of an owner"),
    "rebac.not-delegated": ("{acting_for} has not delegated {action} to {principal}", "NO_DELEGATED_AUTHORITY",
                            "No delegated authority covers this action on this resource", "Escalate to the owning team"),
    "rebac.not-owner": ("{acting_for} does not own {service}, so it cannot lend authority over it", "NO_DELEGATED_AUTHORITY",
                        "No delegated authority covers this action on this resource", "Escalate to the owning team"),
    "rebac.delegation-inactive": ("Delegation {delegation} applies only while an incident on {service} is open",
                                  "DELEGATION_INACTIVE", "Delegated authority is not active for this resource now", None),
}


def condition_holds(key: str, expected: Any, attrs: dict[str, Any]) -> bool:
    name, _, op = key.partition(".")
    if name not in attrs:  # unknown context fails closed: the restrictive rule applies
        return True
    actual = attrs[name]
    if op:
        return OPS[op](actual, expected)
    return actual in expected if isinstance(expected, list) else actual == expected


def rule_matches(rule: dict[str, Any], attrs: dict[str, Any]) -> bool:
    return all(condition_holds(k, v, attrs) for k, v in rule["when"].items())


class PDP:
    def __init__(self, pip: PIP, policy: dict[str, Any] | None = None):
        self.pip = pip
        self.policy = policy or load("policy")

    def evaluate(self, req: Request) -> Decision:
        attrs = self.pip.attributes(req)
        now = ts(req.context["time"])
        denials: list[tuple[str, str, str, str, str | None]] = []  # (id, audit reason, code, message, next)
        grants: list[str] = []
        fmt = {"action": req.action, "principal": req.principal, "acting_for": req.acting_for, "resource": req.resource,
               "environment": req.environment, "service": attrs.get("service"), "delegation": ""}
        chain: list[dict[str, Any]] = []

        def builtin(rid: str, **extra):
            reason, code, msg, nxt = BUILTIN[rid]
            denials.append((rid, reason.format(**{**fmt, **extra}), code, msg, nxt))

        # 0. Deny by default: an unknown principal, action, resource or environment is never allowed, and a write
        #    is never decided without the incident context it depends on.
        if not self.pip.principal_known(req.principal):
            builtin("default.unknown-principal")
        if "kind" not in attrs:
            builtin("default.unknown-action")
        if not self.pip.resource_known(req.resource):
            builtin("default.unknown-resource")
        if not self.pip.environment_known(req.environment):
            builtin("default.unknown-environment")
        if attrs.get("kind") in ("write", "destructive") and not self.pip.severity_known(attrs.get("severity")):
            builtin("default.unknown-incident-context")

        # 1. RBAC: what the role normally permits.
        roles = [r for r in attrs["principal.roles"] if req.action in self.pip.role_actions(r)]
        if roles:
            grants.append(f"role:{roles[0]}")
        else:
            builtin("rbac.no-grant")

        # 2. ReBAC + delegation: whose authority does a write spend?
        if attrs.get("kind") in ("write", "destructive"):
            self._delegated_authority(req, attrs, now, grants, chain, builtin)

        # 3. ABAC guard rules: context narrows what 1 and 2 allowed.
        effect, shaping, constraints, matched = ALLOW, [], {}, []
        for rule in self.policy["rule"]:
            if not rule_matches(rule, attrs):
                continue
            matched.append(rule["id"])
            if rule["effect"] == DENY:
                denials.append((rule["id"], rule["reason"], rule["code"], rule["message"], rule.get("next")))
                continue
            constraints.update(rule.get("constraints", {}))
            shaping.append(rule)
            if STRICTNESS[rule["effect"]] > STRICTNESS[effect]:
                effect = rule["effect"]

        if denials:
            first = denials[0]
            d = Decision(DENY, [r for _, r, *_ in denials], first[2], first[3], first[4], {}, self.policy["version"],
                         grants, [i for i, *_ in denials], attrs)
        elif shaping:
            top = max(shaping, key=lambda r: STRICTNESS[r["effect"]])
            d = Decision(effect, [r["reason"] for r in shaping], top["code"], top["message"], top.get("next"),
                         constraints, self.policy["version"], grants, matched, attrs)
        else:
            d = Decision(ALLOW, [f"{grants[0].split(':', 1)[1]} permits {req.action}"], "OK", "Permitted", None, {},
                         self.policy["version"], grants, matched, attrs)
        d.decision_id = "dec-" + digest([req.as_dict(), d.decision, d.matched], 10)
        d.delegation_chain = chain if d.decision != DENY else []
        return d

    def _delegated_authority(self, req: Request, attrs: dict, now, grants: list[str], chain: list, builtin) -> None:
        if not req.acting_for:
            return builtin("rebac.no-principal")
        dlg = self.pip.delegation(req.acting_for, req.principal, req.action, now)
        if dlg is None:
            return builtin("rebac.not-delegated")
        if not self.pip.related(req.acting_for, "owns", f"service:{attrs['service']}"):
            return builtin("rebac.not-owner")
        if attrs.get("incident_state") not in dlg["while_incident_state"] or attrs.get("incident_service") != attrs["service"]:
            return builtin("rebac.delegation-inactive", delegation=dlg["id"])
        grants += [f"delegation:{dlg['id']}", f"relation:{req.acting_for} owns {attrs['service']}"]
        chain.append({"from": req.acting_for, "to": req.principal, "delegation": dlg["id"], "granted_by": dlg["granted_by"],
                      "actions": dlg["actions"], "expires": dlg["expires"],
                      "relation": f"{req.acting_for} owns service:{attrs['service']}"})
