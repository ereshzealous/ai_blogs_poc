"""The evidence store: append-only governance events, hash-chained, anchored outside the store.

    event_hash = sha256(prev_hash || canonical(event without its hash fields))

Every process that writes evidence (both agent runtimes of a scenario, across restarts) appends to one SQLite database
under BEGIN IMMEDIATE, so the chain is a single total order even with concurrent writers.  When an execution completes,
its chain head is written to a separate witness file (standing in for WORM storage or a transparency log the runtime
cannot rewrite).  A hash chain alone proves that no event was edited *unless the whole chain was recomputed*; the anchor
is what catches a recomputed chain.  Both checks are in verify().

What may be recorded is decided by a schema, not by the caller: every event type has an allow-list of payload fields,
anything else is refused, and values that look like credentials are refused outright.  Raw prompts, retrieved documents
and model reasoning are never payload fields; their digests are.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .common import canon, load, now_iso, sha

GENESIS = "0" * 64
RETENTION = load("retention.toml")

# payload allow-list per event type
SCHEMA: dict[str, set[str]] = {
    "execution.started": {"trigger", "invoker", "on_behalf_of", "incident", "severity", "service", "agent_version", "workload",
                          "pins", "background"},
    "execution.completed": {"outcome", "reason", "mitigated", "attempts", "mutations_observed"},
    "workflow.resumed": {"from_step", "previous_pid", "restored_trace", "in_flight"},
    "context.accessed": {"dataset", "classification", "decision", "reason", "content_digest", "requested_by"},
    "model.invoked": {"provider", "model", "model_digest", "prompt_template", "prompt_template_digest", "agent_config",
                      "options", "input_digest", "input_tokens", "output_tokens", "latency_ms", "finish_reason", "replayed",
                      "structured_output"},
    "decision.proposed": {"capability", "target", "arguments", "rationale_summary", "action_digest", "source"},
    "policy.evaluated": {"policy_evaluation_id", "policy_id", "policy_version", "policy_digest", "decision", "rule", "reason",
                         "obligations", "attributes", "action_digest"},
    "approval.requested": {"approval_id", "action_digest", "scope", "eligible_roles", "quorum", "expires_at", "policy_evaluation_id"},
    "approval.decided": {"approval_id", "approver", "role", "decision", "reason", "decided_at", "signature_valid", "digest_match"},
    "gateway.denied": {"capability", "target", "reason", "catalog", "policy_evaluation_id", "path"},
    "action.authorized": {"capability", "target", "arguments", "catalog", "tool_identity", "credential_audience", "idempotency_key",
                          "policy_evaluation_id", "approval_ids", "action_digest"},
    "attempt.started": {"attempt", "request_id", "idempotency_key", "endpoint"},
    "attempt.finished": {"attempt", "result", "http_status", "external_transaction_id", "replayed", "latency_ms", "error",
                         "claimed_status"},
    "attempt.reconciled": {"attempt", "result", "external_transaction_id", "method"},
    "effect.verified": {"verified", "expected", "observed_before", "observed_after", "revision_delta", "transactions_for_key",
                        "source", "observed_at", "health"},
}

SECRET = re.compile(r"(dpl_live_[A-Za-z0-9]+|Bearer\s+\S+|-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:\d{4}[- ]){3}\d{4}\b)")


class EvidenceRefused(ValueError):
    pass


def _check(event_type: str, payload: dict[str, Any]) -> None:
    allowed = SCHEMA.get(event_type)
    if allowed is None:
        raise EvidenceRefused(f"unknown event type {event_type}")
    extra = set(payload) - allowed
    if extra:
        raise EvidenceRefused(f"{event_type}: fields not in the evidence schema: {sorted(extra)}")
    if SECRET.search(canon(payload)):
        raise EvidenceRefused(f"{event_type}: a value looks like a credential or card number; evidence refuses it")
    if event_type not in RETENTION["event_types"]:
        raise EvidenceRefused(f"{event_type}: no retention class")


class EvidenceStore:
    COLS = ("seq", "event_id", "execution_id", "trace_id", "span_id", "workflow_id", "action_id", "attempt_id", "event_type",
            "occurred_at", "principal", "agent_id", "classification", "retention_class", "payload_json", "prev_hash", "event_hash")

    def __init__(self, path: Path, witness: Path) -> None:
        self.path, self.witness = path, witness
        path.parent.mkdir(parents=True, exist_ok=True)
        witness.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(f"CREATE TABLE IF NOT EXISTS evidence_events ({', '.join(c + (' INTEGER PRIMARY KEY' if c == 'seq' else ' TEXT') for c in self.COLS)})")

    def append(self, event_type: str, *, execution_id: str, trace_id: str | None, span_id: str | None, workflow_id: str,
               principal: str, agent_id: str, payload: dict[str, Any], action_id: str | None = None,
               attempt_id: str | None = None, classification: str = "INTERNAL") -> dict[str, Any]:
        _check(event_type, payload)
        row: dict[str, Any] = {
            "execution_id": execution_id, "trace_id": trace_id, "span_id": span_id, "workflow_id": workflow_id,
            "action_id": action_id, "attempt_id": attempt_id, "event_type": event_type, "occurred_at": now_iso(),
            "principal": principal, "agent_id": agent_id, "classification": classification,
            "retention_class": RETENTION["event_types"][event_type], "payload_json": canon(payload),
        }
        self.db.execute("BEGIN IMMEDIATE")
        try:
            last = self.db.execute("SELECT seq, event_hash FROM evidence_events ORDER BY seq DESC LIMIT 1").fetchone()
            seq, prev = (last[0] + 1, last[1]) if last else (1, GENESIS)
            row["seq"] = seq
            row["event_id"] = f"ev-{seq:05d}-{sha(row)[:6]}"
            row["prev_hash"] = prev
            row["event_hash"] = event_hash(row)
            self.db.execute(f"INSERT INTO evidence_events ({', '.join(self.COLS)}) VALUES ({', '.join('?' * len(self.COLS))})",
                            [row[c] for c in self.COLS])
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return row

    def anchor(self, execution_id: str) -> dict:
        seq, h = self.db.execute("SELECT seq, event_hash FROM evidence_events ORDER BY seq DESC LIMIT 1").fetchone()
        rec = {"anchored_at": now_iso(), "execution_id": execution_id, "seq": seq, "head_hash": h}
        with open(self.witness, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
        return rec

    def events(self, execution_id: str | None = None) -> list[dict]:
        q = f"SELECT {', '.join(self.COLS)} FROM evidence_events" + (" WHERE execution_id=?" if execution_id else "") + " ORDER BY seq"
        return [dict(zip(self.COLS, r)) for r in self.db.execute(q, (execution_id,) if execution_id else ())]


def event_hash(row: dict) -> str:
    body = {k: row[k] for k in EvidenceStore.COLS if k not in ("event_hash", "prev_hash")}
    return sha(row["prev_hash"] + canon(body))


def verify(rows: list[dict], anchors: list[dict]) -> dict:
    """Recompute the chain; then check every anchored head against the recomputed chain."""
    problems, prev = [], GENESIS
    by_seq = {}
    for i, r in enumerate(rows):
        if r["seq"] != i + 1:
            problems.append({"seq": r["seq"], "problem": f"sequence gap: expected {i + 1}"})
        if r["prev_hash"] != prev:
            problems.append({"seq": r["seq"], "problem": "prev_hash does not match the previous event"})
        if event_hash(r) != r["event_hash"]:
            problems.append({"seq": r["seq"], "problem": "event_hash does not match the event's content"})
        prev = r["event_hash"]
        by_seq[r["seq"]] = r["event_hash"]
    anchor_problems = []
    for a in anchors:
        h = by_seq.get(a["seq"])
        if h is None:
            anchor_problems.append({"seq": a["seq"], "problem": "anchored event is missing (truncated chain)"})
        elif h != a["head_hash"]:
            anchor_problems.append({"seq": a["seq"], "problem": "chain head differs from the external anchor (chain rewritten)"})
    return {"events": len(rows), "anchors": len(anchors), "chain_ok": not problems, "anchors_ok": not anchor_problems,
            "intact": not problems and not anchor_problems, "first_problem": (problems + anchor_problems)[:1],
            "problems": len(problems) + len(anchor_problems)}


def load_rows(path: Path) -> list[dict]:
    db = sqlite3.connect(path)
    rows = [dict(zip(EvidenceStore.COLS, r)) for r in db.execute(f"SELECT {', '.join(EvidenceStore.COLS)} FROM evidence_events ORDER BY seq")]
    db.close()
    return rows
