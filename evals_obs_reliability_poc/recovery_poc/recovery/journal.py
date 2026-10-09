"""The workflow store (SQLite): what must survive a crash so that recovery preserves semantics, not just position.

Checkpointing `current_step = 6` tells a resumed worker where it was.  It does not tell it whether the credit at step 6
was sent, executed, answered or lost.  So the classified runtime records, per operation:

  intent   written BEFORE dispatch: operation id, idempotency key, request deadline, matrix version, trace context
  result   written AFTER the outcome is known: certainty, external id, the provider's response, the rule that decided
  events   every observed fact (request_sent, response_received, ...), failure event and recovery decision

The baseline arms use the same store with less in it (A0: the step index; A1: the step index and operation id), which is
what their checkpoints hold in practice.  A write failure is injectable per (kind, tool) for S22 / S23.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .common import canon


class JournalWriteError(Exception):
    """The workflow store refused a write (disk full)."""


SCHEMA = """
create table if not exists run (run_id text primary key, scenario text, arm text, case_id text, trace_id text, status text,
                               matrix_version text, workers integer, last_span text, last_worker text);
create table if not exists checkpoint (run_id text, seq integer, step text, data text);
create table if not exists intent (op_id text primary key, run_id text, step text, tool text, idempotency_key text,
                                   deadline_ms real, request text, trace_id text, seq integer);
create table if not exists result (op_id text primary key, run_id text, step text, certainty text, external_id text,
                                   response text, rule text, seq integer);
create table if not exists event (run_id text, seq integer, worker text, kind text, step text, data text);
"""


class Journal:
    def __init__(self, path: Path, fail_writes: set[str] | None = None):
        self.path = path
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.executescript(SCHEMA)
        self.fail = set(fail_writes or ())          # {"intent:issue_credit", "result:issue_credit"}: fail the next such write once
        self.seq = self._max_seq()

    def _max_seq(self) -> int:
        row = self.db.execute("select max(seq) from (select seq from event union all select seq from checkpoint)").fetchone()
        return row[0] or 0

    def _next(self) -> int:
        self.seq += 1
        return self.seq

    def _maybe_fail(self, kind: str, tool: str) -> None:
        k = f"{kind}:{tool}"
        if k in self.fail:
            self.fail.discard(k)
            raise JournalWriteError(f"workflow store write failed: {k} (disk full)")

    # ---- run ----------------------------------------------------------------------------------------------------------------
    def open_run(self, run_id, scenario, arm, case_id, trace_id, matrix_version) -> dict:
        r = self.run(run_id)
        if r:
            self.db.execute("update run set workers = workers + 1 where run_id = ?", (run_id,))
            return self.run(run_id)
        self.db.execute("insert into run values (?,?,?,?,?,?,?,?,?,?)",
                        (run_id, scenario, arm, case_id, trace_id, "RUNNING", matrix_version, 1, None, None))
        return self.run(run_id)

    def run(self, run_id) -> dict | None:
        cur = self.db.execute("select * from run where run_id = ?", (run_id,))
        row = cur.fetchone()
        return dict(zip([c[0] for c in cur.description], row)) if row else None

    def set_run(self, run_id, **kv) -> None:
        for k, v in kv.items():
            self.db.execute(f"update run set {k} = ? where run_id = ?", (v, run_id))

    # ---- checkpoints (all arms) ----------------------------------------------------------------------------------------
    def checkpoint(self, run_id, step, data: dict, tool: str | None = None, kind: str | None = None) -> None:
        if tool and kind:
            self._maybe_fail(kind, tool)
        self.db.execute("insert into checkpoint values (?,?,?,?)", (run_id, self._next(), step, canon(data)))

    def last_checkpoint(self, run_id) -> dict | None:
        row = self.db.execute("select step, data from checkpoint where run_id = ? order by seq desc limit 1", (run_id,)).fetchone()
        return {"step": row[0], **json.loads(row[1])} if row else None

    # ---- intent / result (A2) ------------------------------------------------------------------------------------------
    def record_intent(self, run_id, step, tool, op_id, key, deadline_ms, request: dict, trace_id) -> None:
        self._maybe_fail("intent", tool)
        self.db.execute("insert or replace into intent values (?,?,?,?,?,?,?,?,?)",
                        (op_id, run_id, step, tool, key, deadline_ms, canon(request), trace_id, self._next()))

    def record_result(self, run_id, step, tool, op_id, certainty, external_id, response, rule) -> None:
        self._maybe_fail("result", tool)
        self.db.execute("insert or replace into result values (?,?,?,?,?,?,?,?)",
                        (op_id, run_id, step, certainty, external_id, canon(response), rule, self._next()))

    def intent(self, op_id) -> dict | None:
        cur = self.db.execute("select * from intent where op_id = ?", (op_id,))
        row = cur.fetchone()
        return dict(zip([c[0] for c in cur.description], row)) if row else None

    def result(self, op_id) -> dict | None:
        cur = self.db.execute("select * from result where op_id = ?", (op_id,))
        row = cur.fetchone()
        return dict(zip([c[0] for c in cur.description], row)) if row else None

    # ---- events --------------------------------------------------------------------------------------------------------
    def event(self, run_id, worker, kind, step, **data) -> None:
        self.db.execute("insert into event values (?,?,?,?,?,?)", (run_id, self._next(), worker, kind, step, canon(data)))

    def events(self, run_id) -> list[dict]:
        rows = self.db.execute("select seq, worker, kind, step, data from event where run_id = ? order by seq", (run_id,)).fetchall()
        return [{"seq": s, "worker": w, "kind": k, "step": st, **json.loads(d)} for s, w, k, st, d in rows]

    def dump(self) -> dict:
        out = {}
        for t in ("run", "checkpoint", "intent", "result", "event"):
            cur = self.db.execute(f"select * from {t} order by rowid")
            cols = [c[0] for c in cur.description]
            out[t] = [dict(zip(cols, r)) for r in cur.fetchall()]
        return out

    def close(self) -> None:
        self.db.close()
