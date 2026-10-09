"""Durable workflow state: the authoritative record of where a workflow is, and what it has already done.

A workflow row holds the current step and state; `checkpoints` is an append-only history of every completed step.
Both are written in one transaction when a step finishes, so after a crash the state is exactly "the last completed
step", never half of one.  A lease (pid + expiry) stops two live processes working on the same workflow; a lease held
by a dead process can be taken over.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from typing import Any

LEASE_S = 900


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class LeaseHeld(RuntimeError):
    pass


class CheckpointStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def create(self, wf: str, request_id: str, incident_id: str, requested_by: str, channel: str, first_step: str,
               state: dict[str, Any], trace_id: str, span_id: str) -> None:
        now = time.time()
        self.db.execute("INSERT INTO workflows VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (wf, request_id, incident_id, requested_by, channel, "RUNNING", first_step, json.dumps(state), trace_id, span_id, now, now, None, None))
        self.event(wf, "workflow.created", first_step, {"request_id": request_id})

    def find_by_request(self, request_id: str) -> str | None:
        row = self.db.execute("SELECT id FROM workflows WHERE request_id=?", (request_id,)).fetchone()
        return row["id"] if row else None

    def load(self, wf: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM workflows WHERE id=?", (wf,)).fetchone()
        if not row:
            raise KeyError(wf)
        rec = dict(row)
        rec["state"] = json.loads(rec["state"])
        return rec

    def acquire(self, wf: str) -> None:
        self.db.execute("BEGIN IMMEDIATE")
        row = self.db.execute("SELECT lease_pid, lease_until FROM workflows WHERE id=?", (wf,)).fetchone()
        pid, until = row["lease_pid"], row["lease_until"] or 0
        if pid and pid != os.getpid() and until > time.time() and _alive(pid):
            self.db.execute("ROLLBACK")
            raise LeaseHeld(f"{wf} is being worked on by pid {pid}")
        taken_over = bool(pid and pid != os.getpid())
        self.db.execute("UPDATE workflows SET lease_pid=?, lease_until=? WHERE id=?", (os.getpid(), time.time() + LEASE_S, wf))
        self.db.execute("COMMIT")
        if taken_over:
            self.event(wf, "lease.taken_over", None, {"previous_pid": pid})

    def release(self, wf: str) -> None:
        self.db.execute("UPDATE workflows SET lease_pid=NULL, lease_until=NULL WHERE id=? AND lease_pid=?", (wf, os.getpid()))

    def checkpoint(self, wf: str, step: str, next_step: str, status: str, state: dict[str, Any]) -> int:
        blob = json.dumps(state, sort_keys=True, default=str)
        self.db.execute("BEGIN IMMEDIATE")
        seq = self.db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM checkpoints WHERE workflow_id=?", (wf,)).fetchone()[0]
        self.db.execute("INSERT INTO checkpoints VALUES (?,?,?,?,?,?,?,?,?)",
                        (wf, seq, step, next_step, status, blob, hashlib.sha256(blob.encode()).hexdigest()[:16], os.getpid(), time.time()))
        self.db.execute("UPDATE workflows SET step=?, status=?, state=?, updated=? WHERE id=?", (next_step, status, blob, time.time(), wf))
        self.db.execute("COMMIT")
        return int(seq)

    def set_status(self, wf: str, status: str) -> None:
        self.db.execute("UPDATE workflows SET status=?, updated=? WHERE id=?", (status, time.time(), wf))

    def event(self, wf: str, kind: str, step: str | None, data: dict[str, Any] | None = None) -> None:
        self.db.execute("INSERT INTO workflow_events (workflow_id, kind, step, data, pid, ts) VALUES (?,?,?,?,?,?)",
                        (wf, kind, step, json.dumps(data or {}, default=str), os.getpid(), time.time()))

    def resumable(self) -> list[str]:
        rows = self.db.execute("SELECT id, lease_pid FROM workflows WHERE status='RUNNING'").fetchall()
        return [r["id"] for r in rows if not _alive(r["lease_pid"]) or r["lease_pid"] == os.getpid()]

    def history(self, wf: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.execute("SELECT workflow_id, seq, step, next_step, status, state_sha, pid, ts FROM checkpoints WHERE workflow_id=? ORDER BY seq", (wf,))]
