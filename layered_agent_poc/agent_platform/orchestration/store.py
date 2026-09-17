"""Durable workflow state: workflows, append-only checkpoints, an event log and approval requests.

Only orchestration writes these tables. Every step transition commits before the next step starts, so a process can die
at any point and a new process can continue from the last checkpoint.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_platform.storage import connect
from agent_platform.telemetry.tracing import span

DDL = """
CREATE TABLE IF NOT EXISTS workflows (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, incident_id TEXT NOT NULL, status TEXT NOT NULL, current_step TEXT NOT NULL,
  channel TEXT NOT NULL, requested_by TEXT NOT NULL, session_id TEXT, trace_id TEXT, root_span_id TEXT,
  segments INTEGER NOT NULL DEFAULT 0, lease_pid INTEGER, lease_until TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS checkpoints (
  workflow_id TEXT NOT NULL, seq INTEGER NOT NULL, step TEXT NOT NULL, next_step TEXT, state TEXT NOT NULL,
  pid INTEGER NOT NULL, at TEXT NOT NULL, PRIMARY KEY (workflow_id, seq));
CREATE TABLE IF NOT EXISTS workflow_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT NOT NULL, type TEXT NOT NULL, payload TEXT NOT NULL,
  pid INTEGER NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, digest TEXT NOT NULL, tool_id TEXT NOT NULL, arguments TEXT NOT NULL,
  required_role TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL, requested_at TEXT NOT NULL,
  decided_by TEXT, decided_at TEXT, comment TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowStore:
    def __init__(self, db_path: Path):
        self.db = connect(db_path)
        self.db.executescript(DDL)

    # ---------------------------------------------------------------- workflows
    def create(self, wf: dict[str, Any]) -> None:
        self.db.execute("INSERT INTO workflows (id, name, incident_id, status, current_step, channel, requested_by, session_id, "
                        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (wf["id"], wf["name"], wf["incident_id"], wf["status"], wf["current_step"], wf["channel"],
                         wf["requested_by"], wf.get("session_id"), now(), now()))

    def get(self, workflow_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        return dict(row) if row else None

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        q, p = "SELECT * FROM workflows", ()
        if status:
            q, p = q + " WHERE status=?", (status,)
        return [dict(r) for r in self.db.execute(q + " ORDER BY created_at", p)]

    def set_status(self, workflow_id: str, status: str, step: str) -> None:
        self.db.execute("UPDATE workflows SET status=?, current_step=?, updated_at=? WHERE id=?", (status, step, now(), workflow_id))

    def set_trace(self, workflow_id: str, trace_id: str, span_id: str) -> None:
        self.db.execute("UPDATE workflows SET trace_id=COALESCE(trace_id, ?), root_span_id=COALESCE(root_span_id, ?) WHERE id=?",
                        (trace_id, span_id, workflow_id))

    def next_segment(self, workflow_id: str) -> int:
        self.db.execute("UPDATE workflows SET segments = segments + 1 WHERE id=?", (workflow_id,))
        return int(self.db.execute("SELECT segments FROM workflows WHERE id=?", (workflow_id,)).fetchone()[0])

    # ---------------------------------------------------------------- leases
    def acquire(self, workflow_id: str, pid: int, ttl_s: int = 900) -> bool:
        """One worker at a time. A lease held by a dead process (a crashed worker) can be taken over."""
        from datetime import timedelta

        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT lease_pid, lease_until FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            holder, until = (row["lease_pid"], row["lease_until"]) if row else (None, None)
            if holder and holder != pid and until and until > now() and _alive(holder):
                self.db.execute("ROLLBACK")
                return False
            until = (datetime.now(timezone.utc) + timedelta(seconds=ttl_s)).isoformat()
            self.db.execute("UPDATE workflows SET lease_pid=?, lease_until=? WHERE id=?", (pid, until, workflow_id))
            self.db.execute("COMMIT")
            return True
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def release(self, workflow_id: str, pid: int) -> None:
        self.db.execute("UPDATE workflows SET lease_pid=NULL, lease_until=NULL WHERE id=? AND lease_pid=?", (workflow_id, pid))

    # ---------------------------------------------------------------- checkpoints
    def save_checkpoint(self, workflow_id: str, step: str, next_step: str | None, state: dict[str, Any], status: str,
                        traced: bool = True) -> int:
        import os
        from contextlib import nullcontext

        cm = span("checkpoint.save", **{"lap.workflow.id": workflow_id, "lap.step": step, "lap.next_step": next_step}) \
            if traced else nullcontext()
        with cm as s:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                seq = int(self.db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM checkpoints WHERE workflow_id=?",
                                          (workflow_id,)).fetchone()[0])
                self.db.execute("INSERT INTO checkpoints VALUES (?,?,?,?,?,?,?)",
                                (workflow_id, seq, step, next_step, json.dumps(state, default=str), os.getpid(), now()))
                self.db.execute("UPDATE workflows SET status=?, current_step=?, updated_at=? WHERE id=?",
                                (status, next_step or step, now(), workflow_id))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
            if s is not None:
                s.set_attribute("lap.checkpoint.seq", seq)
            return seq

    def latest_checkpoint(self, workflow_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM checkpoints WHERE workflow_id=? ORDER BY seq DESC LIMIT 1", (workflow_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["state"] = json.loads(d["state"])
        return d

    def checkpoints(self, workflow_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT seq, step, next_step, pid, at FROM checkpoints WHERE workflow_id=? ORDER BY seq", (workflow_id,))
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- events
    def event(self, workflow_id: str, type_: str, **payload: Any) -> None:
        import os

        self.db.execute("INSERT INTO workflow_events (workflow_id, type, payload, pid, at) VALUES (?,?,?,?,?)",
                        (workflow_id, type_, json.dumps(payload, default=str), os.getpid(), now()))

    def events(self, workflow_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT id, type, payload, pid, at FROM workflow_events WHERE workflow_id=? ORDER BY id", (workflow_id,))
        return [{"id": r["id"], "type": r["type"], "pid": r["pid"], "at": r["at"], **json.loads(r["payload"])} for r in rows]

    # ---------------------------------------------------------------- approvals
    def request_approval(self, workflow_id: str, digest: str, tool_id: str, arguments: dict[str, Any], role: str,
                         reason: str) -> dict[str, Any]:
        existing = self.approval_for(workflow_id, digest)
        if existing:
            return existing
        approval_id = f"apr-{digest[:10]}"
        self.db.execute("INSERT INTO approvals (id, workflow_id, digest, tool_id, arguments, required_role, reason, status, requested_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?)", (approval_id, workflow_id, digest, tool_id, json.dumps(arguments),
                                                       role, reason, "PENDING", now()))
        return self.approval_for(workflow_id, digest) or {}

    def approval_for(self, workflow_id: str, digest: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM approvals WHERE workflow_id=? AND digest=?", (workflow_id, digest)).fetchone()
        return self._approval(row)

    def open_approval(self, workflow_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM approvals WHERE workflow_id=? ORDER BY requested_at DESC LIMIT 1", (workflow_id,)).fetchone()
        return self._approval(row)

    def decide(self, approval_id: str, approver: str, approved: bool, comment: str = "") -> None:
        self.db.execute("UPDATE approvals SET status=?, decided_by=?, decided_at=?, comment=? WHERE id=? AND status='PENDING'",
                        ("APPROVED" if approved else "REJECTED", approver, now(), comment, approval_id))

    @staticmethod
    def _approval(row: Any) -> dict[str, Any] | None:
        if not row:
            return None
        d = dict(row)
        d["arguments"] = json.loads(d["arguments"])
        return d


def _alive(pid: int) -> bool:
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
