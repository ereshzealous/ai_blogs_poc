"""Human approval store. An approval is bound to one invocation digest.

The digest covers tool, canonical arguments, environment and request ID, so approving
`rollback_release(checkout-api, v4.16, production)` does not approve any other version, service,
environment or a later request.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ApprovalRequest:
    digest: str
    request_id: str
    tool_id: str
    arguments_json: str
    environment: str
    reason: str


class ApprovalStore:
    def __init__(self, path: str | Path = ":memory:"):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS approvals (digest TEXT PRIMARY KEY, request_id TEXT, tool_id TEXT, arguments TEXT,"
            " environment TEXT, reason TEXT, status TEXT, requested_at TEXT, decided_at TEXT, approver TEXT, note TEXT)"
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def request(self, req: ApprovalRequest) -> ApprovalStatus:
        with self._lock:
            row = self._db.execute("SELECT status FROM approvals WHERE digest = ?", (req.digest,)).fetchone()
            if row:
                return ApprovalStatus(row[0])
            self._db.execute(
                "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, NULL, NULL, NULL)",
                (req.digest, req.request_id, req.tool_id, req.arguments_json, req.environment, req.reason, self._now()),
            )
            return ApprovalStatus.PENDING

    def decide(self, digest: str, approve: bool, approver: str, note: str = "") -> ApprovalStatus:
        status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
        with self._lock:
            cur = self._db.execute(
                "UPDATE approvals SET status = ?, decided_at = ?, approver = ?, note = ? WHERE digest = ? AND status = 'pending'",
                (status.value, self._now(), approver, note, digest),
            )
            if cur.rowcount != 1:
                raise KeyError(f"no pending approval for digest {digest[:12]}")
        return status

    def status(self, digest: str) -> ApprovalStatus | None:
        row = self._db.execute("SELECT status FROM approvals WHERE digest = ?", (digest,)).fetchone()
        return ApprovalStatus(row[0]) if row else None

    def pending(self) -> list[dict[str, str]]:
        cols = ("digest", "request_id", "tool_id", "arguments", "environment", "reason", "requested_at")
        rows = self._db.execute(f"SELECT {', '.join(cols)} FROM approvals WHERE status = 'pending' ORDER BY requested_at").fetchall()
        return [dict(zip(cols, r)) for r in rows]
