"""Approval bound to one exact invocation.

An approval stores the digest of the canonical invocation (implementation, bound
arguments, environment, requester, agent, request id, policy version).  The gateway
recomputes the digest at execution time; if any of those changed, the approval does
not apply.  Approvals are single-use.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..util import new_id
from .invocation import Invocation


@dataclass
class ApprovalRecord:
    approval_id: str
    digest: str
    invocation: dict[str, Any]
    policy_version: str
    reason: str
    status: str = "pending"  # pending | approved | rejected | consumed
    approver: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    def as_record(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "digest": self.digest,
            "invocation": self.invocation,
            "policy_version": self.policy_version,
            "reason": self.reason,
            "status": self.status,
            "approver": self.approver,
            "history": self.history,
        }


class ApprovalError(Exception):
    pass


class ApprovalService:
    """In-process simulated approval service (the approver is simulated; the binding is real)."""

    def __init__(self, id_prefix: str | None = None) -> None:
        self._by_id: dict[str, ApprovalRecord] = {}
        self._prefix = id_prefix  # deterministic ids (per benchmark row) keep recorded runs exactly replayable

    def request(self, inv: Invocation, policy_version: str, reason: str) -> ApprovalRecord:
        digest = inv.digest(policy_version)
        for rec in self._by_id.values():  # idempotent: the same pending invocation reuses its request
            if rec.digest == digest and rec.status == "pending":
                return rec
        aid = f"APR-{self._prefix}-{len(self._by_id) + 1}" if self._prefix else new_id("APR")
        rec = ApprovalRecord(aid, digest, inv.canonical(), policy_version, reason)
        rec.history.append({"ts": time.time(), "event": "requested"})
        self._by_id[rec.approval_id] = rec
        return rec

    def decide(self, approval_id: str, approver: str, approve: bool) -> ApprovalRecord:
        rec = self._get(approval_id)
        if rec.status != "pending":
            raise ApprovalError(f"approval {approval_id} is {rec.status}")
        if approver == rec.invocation.get("requester_id"):
            raise ApprovalError("requester cannot approve their own invocation")
        rec.status = "approved" if approve else "rejected"
        rec.approver = approver
        rec.history.append({"ts": time.time(), "event": rec.status, "approver": approver})
        return rec

    def check(self, approval_id: str | None, inv: Invocation, policy_version: str) -> tuple[bool, str]:
        """Does ``approval_id`` authorise exactly this invocation right now?"""
        if not approval_id:
            return False, "no approval presented"
        rec = self._by_id.get(approval_id)
        if rec is None:
            return False, "unknown approval"
        if rec.status != "approved":
            return False, f"approval is {rec.status}"
        if rec.digest != inv.digest(policy_version):
            return False, "approval digest does not match this invocation"
        return True, "approved invocation"

    def find_approved(self, digest: str) -> ApprovalRecord | None:
        return next((r for r in self._by_id.values() if r.digest == digest and r.status == "approved"), None)

    def find_rejected(self, digest: str) -> ApprovalRecord | None:
        return next((r for r in self._by_id.values() if r.digest == digest and r.status == "rejected"), None)

    def pending(self) -> list[ApprovalRecord]:
        return [r for r in self._by_id.values() if r.status == "pending"]

    def consume(self, approval_id: str) -> None:
        rec = self._get(approval_id)
        rec.status = "consumed"
        rec.history.append({"ts": time.time(), "event": "consumed"})

    def get(self, approval_id: str) -> ApprovalRecord | None:
        return self._by_id.get(approval_id)

    def all(self) -> list[ApprovalRecord]:
        return list(self._by_id.values())

    def _get(self, approval_id: str) -> ApprovalRecord:
        rec = self._by_id.get(approval_id)
        if rec is None:
            raise ApprovalError(f"unknown approval {approval_id}")
        return rec
