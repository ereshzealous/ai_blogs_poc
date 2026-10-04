"""Episodic memory: what the platform learned in earlier runs. Curated, provenance-tracked and expiring.

Memory is not chat history (that is the session) and not workflow state (that belongs to orchestration).
A memory can be wrong or stale, so it carries its source, a confidence and an expiry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from agent_platform.config import CONFIG_DIR
from agent_platform.storage import connect
from agent_platform.telemetry.tracing import span

DDL = """
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL,
  source TEXT NOT NULL, confidence REAL NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
"""


class MissingProvenance(ValueError):
    pass


@dataclass(frozen=True)
class Memory:
    id: int
    scope: str
    kind: str
    content: str
    source: str
    confidence: float
    created_at: str
    expires_at: str


class MemoryStore:
    def __init__(self, db_path: Path):
        self.db = connect(db_path)
        self.db.executescript(DDL)

    def seed(self) -> None:
        if self.db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]:
            return
        with open(CONFIG_DIR / "memory_seed.yaml", encoding="utf-8") as fh:
            for m in yaml.safe_load(fh):
                self.db.execute("INSERT INTO memories (scope, kind, content, source, confidence, created_at, expires_at) "
                                "VALUES (?,?,?,?,?,?,?)", (m["scope"], m["kind"], m["content"], m["source"],
                                                           m["confidence"], m["created_at"], m["expires_at"]))

    def recall(self, scope: str, *, now: datetime | None = None, limit: int = 3) -> list[Memory]:
        now_s = (now or datetime.now(timezone.utc)).isoformat()
        with span("memory.read", **{"lap.memory.scope": scope}) as s:
            rows = self.db.execute("SELECT * FROM memories WHERE scope=? AND expires_at > ? "
                                   "ORDER BY confidence DESC, created_at DESC LIMIT ?", (scope, now_s, limit)).fetchall()
            expired = self.db.execute("SELECT COUNT(*) FROM memories WHERE scope=? AND expires_at <= ?", (scope, now_s)).fetchone()[0]
            s.set_attribute("lap.memory.returned", len(rows))
            s.set_attribute("lap.memory.expired_skipped", expired)
            return [Memory(**dict(r)) for r in rows]

    def remember(self, scope: str, content: str, *, source: str, confidence: float, ttl_days: int = 180,
                 kind: str = "episodic") -> int:
        if not source:
            raise MissingProvenance("a memory needs a source")
        now = datetime.now(timezone.utc)
        with span("memory.write", **{"lap.memory.scope": scope, "lap.memory.source": source}):
            cur = self.db.execute("INSERT INTO memories (scope, kind, content, source, confidence, created_at, expires_at) "
                                  "VALUES (?,?,?,?,?,?,?)", (scope, kind, content, source, confidence, now.isoformat(),
                                                             (now + timedelta(days=ttl_days)).isoformat()))
            return int(cur.lastrowid)

    def all(self, scope: str) -> list[Memory]:
        return [Memory(**dict(r)) for r in self.db.execute("SELECT * FROM memories WHERE scope=? ORDER BY id", (scope,))]
