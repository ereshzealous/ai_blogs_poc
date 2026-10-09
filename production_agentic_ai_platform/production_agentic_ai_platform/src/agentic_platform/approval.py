"""Human approval as an authorization artifact, bound to one exact invocation.

The approver is shown the canonical action and its digest.  The decision record binds approver, decision and digest and is
HMAC-signed by the approval service.  At execution time the platform recomputes the digest of the invocation it is about
to run and compares it with the approved digest: any change to a bound field (target version, service, environment,
workflow, requester, agent...) is APPROVAL_DIGEST_MISMATCH.  The human approved an action, not an agent session.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

from agentic_platform.canonical import canonical_json, invocation_digest, stable_id
from agentic_platform.store import Store


class ApprovalError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def _sig(key: bytes, approval_id: str, digest: str, approver: str, decision: str, expires_at: float) -> str:
    msg = canonical_json([approval_id, digest, approver, decision, int(expires_at)])
    return hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()


class ApprovalService:
    def __init__(self, store: Store, key: bytes, policy: dict[str, Any], users: dict[str, Any]):
        self.s, self.key, self.p, self.users = store, key, policy["approval"], users

    def request(self, workflow_id: str, inv: dict[str, Any], requested_by: str, decision_id: str) -> dict[str, Any]:
        n = self.s.q("SELECT COUNT(*) FROM approvals WHERE workflow_id=?", workflow_id)[0][0]
        aid = stable_id("apr", workflow_id, invocation_digest(inv), n)
        digest = invocation_digest(inv)
        with self.s.db:
            self.s.db.execute("INSERT INTO approvals (id, workflow_id, digest, canonical, requested_by, requested_at, status, decision_id) VALUES (?,?,?,?,?,?,?,?)",
                              (aid, workflow_id, digest, canonical_json(inv), requested_by, time.time(), "PENDING", decision_id))
        return {"approval_id": aid, "digest": digest, "canonical": canonical_json(inv), "status": "PENDING"}

    def decide(self, approval_id: str, approver: str, decision: str, shown_digest: str) -> dict[str, Any]:
        """The approver's client shows the canonical action; the decision names the digest the human actually saw."""
        row = self.s.q("SELECT digest, requested_by FROM approvals WHERE id=?", approval_id)
        if not row:
            raise ApprovalError("APPROVAL_UNKNOWN", approval_id)
        digest, requested_by = row[0]
        if shown_digest != digest:
            raise ApprovalError("APPROVAL_DIGEST_MISMATCH", "the approver was shown a different action than the one requested")
        if self.p["separation_of_duties"] and approver == requested_by:   # whatever roles the requester holds
            raise ApprovalError("SELF_APPROVAL", f"{approver} requested this action")
        u = self.users.get(approver)
        if not u or self.p["approver_role"] not in u["roles"]:
            raise ApprovalError("APPROVER_NOT_AUTHORIZED", f"{approver} does not hold {self.p['approver_role']}")
        expires = time.time() + self.p["ttl_s"]
        sig = _sig(self.key, approval_id, digest, approver, decision, expires)
        with self.s.db:
            self.s.db.execute("UPDATE approvals SET status=?, approver=?, decided_at=?, expires_at=?, signature=? WHERE id=?",
                              (decision, approver, time.time(), expires, sig, approval_id))
        return self.get(approval_id)

    def get(self, approval_id: str) -> dict[str, Any]:
        cols = ["id", "workflow_id", "digest", "canonical", "requested_by", "requested_at", "status", "approver", "decided_at", "expires_at", "signature", "decision_id"]
        row = self.s.q("SELECT " + ", ".join(cols) + " FROM approvals WHERE id=?", approval_id)
        if not row:
            raise ApprovalError("APPROVAL_UNKNOWN", approval_id)
        return dict(zip(cols, row[0]))

    def validate(self, approval: dict[str, Any], inv: dict[str, Any], agent: str) -> str:
        """Everything that must still be true at execution time.  Returns the digest that was checked."""
        actual = invocation_digest(inv)
        if approval["status"] != "APPROVED":
            raise ApprovalError("APPROVAL_NOT_GRANTED", approval["status"])
        want = _sig(self.key, approval["id"], approval["digest"], approval["approver"], approval["status"], approval["expires_at"])
        if not approval.get("signature") or not hmac.compare_digest(approval["signature"], want):
            raise ApprovalError("APPROVAL_SIGNATURE_INVALID", "decision record does not verify")
        if time.time() >= approval["expires_at"]:
            raise ApprovalError("APPROVAL_EXPIRED")
        if approval["approver"] in (inv["on_behalf_of"], agent):
            raise ApprovalError("SELF_APPROVAL")
        if actual != approval["digest"]:
            raise ApprovalError("APPROVAL_DIGEST_MISMATCH", f"approved {approval['digest'][:16]}…, executing {actual[:16]}…")
        return actual
