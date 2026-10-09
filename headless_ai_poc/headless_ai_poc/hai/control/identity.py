"""Identity: authenticate a head's credential, then exchange it for a short-lived execution identity.

The exchange is the point of the module.  The execution's scopes are the intersection of what the invoker may
delegate and what the agent may ever do.  No step adds authority.  An approval adds it for one call only (see
approvals.py).  Modelled on OAuth 2.0 Token Exchange (RFC 8693) semantics: subject = the invoker or the human it
acts for, actor = the agent, running as the runtime workload.  This is a simulation, not an implementation of the RFC.
"""

from __future__ import annotations

from typing import Any

from hai.config import Clock, load, short_id
from hai.contracts import ExecutionIdentity

INTENT_SCOPE = {"investigate_incident": "incident:investigate", "health_sweep": "health:sweep", "release_check": "release:check"}
RUNTIME_WORKLOAD = "svc.hai-runtime"


class AuthError(Exception):
    pass


class Directory:
    def __init__(self, clock: Clock):
        cfg = load("principals.yaml")
        self.principals: dict[str, dict[str, Any]] = cfg["principals"]
        self.credentials: dict[str, dict[str, str]] = cfg["credentials"]
        self.ttl = float(cfg["token_ttl_s"])
        self.clock = clock
        self.revoked: set[str] = set()

    # ---- ingress ------------------------------------------------------------------------------------------------------
    def authenticate(self, credential: str, channel: str) -> str:
        c = self.credentials.get(credential)
        if not c or credential in self.revoked:
            raise AuthError("unknown or revoked credential")
        if c["channel"] != channel:
            raise AuthError(f"credential is bound to channel {c['channel']}, presented on {channel}")
        return c["principal"]

    def may_invoke(self, principal: str, intent: str) -> bool:
        """Invocation authority: may this principal START this kind of execution?  Says nothing about actions."""
        return INTENT_SCOPE[intent] in self.principals[principal]["scopes"]

    # ---- execution identity ----------------------------------------------------------------------------------------
    def exchange(self, invoker: str, on_behalf_of: str | None, agent: str, execution_id: str) -> ExecutionIdentity:
        subject = on_behalf_of or invoker
        delegable = set(self.principals[subject]["delegable"])
        if on_behalf_of:  # a human acting through a head: the head's workload must also be allowed to pass it on
            delegable &= set(self.principals[invoker]["delegable"])
        agent_p = self.principals[agent]
        scopes = sorted(delegable & set(agent_p["scopes"]))
        now = self.clock.now()
        return ExecutionIdentity(invoker=invoker, on_behalf_of=on_behalf_of, agent=f"{agent}@{agent_p.get('version', '0')}",
                                 workload=RUNTIME_WORKLOAD, scopes=scopes, token_id=short_id("tok", execution_id, now),
                                 issued_at=now, expires_at=now + self.ttl)

    def valid(self, ident: ExecutionIdentity) -> bool:
        return self.clock.now() < ident.expires_at and ident.token_id not in self.revoked

    def refresh(self, ident: ExecutionIdentity, execution_id: str) -> ExecutionIdentity:
        """Re-exchange after a pause.  Scopes are recomputed from the directory, so a revoked delegation stays revoked."""
        return self.exchange(ident.invoker, ident.on_behalf_of, ident.agent.split("@")[0], execution_id)

    def has_role(self, principal: str, role: str) -> bool:
        return role in self.principals.get(principal, {}).get("roles", [])

    def has_scope(self, principal: str, scope: str) -> bool:
        return scope in self.principals.get(principal, {}).get("scopes", [])

    def kind(self, principal: str) -> str:
        return self.principals.get(principal, {}).get("kind", "unknown")
