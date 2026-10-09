"""The directory: humans, workloads, runtimes and agents as principals, and every revocation lever the platform has.

Ingress authentication lives here too: a credential resolves to a principal and is bound to one channel.  The payload
never names its own invoker.
"""

from __future__ import annotations

from typing import Any

from aid.config import load


class AuthError(Exception):
    pass


class Directory:
    def __init__(self):
        cfg = load("principals.yaml")
        self.humans: dict[str, dict[str, Any]] = cfg["humans"]
        self.workloads: dict[str, dict[str, Any]] = cfg["workloads"]
        self.runtimes: dict[str, dict[str, Any]] = cfg["runtimes"]
        self.agents: dict[str, dict[str, Any]] = cfg["agents"]
        self.credentials: dict[str, dict[str, str]] = cfg["credentials"]
        self.non_delegable = set(cfg["non_delegable"])
        self.ttl = float(cfg["token_ttl_s"])
        self.max_depth = int(cfg["max_delegation_depth"])
        # revocation state: one lever per layer
        self.revoked_credentials: set[str] = set()
        self.revoked_grants: set[str] = set()          # a human's delegation to executions
        self.disabled_agents: set[str] = set()         # agent@version

    # ---- ingress ------------------------------------------------------------------------------------------------------
    def authenticate(self, credential: str, channel: str) -> str:
        c = self.credentials.get(credential)
        if not c or credential in self.revoked_credentials:
            raise AuthError("unknown or revoked credential")
        if c["channel"] != channel:
            raise AuthError(f"credential is bound to channel {c['channel']}, presented on {channel}")
        return c["principal"]

    def may_invoke(self, principal: str, scope: str) -> bool:
        return scope in self.workloads.get(principal, {}).get("scopes", [])

    # ---- lookups ------------------------------------------------------------------------------------------------------
    def kind(self, p: str) -> str:
        for k, table in (("human", self.humans), ("workload", self.workloads), ("runtime", self.runtimes), ("agent", self.agents)):
            if p in table:
                return k
        return "unknown"

    def delegable(self, p: str) -> set[str]:
        table = self.humans if p in self.humans else self.workloads
        return set(table.get(p, {}).get("delegable", [])) - self.non_delegable

    def ceiling(self, agent: str) -> set[str]:
        return set(self.agents[agent]["ceiling"]) - self.non_delegable

    def agent_ref(self, agent: str) -> str:
        return f"{agent}@{self.agents[agent]['version']}"

    def spiffe(self, runtime: str) -> str:
        return self.runtimes[runtime]["spiffe"]

    def has_role(self, p: str, role: str) -> bool:
        return role in self.humans.get(p, {}).get("roles", [])

    def holds(self, p: str, scope: str) -> bool:
        return scope in self.humans.get(p, {}).get("scopes", [])

    def oidc(self, p: str) -> str | None:
        return self.humans.get(p, {}).get("oidc")

    def agent_enabled(self, ref: str) -> bool:
        return ref not in self.disabled_agents
