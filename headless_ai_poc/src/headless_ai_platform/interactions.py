"""Interaction state owned by the headless boundary: who touched which workflow from where, which channels want to
hear back, and what has not been delivered yet.

None of this is workflow state. Deleting a row here never changes what the platform does with a workflow; losing a
channel only means a message waits in the outbox until the channel is back.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DDL = """
CREATE TABLE IF NOT EXISTS interactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, workflow_id TEXT, capability TEXT NOT NULL,
  channel TEXT NOT NULL, channel_subject TEXT NOT NULL, principal_id TEXT, operation TEXT NOT NULL,
  action_id TEXT, outcome TEXT NOT NULL, status TEXT, trace_id TEXT, thread_ref TEXT);
CREATE TABLE IF NOT EXISTS idempotency (
  channel TEXT NOT NULL, key TEXT NOT NULL, workflow_id TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY (channel, key));
CREATE TABLE IF NOT EXISTS subscriptions (
  workflow_id TEXT NOT NULL, channel TEXT NOT NULL, address TEXT NOT NULL, principal_id TEXT NOT NULL,
  thread_ref TEXT, last_status TEXT, created_at TEXT NOT NULL, PRIMARY KEY (workflow_id, channel, address));
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT NOT NULL, channel TEXT NOT NULL, address TEXT NOT NULL,
  thread_ref TEXT, status TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'PENDING',
  attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, created_at TEXT NOT NULL, delivered_at TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class InteractionStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(DDL)
        self.lock = threading.Lock()

    def _exec(self, sql: str, args: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.db.execute(sql, args)

    # ---------------------------------------------------------------- interactions
    def record(self, *, workflow_id: str | None, capability: str, channel: str, channel_subject: str,
               principal_id: str | None, operation: str, action_id: str | None, outcome: str, status: str | None,
               trace_id: str | None, thread_ref: str | None) -> None:
        self._exec("INSERT INTO interactions (at, workflow_id, capability, channel, channel_subject, principal_id, operation,"
                   " action_id, outcome, status, trace_id, thread_ref) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (now(), workflow_id, capability, channel, channel_subject, principal_id, operation, action_id, outcome,
                    status, trace_id, thread_ref))

    def interactions(self, workflow_id: str | None = None) -> list[dict[str, Any]]:
        if workflow_id is None:
            rows = self._exec("SELECT * FROM interactions ORDER BY id")
        else:
            rows = self._exec("SELECT * FROM interactions WHERE workflow_id=? ORDER BY id", (workflow_id,))
        return [dict(r) for r in rows.fetchall()]

    # ---------------------------------------------------------------- idempotency
    def remembered(self, channel: str, key: str) -> str | None:
        row = self._exec("SELECT workflow_id FROM idempotency WHERE channel=? AND key=?", (channel, key)).fetchone()
        return row["workflow_id"] if row else None

    def remember(self, channel: str, key: str, workflow_id: str) -> None:
        self._exec("INSERT OR IGNORE INTO idempotency (channel, key, workflow_id, at) VALUES (?,?,?,?)",
                   (channel, key, workflow_id, now()))

    # ---------------------------------------------------------------- subscriptions and outbox
    def subscribe(self, workflow_id: str, channel: str, address: str, principal_id: str, thread_ref: str | None) -> None:
        self._exec("INSERT OR IGNORE INTO subscriptions (workflow_id, channel, address, principal_id, thread_ref, created_at)"
                   " VALUES (?,?,?,?,?,?)", (workflow_id, channel, address, principal_id, thread_ref, now()))

    def subscriptions(self, workflow_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self._exec("SELECT * FROM subscriptions WHERE workflow_id=?", (workflow_id,)).fetchall()]

    def enqueue(self, sub: dict[str, Any], status: str, payload: dict[str, Any]) -> bool:
        """Queue one notification per status change per subscriber. Returns False if this status was already queued."""
        with self.lock:
            cur = self.db.execute("UPDATE subscriptions SET last_status=? WHERE workflow_id=? AND channel=? AND address=?"
                                  " AND (last_status IS NULL OR last_status<>?)",
                                  (status, sub["workflow_id"], sub["channel"], sub["address"], status))
            if cur.rowcount == 0:
                return False
            self.db.execute("INSERT INTO outbox (workflow_id, channel, address, thread_ref, status, payload, created_at)"
                            " VALUES (?,?,?,?,?,?,?)", (sub["workflow_id"], sub["channel"], sub["address"], sub["thread_ref"],
                                                        status, json.dumps(payload), now()))
            return True

    def pending(self, channels: list[str], max_attempts: int) -> list[dict[str, Any]]:
        marks = ",".join("?" * len(channels))
        rows = self._exec(f"SELECT * FROM outbox WHERE state='PENDING' AND attempts<? AND channel IN ({marks}) ORDER BY id",
                          (max_attempts, *channels)).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def delivered(self, outbox_id: int) -> None:
        self._exec("UPDATE outbox SET state='DELIVERED', attempts=attempts+1, delivered_at=?, last_error=NULL WHERE id=?",
                   (now(), outbox_id))

    def failed(self, outbox_id: int, error: str) -> None:
        self._exec("UPDATE outbox SET attempts=attempts+1, last_error=? WHERE id=?", (error[:300], outbox_id))

    def outbox(self, workflow_id: str | None = None) -> list[dict[str, Any]]:
        sql, args = ("SELECT * FROM outbox ORDER BY id", ()) if workflow_id is None else \
            ("SELECT * FROM outbox WHERE workflow_id=? ORDER BY id", (workflow_id,))
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in self._exec(sql, args).fetchall()]
