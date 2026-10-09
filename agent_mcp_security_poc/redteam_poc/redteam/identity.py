"""The identity & delegation service (Agent Identity, T1). It answers 'who is acting, and on whose authority?' from
verified state — never from a claim in content or a peer message.

Key property for T6: a peer agent's text, and a delegation token the peer merely names, create NO authority. A token is
honoured only if the identity service actually issued it (config/principals.yaml `peer_tokens`).
"""
from __future__ import annotations

from dataclasses import dataclass

from redteam.base import GateEvent, Decision, load_yaml


@dataclass
class Context:
    """The verified actor chain behind a proposal. Built from credentials, not from the model's output."""
    human: str               # the principal the agent represents (subject of the delegation)
    agent: str
    runtime: str
    delegation: str
    resource: str
    scopes: list[str]

    def limit(self, kind: str, principals: dict) -> float:
        return float(principals[self.human].get(kind, 0.0))


class Identity:
    def __init__(self) -> None:
        cfg = load_yaml("principals.yaml")
        self.principals = cfg["principals"]
        self.creds = cfg["credentials"]
        self.runtimes = cfg["runtimes"]
        self.delegations = cfg["delegations"]
        self.peer_tokens = cfg.get("peer_tokens") or {}

    def context_for_case(self, delegation_id: str) -> Context:
        d = self.delegations[delegation_id]
        return Context(human=d["subject"], agent=d["actor"], runtime="svc.agent-runtime",
                       delegation=delegation_id, resource=d["resource"], scopes=list(d["scopes"]))

    def verify_delegation_active(self, ctx: Context) -> bool:
        d = self.delegations.get(ctx.delegation)
        return bool(d and d.get("status") == "active")

    def verify_peer_claim(self, claimed_delegation: str | None) -> GateEvent:
        """A peer agent asserts authority. Accept ONLY a delegation the identity service issued. Text is not a token."""
        if claimed_delegation and claimed_delegation in self.peer_tokens:
            return GateEvent("identity", Decision.ALLOW, "peer delegation verified against identity service",
                             {"delegation": claimed_delegation})
        return GateEvent("identity", Decision.DENY,
                         "peer-asserted authority not backed by an issued delegation (message text is not a token)",
                         {"claimed": claimed_delegation or "none"})
