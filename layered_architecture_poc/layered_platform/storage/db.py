"""SQLite access for the platform's own state (workflows, checkpoints, approvals, operations, memory, audit).

One file per deployment, WAL mode, synchronous=FULL: a committed checkpoint survives a SIGKILL of the process.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS workflows (id TEXT PRIMARY KEY, request_id TEXT, incident_id TEXT, requested_by TEXT, channel TEXT,
    status TEXT, step TEXT, state TEXT, trace_id TEXT, root_span_id TEXT, created REAL, updated REAL, lease_pid INTEGER, lease_until REAL);
CREATE TABLE IF NOT EXISTS checkpoints (workflow_id TEXT, seq INTEGER, step TEXT, next_step TEXT, status TEXT, state TEXT,
    state_sha TEXT, pid INTEGER, ts REAL, PRIMARY KEY (workflow_id, seq));
CREATE TABLE IF NOT EXISTS workflow_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT, kind TEXT, step TEXT, data TEXT, pid INTEGER, ts REAL);
CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, workflow_id TEXT, capability TEXT, args TEXT, digest TEXT, requested_by TEXT,
    required_role TEXT, status TEXT, decided_by TEXT, reason TEXT, created REAL, decided REAL);
CREATE TABLE IF NOT EXISTS operations (op_id TEXT PRIMARY KEY, workflow_id TEXT, capability TEXT, args_sha TEXT, state TEXT,
    attempts INTEGER, result TEXT, error TEXT, created REAL, updated REAL);
CREATE TABLE IF NOT EXISTS policy_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT, capability TEXT, args TEXT,
    principal TEXT, effect TEXT, rule TEXT, reason TEXT, trace_id TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS tool_calls (seq INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT, op_id TEXT, capability TEXT, server TEXT,
    tool TEXT, args TEXT, attempt INTEGER, outcome TEXT, error TEXT, wall_s REAL, trace_id TEXT, pid INTEGER, ts REAL);
CREATE TABLE IF NOT EXISTS model_usage (seq INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT, agent TEXT, route TEXT, model TEXT,
    prompt_tokens INTEGER, completion_tokens INTEGER, wall_s REAL, trace_id TEXT, pid INTEGER, ts REAL);
CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, subject TEXT, kind TEXT, text TEXT, source TEXT, confidence REAL,
    created REAL, expires REAL);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path), timeout=30, isolation_level=None, check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db
