"""Operation records for side-effecting calls. A retry, or a resumed workflow, reuses the same operation id."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_platform.storage import connect

DDL = """
CREATE TABLE IF NOT EXISTS idempotency (
  operation_id TEXT PRIMARY KEY, tool_id TEXT NOT NULL, args_digest TEXT NOT NULL, status TEXT NOT NULL,
  result TEXT, attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
"""


class OperationConflict(RuntimeError):
    pass


class IdempotencyStore:
    def __init__(self, db_path: Path):
        self.db = connect(db_path)
        self.db.executescript(DDL)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def begin(self, operation_id: str, tool_id: str, args_digest: str) -> dict[str, Any] | None:
        """Return the completed record if this operation already succeeded, else mark it in flight."""
        row = self.db.execute("SELECT * FROM idempotency WHERE operation_id=?", (operation_id,)).fetchone()
        if row is not None:
            if row["args_digest"] != args_digest or row["tool_id"] != tool_id:
                raise OperationConflict(f"operation {operation_id} was recorded with different arguments")
            if row["status"] == "COMPLETED":
                return {"status": row["status"], "result": json.loads(row["result"]), "attempts": row["attempts"]}
            return {"status": row["status"], "result": None, "attempts": row["attempts"]}
        now = self._now()
        self.db.execute("INSERT INTO idempotency VALUES (?,?,?,?,?,?,?,?)",
                        (operation_id, tool_id, args_digest, "IN_FLIGHT", None, 0, now, now))
        return None

    def attempt(self, operation_id: str) -> None:
        self.db.execute("UPDATE idempotency SET attempts = attempts + 1, updated_at=? WHERE operation_id=?",
                        (self._now(), operation_id))

    def complete(self, operation_id: str, result: Any) -> None:
        self.db.execute("UPDATE idempotency SET status='COMPLETED', result=?, updated_at=? WHERE operation_id=?",
                        (json.dumps(result), self._now(), operation_id))

    def fail(self, operation_id: str, error: str) -> None:
        self.db.execute("UPDATE idempotency SET status='UNKNOWN', result=?, updated_at=? WHERE operation_id=?",
                        (json.dumps({"error": error}), self._now(), operation_id))

    def get(self, operation_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM idempotency WHERE operation_id=?", (operation_id,)).fetchone()
        return dict(row) if row else None
