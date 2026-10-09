"""Audit: an append-only, hash-chained record of consequential facts.

Observability (telemetry.py) answers "why is the system behaving this way?".  Audit answers "what action happened,
under whose authority, and what changed?".  Audit records are few, structured, and tamper-evident; spans are many,
sampled in production, and disposable.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from hai.config import Clock

GENESIS = "0" * 64


class AuditLog:
    def __init__(self, db, clock: Clock):
        self.db, self.clock = db, clock

    def record(self, kind: str, execution_id: str | None, correlation_id: str | None, /, **fields: Any) -> None:
        prev = self.db.execute("SELECT hash FROM audit ORDER BY n DESC LIMIT 1").fetchone()
        prev_h = prev["hash"] if prev else GENESIS
        body = json.dumps(fields, sort_keys=True, default=str)
        t = self.clock.now()
        h = hashlib.sha256(f"{prev_h}|{t}|{execution_id}|{correlation_id}|{kind}|{body}".encode()).hexdigest()
        self.db.execute("INSERT INTO audit (t, execution_id, correlation_id, kind, record, prev, hash) VALUES (?,?,?,?,?,?,?)",
                        (t, execution_id, correlation_id, kind, body, prev_h, h))
        self.db.commit()

    def records(self, execution_id: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM audit" + (" WHERE execution_id=?" if execution_id else "") + " ORDER BY n"
        return [dict(r) | {"record": json.loads(r["record"])} for r in self.db.execute(q, (execution_id,) if execution_id else ())]

    def verify(self) -> tuple[bool, int | None]:
        """Recompute the chain.  Returns (intact, first broken row)."""
        prev_h = GENESIS
        for r in self.db.execute("SELECT * FROM audit ORDER BY n"):
            h = hashlib.sha256(f"{prev_h}|{r['t']}|{r['execution_id']}|{r['correlation_id']}|{r['kind']}|{r['record']}".encode()).hexdigest()
            if r["prev"] != prev_h or r["hash"] != h:
                return False, r["n"]
            prev_h = r["hash"]
        return True, None

    def answer(self, execution_id: str) -> dict[str, Any]:
        """The seven audit questions for one execution, answered from audit records alone."""
        recs = self.records(execution_id)
        started = next((r["record"] for r in recs if r["kind"] == "execution.started"), {})
        calls = [r["record"] for r in recs if r["kind"] == "capability.call"]
        changes = [c for c in calls if c.get("kind") == "write" and c.get("status") == "ok"]
        approvals = [r["record"] for r in recs if r["kind"] == "approval.decided" and r["record"].get("accepted")]
        return {
            "what_happened": [f"{c['capability']} -> {c['status']}" for c in calls],
            "who_initiated": {"invoker": started.get("invoker"), "channel": started.get("channel"), "source": started.get("source"),
                              "on_behalf_of": started.get("on_behalf_of")},
            "which_identity_executed": {"agent": started.get("agent"), "workload": started.get("workload"), "token": started.get("token_id")},
            "capabilities_used": sorted({c["capability"] for c in calls}),
            "data_accessed": sorted({c["system"] for c in calls if c.get("kind") == "read" and c.get("status") == "ok"}),
            "what_changed": [{"capability": c["capability"], "arguments": c["arguments"], "effect": c.get("output")} for c in changes],
            "which_approval": [{"approval_id": a["approval_id"], "decided_by": a["decided_by"], "digest": a["digest"]} for a in approvals],
        }
