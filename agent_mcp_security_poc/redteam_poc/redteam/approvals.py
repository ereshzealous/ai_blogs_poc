"""The approval service (Human-in-the-Loop, T3). An approval EXISTS only as a record here, bound to the action digest and
to an eligible human. It is never parsed from content: a fake approval reference in an email, a tool result or a peer
message resolves to nothing (I-APPROVAL).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from redteam.base import Decision, GateEvent


@dataclass
class Approval:
    approval_id: str
    action_digest: str
    approver: str


@dataclass
class ApprovalService:
    principals: dict
    _records: dict[str, Approval] = field(default_factory=dict)

    def grant(self, approval_id: str, action_digest: str, approver: str) -> Approval:
        """A real approval: an eligible human decides about an exact action. Used by the legitimate escalation (OK-2)."""
        a = Approval(approval_id, action_digest, approver)
        self._records[action_digest] = a
        return a

    def check(self, action_digest: str, required_role: str, requester_chain: set[str]) -> GateEvent:
        rec = self._records.get(action_digest)
        if rec is None:
            return GateEvent("approval", Decision.REQUIRE_APPROVAL,
                             "no approval record bound to this action digest (a claimed approval is not a record)")
        p = self.principals.get(rec.approver, {})
        if required_role not in p.get("roles", []):
            return GateEvent("approval", Decision.DENY, "approver lacks the required role",
                             {"approver": rec.approver})
        if rec.approver in requester_chain:
            return GateEvent("approval", Decision.DENY, "separation of duties: approver is in the request chain",
                             {"approver": rec.approver})
        return GateEvent("approval", Decision.ALLOW, "approval record bound to this exact action",
                         {"approval_id": rec.approval_id, "approver": rec.approver})
