"""Append-only audit log of policy decisions, approvals checks and executions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_platform.storage import connect

DDL = """
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, workflow_id TEXT, event TEXT NOT NULL, body TEXT NOT NULL);
"""


class AuditLog:
    def __init__(self, db_path: Path):
        self.db = connect(db_path)
        self.db.executescript(DDL)

    def write(self, event: str, workflow_id: str | None, **fields: Any) -> None:
        self.db.execute("INSERT INTO audit (at, workflow_id, event, body) VALUES (?,?,?,?)",
                        (datetime.now(timezone.utc).isoformat(), workflow_id, event, json.dumps(fields, default=str)))

    def list(self, workflow_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT id, at, event, body FROM audit WHERE workflow_id=? ORDER BY id", (workflow_id,))
        return [{"id": r["id"], "at": r["at"], "event": r["event"], **json.loads(r["body"])} for r in rows]
