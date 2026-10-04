"""Conversation sessions: what was said in this interaction. Append-only, per channel and user."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_platform.storage import connect

DDL = """
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, channel TEXT NOT NULL, user_id TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, at TEXT NOT NULL);
"""


class SessionStore:
    def __init__(self, db_path: Path):
        self.db = connect(db_path)
        self.db.executescript(DDL)

    def open(self, channel: str, user_id: str, session_id: str | None = None) -> str:
        sid = session_id or f"ses-{uuid.uuid4().hex[:10]}"
        self.db.execute("INSERT OR IGNORE INTO sessions VALUES (?,?,?,?)",
                        (sid, channel, user_id, datetime.now(timezone.utc).isoformat()))
        return sid

    def append(self, session_id: str, role: str, content: str) -> None:
        self.db.execute("INSERT INTO messages (session_id, role, content, at) VALUES (?,?,?,?)",
                        (session_id, role, content, datetime.now(timezone.utc).isoformat()))

    def history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT role, content, at FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
                               (session_id, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]
