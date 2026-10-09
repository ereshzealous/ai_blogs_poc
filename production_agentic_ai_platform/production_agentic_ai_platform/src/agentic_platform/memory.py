"""Episodic memory writes are governance events.

A write is allowed only for a permitted kind, with the required provenance (a verified outcome, the workflow, the trace,
the evidence it rests on), tenant-scoped, with an expiry, and without forbidden content.  Every attempt, allowed or not,
is recorded.  Memory is recall with provenance; it never overrides the systems of record.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from agentic_platform.canonical import stable_id


class MemoryService:
    def __init__(self, store, policy: dict[str, Any], evidence):
        self.s, self.p, self.ev = store, policy["memory"]["episodic_write"], evidence

    def write(self, *, tenant: str, kind: str, text: str, provenance: dict[str, Any], workflow_id: str) -> dict[str, Any]:
        why = []
        if kind not in self.p["allowed_kinds"]:
            why.append(f"kind {kind} not allowed")
        why += [f"missing provenance {k}" for k in self.p["require"] if not provenance.get(k)]
        why += [f"forbidden content {p}" for p in self.p["forbidden_patterns"] if re.search(p, text)]
        if why:
            rec = {"decision": "DENIED", "code": "MEMORY_WRITE_DENIED", "reasons": why, "kind": kind, "tenant": tenant}
            self.ev.record("memory.write", rec, workflow_id=workflow_id)
            return rec
        mid = stable_id("mem", tenant, workflow_id, text)
        exp = time.time() + self.p["ttl_days"] * 86400
        self.s.db.execute("INSERT INTO memory VALUES (?,?,?,?,?,?,?)", (mid, tenant, kind, text, json.dumps(provenance), time.time(), exp))
        rec = {"decision": "WRITTEN", "id": mid, "kind": kind, "tenant": tenant, "ttl_days": self.p["ttl_days"], "provenance": provenance}
        self.ev.record("memory.write", rec, workflow_id=workflow_id)
        return rec
