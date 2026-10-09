"""The simulated target systems: Kubernetes, Jira, Slack and telemetry.

Each one authenticates a credential, authorizes the principal against its own grants, applies the effect, and writes
its own audit log in its own shape.  A tool records only what it is shown: that is the point of the experiments.
"""

from __future__ import annotations

from typing import Any

from aid.config import Clock, load
from aid.contracts import ToolCredential

OBJECT = {"kubernetes": "deployments/payment-service", "jira": "INC-4102", "slack": "#inc-payments", "telemetry": "payment-service.errors"}


class Tool:
    def __init__(self, name: str, clock: Clock, grants: dict[str, set[str]]):
        self.name, self.clock, self.grants = name, clock, grants
        self.revoked_credentials: set[str] = set()
        self.disabled_principals: set[str] = set()
        self.log: list[dict[str, Any]] = []
        self.effects: list[dict[str, Any]] = []

    def _entry(self, cred: ToolCredential, verb: str, status: int) -> dict[str, Any]:
        t = self.clock.now()
        if self.name == "kubernetes":
            e = {"ts": t, "user.username": cred.principal, "verb": verb.split(":")[1], "objectRef": OBJECT[self.name],
                 "namespace": "payments", "responseStatus": status}
            if cred.impersonated_user:
                e["impersonatedUser"] = cred.impersonated_user
            return e
        if self.name == "jira":
            return {"ts": t, "actor": cred.principal, "action": verb, "issue": OBJECT[self.name], "status": status}
        if self.name == "slack":
            return {"ts": t, "bot_user": cred.principal, "action": verb, "channel": OBJECT[self.name], "status": status}
        return {"ts": t, "key": cred.principal, "action": verb, "query": OBJECT[self.name], "status": status}

    def call(self, cred: ToolCredential, verb: str, args: dict[str, Any]) -> tuple[int, str]:
        if cred.aud not in (self.name, "any"):
            return 401, f"credential audience is {cred.aud}, not {self.name}"   # rejected before it is even logged as a user
        if cred.exp <= self.clock.now() or cred.credential_id in self.revoked_credentials:
            status, why = 401, "credential expired or revoked"
        elif cred.principal in self.disabled_principals:
            status, why = 401, f"principal {cred.principal} disabled"
        elif verb not in self.grants.get(cred.principal, set()):
            status, why = 403, f"{cred.principal} may not {verb}"
        else:
            status, why = 200, "ok"
            self.effects.append({"ts": self.clock.now(), "verb": verb, "args": args, "principal": cred.principal})
        self.log.append(self._entry(cred, verb, status))
        return status, why


def build_tools(clock: Clock) -> dict[str, Tool]:
    """Every system's own grants: the tool identities, the shared account's accumulated grants, and human accounts."""
    ti, sa = load("tool_identities.yaml"), load("shared_sa.yaml")
    grants: dict[str, dict[str, set[str]]] = {s: {} for s in OBJECT}
    for ident in ti["tool_identities"].values():
        grants[ident["system"]].setdefault(ident["principal"], set()).update(ident["permissions"])
    sa_principal = shared_principals(sa)
    for g in sa["grants"]:
        grants[g["system"]].setdefault(sa_principal[g["system"]], set()).update(g["permissions"])
    for system, users in ti["human_grants"].items():
        for user, perms in users.items():
            grants[system].setdefault(user, set()).update(perms)
    return {s: Tool(s, clock, grants[s]) for s in OBJECT}


def shared_principals(sa: dict[str, Any]) -> dict[str, str]:
    return {"kubernetes": sa["principal"], "jira": sa["jira_account"], "slack": sa["slack_bot"], "telemetry": sa["telemetry_key"]}
