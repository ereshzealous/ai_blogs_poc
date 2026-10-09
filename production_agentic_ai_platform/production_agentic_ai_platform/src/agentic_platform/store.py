"""Platform state (platform.db): each kind of state has its own table and its own owner.

    sessions            the current interaction (experience layer)
    workflows, checkpoints   durable task state (orchestration only)
    action_journal      attempts at consequential actions and their outcomes (tool & action platform)
    approvals           approval requests and signed decisions (approval service)
    budget_ledger       runtime resource usage per workflow (enforcement)
    knowledge           enterprise knowledge index with tenant/classification/ACL/environment metadata (context)
    memory              episodic memory, tenant-scoped, with provenance and expiry (memory service)

The knowledge table is an index: the authoritative facts (what is deployed, what is running) come from the systems of
record through MCP, never from here.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import yaml

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, user_id TEXT, channel TEXT, tenant TEXT, created_at REAL, messages_json TEXT);
CREATE TABLE IF NOT EXISTS workflows (id TEXT PRIMARY KEY, session_id TEXT, agent TEXT, user_id TEXT, tenant TEXT, incident TEXT, status TEXT,
  traceparent TEXT, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS checkpoints (workflow_id TEXT, seq INTEGER, step TEXT, state_json TEXT, at REAL, pid INTEGER, PRIMARY KEY (workflow_id, seq));
CREATE TABLE IF NOT EXISTS action_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT, digest TEXT, idempotency_key TEXT, attempt INTEGER,
  capability_jti TEXT, status TEXT, result_json TEXT, at REAL, pid INTEGER);
CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, workflow_id TEXT, digest TEXT, canonical TEXT, requested_by TEXT, requested_at REAL,
  status TEXT, approver TEXT, decided_at REAL, expires_at REAL, signature TEXT, decision_id TEXT);
CREATE TABLE IF NOT EXISTS budget_ledger (workflow_id TEXT, kind TEXT, units REAL, detail TEXT, at REAL);
CREATE TABLE IF NOT EXISTS knowledge (id TEXT PRIMARY KEY, kind TEXT, tenant TEXT, classification TEXT, acl_json TEXT, environment TEXT, source TEXT,
  updated_at TEXT, expires_at TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS memory (id TEXT PRIMARY KEY, tenant TEXT, kind TEXT, text TEXT, provenance_json TEXT, created_at REAL, expires_at REAL);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    @classmethod
    def reset(cls, path: str | Path, seed_path: Path) -> Store:
        p = Path(path)
        for suffix in ("", "-wal", "-shm"):
            Path(str(p) + suffix).unlink(missing_ok=True)
        s = cls(p)
        seed = yaml.safe_load(seed_path.read_text())
        with s.db:
            for k in seed["knowledge"]:
                s.db.execute("INSERT INTO knowledge VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (k["id"], k["kind"], k["tenant"], k["classification"], json.dumps(k["acl"]), k["environment"], k["source"],
                              k["updated_at"], k.get("expires_at"), k["text"]))
        return s

    def q(self, sql: str, *args: Any) -> list[tuple]:
        return self.db.execute(sql, args).fetchall()

    # ---- workflow state ------------------------------------------------------------------------------------------------
    def checkpoint(self, workflow_id: str, step: str, state: dict[str, Any], pid: int) -> int:
        n = self.q("SELECT COALESCE(MAX(seq), 0) FROM checkpoints WHERE workflow_id=?", workflow_id)[0][0] + 1
        with self.db:
            self.db.execute("INSERT INTO checkpoints VALUES (?,?,?,?,?,?)", (workflow_id, n, step, json.dumps(state, default=str), time.time(), pid))
            self.db.execute("UPDATE workflows SET status=?, updated_at=? WHERE id=?", (state.get("status", "running"), time.time(), workflow_id))
        return n

    def latest(self, workflow_id: str) -> dict[str, Any] | None:
        r = self.q("SELECT state_json FROM checkpoints WHERE workflow_id=? ORDER BY seq DESC LIMIT 1", workflow_id)
        return json.loads(r[0][0]) if r else None

    # ---- budget --------------------------------------------------------------------------------------------------------
    def usage(self, workflow_id: str) -> dict[str, float]:
        return {k: v for k, v in self.q("SELECT kind, SUM(units) FROM budget_ledger WHERE workflow_id=? GROUP BY kind", workflow_id)}

    def charge(self, workflow_id: str, kind: str, units: float, detail: str) -> None:
        self.db.execute("INSERT INTO budget_ledger VALUES (?,?,?,?,?)", (workflow_id, kind, units, detail, time.time()))
