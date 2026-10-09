"""Operation identity for side effects.

A write is identified by op_id = sha256(workflow_id | step | capability | canonical arguments).  The same logical
action in the same workflow step always gets the same op_id, in any process, before or after a crash.  The op_id is
sent to the backend as its idempotency key, and the platform records the operation's state:

    IN_FLIGHT  sent, no answer yet (or the process died waiting)
    UNKNOWN    the call timed out: it may or may not have happened
    COMPLETED  the backend answered; the stored result is returned to every later attempt
    FAILED     the backend refused it

This gives effectively-once execution *when the backend honours the key*.  It is not exactly-once networking.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import Any


def op_id(workflow_id: str, step: str, capability: str, args: dict[str, Any]) -> str:
    canon = json.dumps(args, sort_keys=True, separators=(",", ":"))
    return "op-" + hashlib.sha256(f"{workflow_id}|{step}|{capability}|{canon}".encode()).hexdigest()[:24]


class OperationConflict(RuntimeError):
    pass


class Operations:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def begin(self, op: str, workflow_id: str, capability: str, args: dict[str, Any]) -> dict[str, Any] | None:
        """Returns the stored result if the operation already completed; otherwise marks an attempt IN_FLIGHT."""
        sha = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()
        now = time.time()
        row = self.db.execute("SELECT * FROM operations WHERE op_id=?", (op,)).fetchone()
        if row:
            if row["args_sha"] != sha:
                raise OperationConflict(f"{op} reused with different arguments")
            if row["state"] == "COMPLETED":
                return json.loads(row["result"])
            self.db.execute("UPDATE operations SET state='IN_FLIGHT', attempts=attempts+1, updated=? WHERE op_id=?", (now, op))
        else:
            self.db.execute("INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,?,?)", (op, workflow_id, capability, sha, "IN_FLIGHT", 1, None, None, now, now))
        return None

    def finish(self, op: str, state: str, result: Any = None, error: str | None = None) -> None:
        self.db.execute("UPDATE operations SET state=?, result=?, error=?, updated=? WHERE op_id=?",
                        (state, json.dumps(result, default=str) if result is not None else None, error, time.time(), op))

    def get(self, op: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM operations WHERE op_id=?", (op,)).fetchone()
        return dict(row) if row else None
