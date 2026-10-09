"""The platform database: inbox, executions, checkpoints, approvals, idempotency, audit, dead letters.

It is separate from the world (the systems of record).  AI state lives here; business truth lives there.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS inbox (source TEXT, event_id TEXT, received REAL, envelope TEXT, execution_id TEXT, PRIMARY KEY (source, event_id));
CREATE TABLE IF NOT EXISTS executions (id TEXT PRIMARY KEY, correlation_id TEXT, fingerprint TEXT, intent TEXT, channel TEXT, invoker TEXT,
    status TEXT, step TEXT, state TEXT, identity TEXT, created REAL, updated REAL);
CREATE TABLE IF NOT EXISTS checkpoints (n INTEGER PRIMARY KEY AUTOINCREMENT, execution_id TEXT, step TEXT, status TEXT, t REAL);
CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, execution_id TEXT, capability TEXT, arguments TEXT, digest TEXT,
    required_role TEXT, required_scope TEXT, requested_by TEXT, status TEXT, decided_by TEXT, created REAL, expires REAL, decided REAL);
CREATE TABLE IF NOT EXISTS calls (key TEXT PRIMARY KEY, execution_id TEXT, capability TEXT, response TEXT);
CREATE TABLE IF NOT EXISTS dead_letters (n INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, reason TEXT, payload TEXT, t REAL);
CREATE TABLE IF NOT EXISTS audit (n INTEGER PRIMARY KEY AUTOINCREMENT, t REAL, execution_id TEXT, correlation_id TEXT, kind TEXT,
    record TEXT, prev TEXT, hash TEXT);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db
