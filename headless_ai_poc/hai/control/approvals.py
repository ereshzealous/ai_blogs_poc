"""Approvals: a human grant bound to one exact capability call.

An approval names the digest of (capability, arguments, execution).  It is refused when the digest does not match,
the approver lacks the role or the scope, the approver is the invoker or an agent, or the request has expired.
A granted approval authorizes that one call, once; it never widens the execution's scopes.
"""

from __future__ import annotations

import json
from typing import Any

from hai.config import Clock, digest, short_id
from hai.control.identity import Directory


class Approvals:
    def __init__(self, db, directory: Directory, clock: Clock, ttl_s: float):
        self.db, self.directory, self.clock, self.ttl = db, directory, clock, ttl_s

    @staticmethod
    def call_digest(execution_id: str, capability: str, arguments: dict[str, Any]) -> str:
        return digest({"execution": execution_id, "capability": capability, "arguments": arguments})

    def request(self, execution_id: str, capability: str, arguments: dict[str, Any], required_role: str, required_scope: str | None,
                requested_by: str) -> dict[str, Any]:
        d = self.call_digest(execution_id, capability, arguments)
        existing = self.db.execute("SELECT * FROM approvals WHERE digest=?", (d,)).fetchone()
        if existing:
            return dict(existing)
        aid = short_id("apr", d)
        now = self.clock.now()
        self.db.execute("INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, execution_id, capability, json.dumps(arguments, sort_keys=True), d, required_role, required_scope,
                         requested_by, "PENDING", None, now, now + self.ttl, None))
        self.db.commit()
        return dict(self.db.execute("SELECT * FROM approvals WHERE id=?", (aid,)).fetchone())

    def get(self, aid: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM approvals WHERE id=?", (aid,)).fetchone()
        return dict(row) if row else None

    def pending_for(self, execution_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.execute("SELECT * FROM approvals WHERE execution_id=? AND status='PENDING'", (execution_id,))]

    def decide(self, aid: str, decided_by: str, approve: bool, presented_digest: str, invoker: str) -> tuple[bool, str]:
        """Returns (accepted, reason).  A refused decision changes nothing."""
        a = self.get(aid)
        if not a:
            return False, "no such approval request"
        if a["status"] != "PENDING":
            return False, f"approval is already {a['status']}"
        if self.clock.now() > a["expires"]:
            self._set(aid, "EXPIRED", None)
            return False, "approval request expired"
        if presented_digest != a["digest"]:
            return False, "digest mismatch: the decision does not match the exact call awaiting approval"
        if self.directory.kind(decided_by) != "human":
            return False, f"{decided_by} is not a human; agents and services cannot approve"
        if decided_by == invoker:
            return False, "the invoker cannot approve its own execution"
        if not self.directory.has_role(decided_by, a["required_role"]):
            return False, f"{decided_by} lacks role {a['required_role']}"
        if a["required_scope"] and not self.directory.has_scope(decided_by, a["required_scope"]):
            return False, f"{decided_by} lacks scope {a['required_scope']}"
        self._set(aid, "APPROVED" if approve else "REJECTED", decided_by)
        return True, "accepted"

    def expire_due(self) -> list[dict[str, Any]]:
        due = [dict(r) for r in self.db.execute("SELECT * FROM approvals WHERE status='PENDING' AND expires < ?", (self.clock.now(),))]
        for a in due:
            self._set(a["id"], "EXPIRED", None)
        return due

    def consume(self, aid: str) -> None:
        self._set(aid, "CONSUMED", self.get(aid)["decided_by"])

    def _set(self, aid: str, status: str, by: str | None) -> None:
        self.db.execute("UPDATE approvals SET status=?, decided_by=?, decided=? WHERE id=?", (status, by, self.clock.now(), aid))
        self.db.commit()
