"""Memory stores (SQLite). The governed store keeps the full record; the naive store keeps text and a timestamp, as a
plain "remember this" store does. Neither store is working context, and neither holds workflow state."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from governed_memory.models.record import MemoryRecord
from governed_memory.platform.layered_adapter import connect


def _to_json(r: MemoryRecord) -> str:
    d = asdict(r)
    d["created_at"] = r.created_at.isoformat()
    d["expires_at"] = r.expires_at.isoformat() if r.expires_at else None
    d["trust"] = {"source_class": d.pop("source_class")}
    return json.dumps(d, sort_keys=True)


class GovernedMemoryStore:
    def __init__(self, db_path: Path):
        self.db = connect(db_path)
        self.db.execute("CREATE TABLE IF NOT EXISTS governed_memories (id TEXT PRIMARY KEY, record TEXT NOT NULL)")

    def put(self, r: MemoryRecord) -> None:
        self.db.execute("INSERT OR REPLACE INTO governed_memories VALUES (?,?)", (r.id, _to_json(r)))

    def all(self) -> list[MemoryRecord]:
        return [MemoryRecord.from_dict(json.loads(row[0])) for row in
                self.db.execute("SELECT record FROM governed_memories ORDER BY id")]


class NaiveMemoryStore:
    def __init__(self, db_path: Path):
        self.db = connect(db_path)
        self.db.execute("CREATE TABLE IF NOT EXISTS naive_memories (id TEXT PRIMARY KEY, content TEXT NOT NULL, created_at TEXT NOT NULL)")

    def put(self, r: MemoryRecord) -> None:
        self.db.execute("INSERT OR REPLACE INTO naive_memories VALUES (?,?,?)", (r.id, r.content, r.created_at.isoformat()))

    def texts(self) -> list[tuple[str, str, str]]:
        return [tuple(row) for row in self.db.execute("SELECT id, content, created_at FROM naive_memories ORDER BY id")]
