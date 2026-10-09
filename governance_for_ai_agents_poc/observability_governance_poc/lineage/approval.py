"""The approval service: durable approval requests bound to one exact action, decisions signed by the service.

An approval request carries the digest of the action it covers (capability, target, arguments, incident, policy evaluation).
A decision is signed (HMAC) by the approval service over (approval_id, action digest, approver, decision), and only for a
principal the directory says holds an eligible role.  The runtime checks, before it acts, that every approval it relies on
is signed, eligible and bound to the digest of the action it is about to execute.  An approval copied from another action
fails that check (tests/test_approval_binding.py).

State lives in its own SQLite database (state/approvals.db), outside the agent runtime, so a runtime that is SIGKILLed while
waiting reads the request and its decisions back instead of asking again.
"""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
from pathlib import Path

from .common import AppLog, canon, load, now_iso, sha, short

SERVICE_KEY = b"approval-service-signing-key"      # held by the approval service only
PEOPLE = load("principals.toml")["people"]


def action_digest(action: dict, incident: str, policy_evaluation_id: str) -> str:
    return "sha256:" + sha({"action": {k: action.get(k) for k in ("capability", "service", "environment", "to_version")},
                            "incident": incident, "policy_evaluation_id": policy_evaluation_id})


def sign(approval_id: str, digest: str, approver: str, decision: str) -> str:
    return hmac.new(SERVICE_KEY, canon([approval_id, digest, approver, decision]).encode(), hashlib.sha256).hexdigest()


def role_of(person: str, eligible: list[str], service: str) -> str | None:
    for r in PEOPLE.get(person, {}).get("roles", []):
        base, _, scope = r.partition(":")
        if base in eligible and (not scope or scope == service):
            return base
    return None


class ApprovalService:
    def __init__(self, sdir: Path) -> None:
        self.db = sqlite3.connect(sdir / "state" / "approvals.db", timeout=30, isolation_level=None)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS requests (approval_id TEXT PRIMARY KEY, incident TEXT, service TEXT, action_text TEXT, action_digest TEXT,
            eligible_roles TEXT, quorum INTEGER, expires_at TEXT, policy_evaluation_id TEXT, requested_by TEXT, requested_at TEXT, state TEXT);
        CREATE TABLE IF NOT EXISTS decisions (approval_id TEXT, approver TEXT, role TEXT, decision TEXT, reason TEXT, decided_at TEXT,
            action_digest TEXT, signature TEXT, PRIMARY KEY (approval_id, approver));
        """)
        self.log = AppLog(sdir, "approval-service", "approvals 1.9.0")

    def request(self, execution_id: str, incident: str, action: dict, digest: str, obligations: dict, pe_id: str, requested_by: str) -> dict:
        aid = "apr-" + short([execution_id, digest], 8)
        text = f"{action['capability']} {action['service']} {action.get('to_version', '')} ({action['environment']})".strip()
        self.db.execute("INSERT OR IGNORE INTO requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, incident, action["service"], text, digest, ",".join(obligations["approver_roles"]), obligations["quorum"],
                         f"+{obligations['expires_in_s']}s", pe_id, requested_by, now_iso(), "PENDING"))
        self.log("INFO", "approval requested", approval_id=aid, incident=incident, action=text, quorum=obligations["quorum"],
                 eligible=obligations["approver_roles"])
        return {"approval_id": aid, "action_text": text}

    def pending(self) -> list[dict]:
        cols = ("approval_id", "incident", "service", "action_text", "action_digest", "eligible_roles", "quorum")
        return [dict(zip(cols, r)) for r in self.db.execute(f"SELECT {', '.join(cols)} FROM requests WHERE state='PENDING'")]

    def decide(self, approval_id: str, approver: str, decision: str, reason: str) -> dict:
        """Called on behalf of an authenticated human (SSO + WebAuthn, simulated).  Refuses ineligible people."""
        req = self.db.execute("SELECT action_digest, eligible_roles, quorum, service FROM requests WHERE approval_id=?", (approval_id,)).fetchone()
        digest, eligible, quorum, service = req
        role = role_of(approver, eligible.split(","), service)
        if role is None:
            self.log("WARN", "decision refused: approver not eligible", approval_id=approval_id, approver=approver)
            return {"refused": True}
        sig = sign(approval_id, digest, approver, decision)
        self.db.execute("INSERT OR IGNORE INTO decisions VALUES (?,?,?,?,?,?,?,?)",
                        (approval_id, approver, role, decision, reason, now_iso(), digest, sig))
        decs = self.decisions(approval_id)
        state = "REJECTED" if any(d["decision"] == "REJECTED" for d in decs) else (
            "APPROVED" if len({d["role"] for d in decs if d["decision"] == "APPROVED"}) >= quorum else "PENDING")
        self.db.execute("UPDATE requests SET state=? WHERE approval_id=?", (state, approval_id))
        self.log("INFO", "decision recorded", approval_id=approval_id, approver=approver, role=role, decision=decision, state=state)
        return {"state": state}

    def decisions(self, approval_id: str) -> list[dict]:
        cols = ("approval_id", "approver", "role", "decision", "reason", "decided_at", "action_digest", "signature")
        return [dict(zip(cols, r)) for r in self.db.execute(f"SELECT {', '.join(cols)} FROM decisions WHERE approval_id=? ORDER BY decided_at", (approval_id,))]

    def state(self, approval_id: str) -> str:
        return self.db.execute("SELECT state FROM requests WHERE approval_id=?", (approval_id,)).fetchone()[0]


def check(decision: dict, expected_digest: str) -> dict:
    """What the runtime verifies before it relies on a decision."""
    sig_ok = hmac.compare_digest(decision["signature"], sign(decision["approval_id"], decision["action_digest"], decision["approver"], decision["decision"]))
    return {"signature_valid": sig_ok, "digest_match": decision["action_digest"] == expected_digest}
