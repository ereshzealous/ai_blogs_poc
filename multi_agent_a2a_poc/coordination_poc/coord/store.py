"""The platform store (platform.db): canonical workflow state plus append-only ledgers.

Workflow truth lives in `workflows` (status, termination, outcome, the final view) and `steps`; only the capability
runtime in the host process writes them.  Every process may append to the ledgers (`gateway_calls`, `model_usage`,
`approvals`) and the host records `delegations` and `artifacts`.  An agent's own context, in its own process, is never
consulted for what happened: the ledgers are.  ("Agent memory is not workflow truth" is a hypothesis the run tests.)
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from coord.util import canon

SCHEMA = """
CREATE TABLE IF NOT EXISTS workflows (workflow_id TEXT PRIMARY KEY, run_id TEXT, arch TEXT, fixture_id TEXT, repeat INTEGER, seed INTEGER,
    incident_id TEXT, service TEXT, environment TEXT, status TEXT, termination TEXT, outcome TEXT, started REAL, ended REAL,
    deadline REAL, max_tokens INTEGER, idempotency TEXT DEFAULT 'workflow', trace_id TEXT, config TEXT, result TEXT, view TEXT);
CREATE TABLE IF NOT EXISTS steps (seq INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT, component TEXT, kind TEXT,
    decided_by TEXT, detail TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS delegations (delegation_id TEXT, attempt INTEGER, workflow_id TEXT, seq INTEGER, agent TEXT, mode TEXT,
    objective_digest TEXT, inputs TEXT, a2a_task_id TEXT, a2a_context_id TEXT, a2a_state TEXT, state TEXT, started REAL, ended REAL,
    client_ms REAL, server_ms REAL, req_bytes INTEGER, resp_bytes INTEGER, error TEXT, artifact_id TEXT, scopes TEXT, token_chain TEXT,
    PRIMARY KEY (delegation_id, attempt));
CREATE TABLE IF NOT EXISTS artifacts (artifact_id TEXT, workflow_id TEXT, producer TEXT, kind TEXT, body TEXT,
    delegation_id TEXT, bytes INTEGER, created REAL, PRIMARY KEY (workflow_id, artifact_id));
CREATE TABLE IF NOT EXISTS gateway_calls (seq INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT, component TEXT, actor_chain TEXT,
    capability TEXT, kind TEXT, args TEXT, effect TEXT, rule TEXT, approval_id TEXT, outcome TEXT, error TEXT, idem_key TEXT,
    world_version INTEGER, evidence_ref TEXT, wall_ms REAL, trace_id TEXT, pid INTEGER, ts REAL, delegation_id TEXT, wf_seq INTEGER);
CREATE TABLE IF NOT EXISTS approvals (approval_id TEXT PRIMARY KEY, workflow_id TEXT, capability TEXT, args TEXT, digest TEXT,
    approver TEXT, role TEXT, decided TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS model_usage (seq INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT, component TEXT, role TEXT, model TEXT,
    prompt_tokens INTEGER, completion_tokens INTEGER, wall_ms REAL, ok INTEGER, error TEXT, trace_id TEXT, pid INTEGER, ts REAL,
    delegation_id TEXT);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript(SCHEMA)

    def db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=60, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.row_factory = sqlite3.Row
        return db

    def execute(self, sql: str, args: tuple[Any, ...] = ()) -> None:
        with self.db() as db:
            db.execute(sql, args)

    def rows(self, sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.db() as db:
            return [dict(r) for r in db.execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        r = self.rows(sql, args)
        return r[0] if r else None

    # ---- workflow (single writer: the host runtime) --------------------------------------------------------------------
    def create_workflow(self, **w: Any) -> None:
        cols = ",".join(w)
        self.execute(f"INSERT INTO workflows ({cols}) VALUES ({','.join('?' * len(w))})",
                     tuple(canon(v) if isinstance(v, (dict, list)) else v for v in w.values()))

    def update_workflow(self, workflow_id: str, **w: Any) -> None:
        sets = ",".join(f"{k}=?" for k in w)
        self.execute(f"UPDATE workflows SET {sets} WHERE workflow_id=?",
                     tuple(canon(v) if isinstance(v, (dict, list)) else v for v in w.values()) + (workflow_id,))

    def workflow(self, workflow_id: str) -> dict[str, Any] | None:
        return self.one("SELECT * FROM workflows WHERE workflow_id=?", (workflow_id,))

    def step(self, workflow_id: str, component: str, kind: str, decided_by: str, **detail: Any) -> None:
        """decided_by: 'code' (deterministic decision) or 'model' (an agent decided)."""
        self.execute("INSERT INTO steps (workflow_id, component, kind, decided_by, detail, ts) VALUES (?,?,?,?,?,?)",
                     (workflow_id, component, kind, decided_by, canon(detail), time.time()))

    # ---- ledgers ----------------------------------------------------------------------------------------------------
    def tokens_used(self, workflow_id: str) -> int:
        r = self.one("SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0) AS n FROM model_usage WHERE workflow_id=?", (workflow_id,))
        return int(r["n"]) if r else 0

    def record_usage(self, **u: Any) -> None:
        u.setdefault("pid", os.getpid())
        u.setdefault("ts", time.time())
        cols = ",".join(u)
        self.execute(f"INSERT INTO model_usage ({cols}) VALUES ({','.join('?' * len(u))})", tuple(u.values()))

    def record_call(self, **c: Any) -> tuple[int, int]:
        """Append one gateway call.  Returns (global seq, per-workflow ordinal); the ordinal numbers evidence refs, so a
        workflow replayed into a fresh store produces the same refs, hence the same prompts."""
        c.setdefault("pid", os.getpid())
        c.setdefault("ts", time.time())
        db = self.db()
        try:
            db.execute("BEGIN IMMEDIATE")
            n = db.execute("SELECT COUNT(*) FROM gateway_calls WHERE workflow_id=?", (c.get("workflow_id"),)).fetchone()[0] + 1
            c["wf_seq"] = n
            cols = ",".join(c)
            cur = db.execute(f"INSERT INTO gateway_calls ({cols}) VALUES ({','.join('?' * len(c))})", tuple(c.values()))
            db.execute("COMMIT")
            return int(cur.lastrowid), int(n)
        except BaseException:
            db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def set_call(self, seq: int, **c: Any) -> None:
        sets = ",".join(f"{k}=?" for k in c)
        self.execute(f"UPDATE gateway_calls SET {sets} WHERE seq=?", tuple(c.values()) + (seq,))

    def calls(self, workflow_id: str) -> list[dict[str, Any]]:
        out = self.rows("SELECT * FROM gateway_calls WHERE workflow_id=? ORDER BY seq", (workflow_id,))
        for r in out:
            r["args"] = json.loads(r["args"])
        return out

    def put_artifact(self, artifact_id: str, workflow_id: str, producer: str, kind: str, body: Any, delegation_id: str | None) -> None:
        text = canon(body)
        self.execute("INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?,?,?,?)",
                     (artifact_id, workflow_id, producer, kind, text, delegation_id, len(text.encode()), time.time()))

    def artifact(self, workflow_id: str, artifact_id: str) -> dict[str, Any] | None:
        r = self.one("SELECT * FROM artifacts WHERE workflow_id=? AND artifact_id=?", (workflow_id, artifact_id))
        if r:
            r["body"] = json.loads(r["body"])
        return r
