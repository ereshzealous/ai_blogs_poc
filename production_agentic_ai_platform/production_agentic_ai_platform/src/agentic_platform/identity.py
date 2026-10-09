"""Identity: the user, the agent, the workload, and the delegation between them.  Effective authority is an intersection.

    effective = user ∩ agent ceiling ∩ delegated scope ∩ workload ∩ environment policy

and a tool call additionally needs its own required permission to be in that set.  Grants are operation:service:environment
patterns with `*`; they are expanded over the control plane's universe so that intersection is plain set intersection
and every decision can show exactly which layer removed what.

The workload identity document is a simulated SPIFFE-style attestation (an HMAC-signed statement from the runtime
attestor), not a SPIRE deployment.  Users are asserted by the request boundary as an IdP would assert them.
"""

from __future__ import annotations

import fnmatch
import hashlib
import hmac
import time
from dataclasses import dataclass, field
from typing import Any

from agentic_platform.canonical import canonical_json
from agentic_platform.control_plane import Bundle


class IdentityError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def expand(patterns: list[str], universe: dict[str, list[str]]) -> set[str]:
    out = set()
    for op in universe["operations"]:
        for svc in universe["services"]:
            for env in universe["environments"]:
                p = f"{op}:{svc}:{env}"
                if any(fnmatch.fnmatchcase(p, pat) for pat in patterns):
                    out.add(p)
    return out


@dataclass
class User:
    id: str
    tenant: str
    groups: list[str]
    clearance: str
    roles: list[str]
    permissions: set[str]


@dataclass
class Workload:
    id: str
    environment: str
    permissions: set[str]
    document: dict[str, Any]


@dataclass
class Delegation:
    id: str
    user: str
    agent: str
    incident: str
    scope: set[str]
    issued_at: float
    expires_at: float
    requested: set[str] = field(default_factory=set)

    def valid(self, now: float | None = None) -> bool:
        return (now or time.time()) < self.expires_at


class IdentityService:
    def __init__(self, bundle: Bundle, attestor_key: bytes):
        self.b, self.key = bundle, attestor_key
        self.universe = bundle.doc["identity"]["universe"]

    def user(self, user_id: str) -> User:
        u = self.b.doc["identity"]["users"].get(user_id)
        if not u:
            raise IdentityError("UNKNOWN_USER", user_id)
        return User(user_id, u["tenant"], u["groups"], u["clearance"], u["roles"], expand(u["permissions"], self.universe))

    def agent_ceiling(self, agent_id: str) -> set[str]:
        return expand(self.b.agent(agent_id)["permissions"], self.universe)

    def attest_workload(self, workload_id: str) -> Workload:
        w = self.b.doc["identity"]["workloads"].get(workload_id)
        if not w:
            raise IdentityError("WORKLOAD_NOT_ATTESTED", workload_id)
        doc = {"spiffe_id": workload_id, "environment": w["environment"], "attested_by": w["attested_by"], "iat": int(time.time()),
               "exp": int(time.time()) + 3600}
        doc["sig"] = hmac.new(self.key, canonical_json(doc).encode(), hashlib.sha256).hexdigest()
        return Workload(workload_id, w["environment"], expand(w["permissions"], self.universe), doc)

    def delegate(self, user: User, agent_id: str, incident: dict[str, Any], delegation_id: str) -> Delegation:
        """The user hands the agent a narrow, expiring scope for one incident.  It can never exceed what the user holds."""
        a = self.b.agent(agent_id)
        requested = expand([t.format(service=incident["service"], environment=incident["environment"]) for t in a["delegation_template"]], self.universe)
        now = time.time()
        return Delegation(delegation_id, user.id, agent_id, incident["id"], requested & user.permissions, now, now + a["delegation_ttl_s"], requested)

    def environment_allowed(self) -> set[str]:
        envs = self.b.policy["environments"]
        pats = [f"{op}:*:{env}" for env, e in envs.items() for op in e["allowed_operations"]]
        return expand(pats, self.universe)

    def effective(self, user: User, agent_id: str, delegation: Delegation, workload: Workload) -> dict[str, Any]:
        layers = {"user": user.permissions, "agent": self.agent_ceiling(agent_id), "delegation": delegation.scope,
                  "workload": workload.permissions, "environment": self.environment_allowed()}
        eff = set.intersection(*layers.values())
        return {"layers": {k: sorted(v) for k, v in layers.items()}, "effective": sorted(eff),
                "sizes": {k: len(v) for k, v in layers.items()} | {"effective": len(eff)}}

    @staticmethod
    def removed_by(layers: dict[str, list[str]], permission: str) -> list[str]:
        """Which layers do not grant `permission` (the explanation for a DENY)."""
        return [k for k, v in layers.items() if permission not in v]
