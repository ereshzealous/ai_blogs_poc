"""Memory: what the platform retained from earlier work, with provenance, kind and an expiry.

Memory is not workflow state: it is advisory, it can be stale, and the model reads it as context, never as truth.
`remember` is keyed, so writing the same memory twice (for example after a resume) does not duplicate it.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

import yaml

from layered_platform.config import ROOT


class MemoryStore:
    def __init__(self, db: sqlite3.Connection, seed: str | None = None, ttl_days: int = 180):
        self.db, self.ttl = db, ttl_days * 86400
        if seed and not self.db.execute("SELECT 1 FROM memories LIMIT 1").fetchone():
            for m in yaml.safe_load((ROOT / seed).read_text()):
                self.remember(m["id"], m["subject"], m["kind"], m["text"], m["source"], confidence=0.9)

    def remember(self, key: str, subject: str, kind: str, text: str, source: str, confidence: float = 0.8) -> None:
        now = time.time()
        self.db.execute("INSERT OR REPLACE INTO memories VALUES (?,?,?,?,?,?,?,?)", (key, subject, kind, text, source, confidence, now, now + self.ttl))

    def recall(self, subject: str, limit: int = 5) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM memories WHERE subject=? AND expires>? ORDER BY created DESC LIMIT ?", (subject, time.time(), limit)).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM memories").fetchone()[0])
