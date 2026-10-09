"""Approval records, bound to the exact action.

An approval covers one capability with one set of arguments in one workflow: its digest is sha256 of those three.
A grant is valid only if it is APPROVED, its digest matches the action being executed, the approver holds the
required role, and the approver is not the person who asked for the work (separation of duties).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from typing import Any

from layered_platform.policy.identity import Directory


def digest(workflow_id: str, capability: str, args: dict[str, Any]) -> str:
    return hashlib.sha256(f"{workflow_id}|{capability}|{json.dumps(args, sort_keys=True)}".encode()).hexdigest()


class ApprovalError(PermissionError):
    pass


class Approvals:
    def __init__(self, db: sqlite3.Connection, directory: Directory):
        self.db, self.directory = db, directory

    def request(self, workflow_id: str, capability: str, args: dict[str, Any], requested_by: str, required_role: str) -> dict[str, Any]:
        d = digest(workflow_id, capability, args)
        row = self.db.execute("SELECT * FROM approvals WHERE digest=? AND status='PENDING'", (d,)).fetchone()
        if row:
            return dict(row)
        aid = "apr-" + uuid.uuid5(uuid.NAMESPACE_URL, d).hex[:10]
        self.db.execute("INSERT OR IGNORE INTO approvals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, workflow_id, capability, json.dumps(args, sort_keys=True), d, requested_by, required_role, "PENDING", None, "", time.time(), None))
        return dict(self.db.execute("SELECT * FROM approvals WHERE id=?", (aid,)).fetchone())

    def pending(self, workflow_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM approvals WHERE workflow_id=? AND status='PENDING' ORDER BY created DESC", (workflow_id,)).fetchone()
        return dict(row) if row else None

    def get(self, approval_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
        return dict(row) if row else None

    def decide(self, approval_id: str, decided_by: str, approve: bool, reason: str = "") -> dict[str, Any]:
        rec = self.get(approval_id)
        if not rec:
            raise ApprovalError(f"no approval {approval_id}")
        if rec["status"] != "PENDING":
            return rec
        if rec["required_role"] not in self.directory.roles(decided_by):
            raise ApprovalError(f"{decided_by} does not hold {rec['required_role']}")
        if decided_by == rec["requested_by"]:
            raise ApprovalError("separation of duties: the requester cannot approve their own request")
        self.db.execute("UPDATE approvals SET status=?, decided_by=?, reason=?, decided=? WHERE id=?",
                        ("APPROVED" if approve else "REJECTED", decided_by, reason, time.time(), approval_id))
        return self.get(approval_id) or rec

    def verify_grant(self, approval_id: str | None, workflow_id: str, capability: str, args: dict[str, Any], required_role: str | None) -> dict[str, Any]:
        rec = self.get(approval_id) if approval_id else None
        if not rec:
            raise ApprovalError("approval required and no grant presented")
        if rec["status"] != "APPROVED":
            raise ApprovalError(f"approval {approval_id} is {rec['status']}")
        if rec["digest"] != digest(workflow_id, capability, args):
            raise ApprovalError("approval does not cover this exact action")
        if required_role and required_role not in self.directory.roles(rec["decided_by"]):
            raise ApprovalError("approver lacks the required role")
        return rec
