"""The two objects that cross the policy boundary: an authorization request and a decision."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

ALLOW, CONSTRAINED, APPROVAL, DENY = "ALLOW", "ALLOW_WITH_CONSTRAINTS", "ALLOW_WITH_APPROVAL", "DENY"
# Our gateway's combining rule, fail-closed. An engine such as Cedar returns permit/deny plus diagnostics; the gateway
# maps those (and their obligations) onto these four enforceable execution states.
STRICTNESS = {ALLOW: 0, CONSTRAINED: 1, APPROVAL: 2, DENY: 3}


def digest(obj: Any, n: int = 12) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:n]


@dataclass(frozen=True)
class Request:
    """Can <principal>, acting for <acting_for>, perform <action> on <resource> in <environment>, given <context>?

    principal and acting_for come from the execution identity (Agent Identity, T1); action, resource, environment and
    arguments describe the proposed call. context carries only what the runtime binds to the execution: the platform
    clock and the incident id. The agent asserts nothing about itself, and the PIP ignores anything else placed in
    context or arguments (confidence, urgency, a claimed evidence score): asserted attributes can never loosen a decision.
    """

    principal: str
    acting_for: str | None
    action: str
    resource: str  # "<type>/<name>", e.g. deployment/payment-service
    environment: str
    context: dict[str, Any] = field(default_factory=dict)
    arguments: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def fingerprint(self) -> str:
        """Identifies the exact call: principal, acting-for, action, resource, environment, incident and arguments.
        An approval is bound to this (plus the policy version, decision id and expiry, see approvals.py), never to the
        agent, the session or the English intention."""
        d = self.as_dict()
        d["context"] = {k: v for k, v in d["context"].items() if k != "time"}
        return digest(d, 16)


@dataclass
class Decision:
    decision: str
    reasons: list[str]  # audit-only: precise, may name rules, attributes and relationships
    code: str  # agent-facing
    message: str  # agent-facing
    next: str | None  # agent-facing
    constraints: dict[str, Any]
    policy_version: str
    grants: list[str]  # what made the action possible at all (role, delegation, relationship)
    matched: list[str]  # which rules shaped or blocked it
    attributes: dict[str, Any]  # every attribute the decision was computed from
    decision_id: str = ""
    delegation_chain: list[dict[str, Any]] = field(default_factory=list)  # whose authority a write spent, and the record

    @property
    def reason(self) -> str:
        return "; ".join(self.reasons)

    def public(self) -> dict[str, Any]:
        """What the agent is told: enough to act on, and only what the caller is allowed to learn.
        No rule ids, no attributes, no relationship paths, no policy internals."""
        out = {"decision": self.decision, "code": self.code, "reason": self.message}
        if self.next:
            out["next"] = self.next
        if self.constraints:
            out["constraints"] = self.constraints
        return out
