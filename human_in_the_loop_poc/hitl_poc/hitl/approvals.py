"""The approval service: approval requests as a real state machine, and decisions bound to an action digest.

States (the article's state machine)
    PROPOSED → POLICY_EVALUATED → REJECTED (policy DENY) · EXECUTING (ALLOW) · PENDING_APPROVAL (REQUIRE_APPROVAL)
    PENDING_APPROVAL → APPROVED | DENIED | EXPIRED | CANCELED      (→ PENDING_APPROVAL: escalated, or 1 of 2 approvals)
    APPROVED → REVALIDATING → EXECUTING | REAPPROVAL_REQUIRED | REJECTED | EXPIRED
    EXECUTING → SUCCEEDED | FAILED          FAILED (retryable) → REVALIDATING  (a retry is revalidated like a resume)

Every transition is a compare-and-set on the current state, so two racing requests cannot both win and an illegal
transition (DENIED → APPROVED, EXPIRED → EXECUTING, SUCCEEDED → REVALIDATING …) fails instead of happening.  Entering
REVALIDATING is the single-use consumption of an approval: only one worker can move it out of APPROVED.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from hitl.base import AuditLog, Clock, Directory, canonical, connect, short_id
from hitl.contracts import ActionProposal, ApprovalArtifact, ApprovalDecision, Approver, DecisionRequest
from hitl.policy import PolicyEngine

TRANSITIONS: dict[str, set[str]] = {
    "PROPOSED": {"POLICY_EVALUATED"},
    "POLICY_EVALUATED": {"PENDING_APPROVAL", "EXECUTING", "REJECTED"},
    "PENDING_APPROVAL": {"PENDING_APPROVAL", "APPROVED", "DENIED", "EXPIRED", "CANCELED"},
    "APPROVED": {"REVALIDATING", "EXPIRED", "CANCELED"},
    "REVALIDATING": {"EXECUTING", "REAPPROVAL_REQUIRED", "REJECTED", "EXPIRED"},
    "EXECUTING": {"SUCCEEDED", "FAILED"},
    "FAILED": {"REVALIDATING"},              # only through ExecutionGate.retry and its rules
    "SUCCEEDED": set(), "DENIED": set(), "REJECTED": set(), "EXPIRED": set(), "CANCELED": set(), "REAPPROVAL_REQUIRED": set(),
}
TERMINAL = {k for k, v in TRANSITIONS.items() if not v}


class IllegalTransition(Exception):
    pass


class ServiceUnavailable(Exception):
    pass


class DecisionRefused(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


class ApprovalService:
    def __init__(self, path, clock: Clock, directory: Directory, policy: PolicyEngine, audit: AuditLog):
        self.db = connect(path)
        self.clock, self.directory, self.policy, self.audit = clock, directory, policy, audit
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, correlation_id TEXT, state TEXT, body TEXT, version INTEGER,
                failure TEXT, created REAL, updated REAL);
            CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, proposal_id TEXT, body TEXT, request_key TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS transitions (n INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT, src TEXT, dst TEXT, by TEXT, t REAL, note TEXT);
        """)
        self.available = True
        self.after_read: Callable[[str], None] | None = None     # test hook: interleave two racing decisions deterministically
        # The safeguard a negative control removes: the approver is the AUTHENTICATED principal.  With it off, the service
        # believes an identity claimed in the request (the naive design a model could exploit).
        self.authenticate_approver = True

    def _up(self) -> None:
        if not self.available:
            raise ServiceUnavailable("approval service unreachable")

    # ---- proposals ---------------------------------------------------------------------------------------------------
    def create(self, p: ActionProposal) -> None:
        self._up()
        self.db.execute("INSERT INTO proposals VALUES (?,?,?,?,?,?,?,?)",
                        (p.proposal_id, p.correlation_id, "PROPOSED", p.model_dump_json(), 0, None, self.clock.now(), self.clock.now()))
        self.db.execute("INSERT INTO transitions (proposal_id, src, dst, by, t, note) VALUES (?,?,?,?,?,?)",
                        (p.proposal_id, None, "PROPOSED", p.requested_by.runtime, self.clock.now(), ""))

    def get(self, pid: str) -> dict[str, Any] | None:
        self._up()
        r = self.db.execute("SELECT id, correlation_id, state, body, version, failure FROM proposals WHERE id=?", (pid,)).fetchone()
        if not r:
            return None
        return {"id": r[0], "correlation_id": r[1], "state": r[2], "proposal": ActionProposal.model_validate_json(r[3]), "version": r[4],
                "failure": json.loads(r[5]) if r[5] else None}

    def list(self, state: str | None = None) -> list[dict[str, Any]]:
        self._up()
        q = "SELECT id FROM proposals" + (" WHERE state=?" if state else "") + " ORDER BY created, id"
        return [self.get(r[0]) for r in self.db.execute(q, (state,) if state else ())]

    def transition(self, pid: str, src: str, dst: str, by: str, failure: dict | None = None, note: str = "") -> None:
        """Compare-and-set.  Raises IllegalTransition when the move is not in the table or the state already moved."""
        self._up()
        if dst not in TRANSITIONS.get(src, set()):
            raise IllegalTransition(f"{src} → {dst} is not a legal transition")
        cur = self.db.execute("UPDATE proposals SET state=?, version=version+1, updated=?, failure=? WHERE id=? AND state=?",
                              (dst, self.clock.now(), json.dumps(failure) if failure else None, pid, src))
        if cur.rowcount != 1:
            now = self.db.execute("SELECT state FROM proposals WHERE id=?", (pid,)).fetchone()
            raise IllegalTransition(f"expected {src}, found {now[0] if now else 'nothing'}; {src} → {dst} refused")
        self.db.execute("INSERT INTO transitions (proposal_id, src, dst, by, t, note) VALUES (?,?,?,?,?,?)", (pid, src, dst, by, self.clock.now(), note))

    def mark_used(self, pid: str, by: str) -> None:
        """Arm B's single use: an unconditional write after the side effect ("used = true"), not a compare-and-set.
        Only the action-bound arm calls it; it is the design that experiment H7 tests against the atomic consume."""
        src = self.db.execute("SELECT state FROM proposals WHERE id=?", (pid,)).fetchone()[0]
        self.db.execute("UPDATE proposals SET state='SUCCEEDED', version=version+1, updated=? WHERE id=?", (self.clock.now(), pid))
        self.db.execute("INSERT INTO transitions (proposal_id, src, dst, by, t, note) VALUES (?,?,?,?,?,?)",
                        (pid, src, "SUCCEEDED", by, self.clock.now(), "marked used after the call (no compare-and-set)"))

    def history(self, pid: str) -> list[tuple[str | None, str, str]]:
        return [(r[0], r[1], r[2]) for r in self.db.execute("SELECT src, dst, by FROM transitions WHERE proposal_id=? ORDER BY n", (pid,))]

    def transitions(self, pid: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT proposal_id, src, dst, by, t, note FROM transitions" + (" WHERE proposal_id=?" if pid else "") + " ORDER BY n"
        return [{"proposal_id": r[0], "src": r[1], "dst": r[2], "by": r[3], "t": r[4], "note": r[5]} for r in self.db.execute(q, (pid,) if pid else ())]

    def expire_due(self) -> list[str]:
        out = []
        for rec in self.list("PENDING_APPROVAL") + self.list("APPROVED"):
            if self.clock.now() > rec["proposal"].expires_at:
                self.transition(rec["id"], rec["state"], "EXPIRED", "svc.hitl-runtime", note="no usable decision before expires_at")
                self.audit.record("proposal.expired", rec["correlation_id"], rec["id"], state_before=rec["state"])
                out.append(rec["id"])
        return out

    def escalate_due(self) -> list[str]:
        """No decision within escalate_after_s: route the request to the secondary on-call.  A traceable transition."""
        out = []
        for rec in self.list("PENDING_APPROVAL"):
            p, after = rec["proposal"], float(self.policy.approval.get("escalate_after_s", 0) or 0)
            done = any(t["note"].startswith("escalated") for t in self.transitions(rec["id"]))
            if after and not done and self.clock.now() >= p.created_at + after and self.clock.now() <= p.expires_at:
                to = self.directory.oncall("secondary")
                self.transition(rec["id"], "PENDING_APPROVAL", "PENDING_APPROVAL", "policy.escalation", note=f"escalated to {to}")
                self.audit.record("approval.escalated", rec["correlation_id"], rec["id"], escalated_from=self.directory.oncall("primary"), escalated_to=to,
                                  after_s=after)
                out.append(rec["id"])
        return out

    def cancel(self, pid: str, by: str, reason: str) -> None:
        rec = self.get(pid)
        self.transition(pid, rec["state"], "CANCELED", by)
        self.audit.record("proposal.canceled", rec["correlation_id"], pid, by=by, reason=reason)

    # ---- eligibility -------------------------------------------------------------------------------------------------
    def eligibility(self, who: str, p: ActionProposal) -> tuple[int, str] | str:
        """Refusal (status, reason) or, when eligible, the role and relationship that make `who` eligible."""
        chain = {p.requested_by.agent_id, p.requested_by.runtime, p.requested_by.invoker, p.acting_on_behalf_of.id}
        if who in chain:
            return (403, f"{who} is in the request chain; a requester cannot approve its own proposal")
        if self.directory.kind(who) != "human":
            return (403, f"{who} is a {self.directory.kind(who)}; only an authenticated human can decide")
        role = self.policy.approval["required_role"]
        if role not in self.directory.roles(who):
            return (403, f"{who} lacks role {role}")
        if "deployment_author" in self.policy.approval["separation_of_duties"] and p.context.get("deployment_author") == who:
            return (403, f"separation of duties: {who} authored the deployment this action reverts")
        return f"role {role}; not in the request chain; not the author of {p.preconditions.get('current_version', 'the change')}"

    # ---- decisions ---------------------------------------------------------------------------------------------------
    def decisions(self, pid: str) -> list[ApprovalDecision]:
        return [ApprovalDecision.model_validate_json(r[0]) for r in self.db.execute("SELECT body FROM decisions WHERE proposal_id=? ORDER BY rowid", (pid,))]

    def decision_for(self, pid: str) -> ApprovalDecision | None:
        ds = self.decisions(pid)
        return ds[-1] if ds else None

    def artifact(self, pid: str) -> ApprovalArtifact | None:
        rec, d = self.get(pid), self.decision_for(pid)
        return ApprovalArtifact.build(rec["proposal"], d) if rec and d else None

    def decide(self, pid: str, credential: str | None, req: DecisionRequest, claimed_approver: str | None = None,
               channel: str = "api") -> ApprovalDecision:
        """Authenticate the approver from the credential, then decide.  `claimed_approver` (a request body, model output) is
        recorded and ignored, unless the negative control has switched authentication off."""
        self._up()
        try:
            who = self.directory.authenticate(credential)
        except Exception:
            raise DecisionRefused(401, "unauthenticated")
        if claimed_approver and claimed_approver != who:
            if self.authenticate_approver:
                self.audit.record("approval.claim_ignored", None, pid, authenticated=who, claimed=claimed_approver)
            else:
                who = claimed_approver
        return self.decide_as(pid, who, req, channel)

    def decide_as(self, pid: str, who: str, req: DecisionRequest, channel: str = "api") -> ApprovalDecision:
        """Decide as an already authenticated enterprise principal (the inbox, or a chat click mapped to a principal)."""
        self._up()
        rec = self.get(pid)
        if rec is None:
            raise DecisionRefused(404, "no such proposal")
        p: ActionProposal = rec["proposal"]
        key = req.request_id or short_id("dreq", pid, who, req.decision, req.action_digest, len(self.decisions(pid)))
        seen = self.db.execute("SELECT body FROM decisions WHERE request_key=?", (key,)).fetchone()
        if seen:                                           # the same request delivered again: same answer, no new decision
            self.audit.record("approval.duplicate", rec["correlation_id"], pid, approver=who, request_key=key)
            return ApprovalDecision.model_validate_json(seen[0])
        if self.after_read:
            self.after_read(who)
        refuse = self._refusal(rec, who, req)
        if isinstance(refuse, tuple):
            self.audit.record("approval.refused", rec["correlation_id"], pid, approver=who, decision=req.decision, status=refuse[0],
                              reason=refuse[1], channel=channel)
            raise DecisionRefused(*refuse)
        need = max(1, p.policy.required_approvals or 1)
        have = {d.approver.identity for d in self.decisions(pid) if d.decision == "approve"}
        if req.decision == "deny":
            dst, note = "DENIED", ""
        elif len(have | {who}) >= need:
            dst, note = "APPROVED", (f"approval {len(have) + 1} of {need}" if need > 1 else "")
        else:
            dst, note = "PENDING_APPROVAL", f"approval {len(have) + 1} of {need}"
        try:
            self.transition(pid, "PENDING_APPROVAL", dst, who, note=note)
        except IllegalTransition as e:
            self.audit.record("approval.refused", rec["correlation_id"], pid, approver=who, decision=req.decision, status=409, reason=str(e))
            raise DecisionRefused(409, str(e))
        d = ApprovalDecision(approval_id=short_id("apr", pid, who, req.decision), proposal_id=pid, action_digest=p.action_digest,
                             decision=req.decision, approver=Approver(identity=who, roles=self.directory.roles(who), eligible_because=refuse),
                             decided_at=self.clock.now(), reason=req.reason, channel=channel)
        self.db.execute("INSERT INTO decisions VALUES (?,?,?,?)", (d.approval_id, pid, d.model_dump_json(), key))
        self.audit.record("approval.decided", rec["correlation_id"], pid, approval_id=d.approval_id, approver=who, roles=d.approver.roles,
                          eligible_because=refuse, decision=req.decision, action_digest=p.action_digest, reason=req.reason, channel=channel,
                          state_after=dst, approvals=f"{len(have | {who}) if req.decision == 'approve' else len(have)} of {need}")
        if dst == "APPROVED":
            self.audit.record("approval.artifact", rec["correlation_id"], pid, **ApprovalArtifact.build(p, d).model_dump())
        return d

    def _refusal(self, rec: dict[str, Any], who: str, req: DecisionRequest) -> tuple[int, str] | str:
        p: ActionProposal = rec["proposal"]
        if rec["state"] != "PENDING_APPROVAL":
            return (409, f"proposal is {rec['state']}; only PENDING_APPROVAL can be decided")
        if self.clock.now() > p.expires_at:
            self.transition(rec["id"], "PENDING_APPROVAL", "EXPIRED", "svc.hitl-runtime", note="decision arrived after expires_at")
            return (409, "proposal expired before the decision")
        if req.action_digest != p.action_digest:
            return (409, "digest mismatch: the decision is not about the action awaiting approval")
        el = self.eligibility(who, p)
        if isinstance(el, tuple):
            return el
        if req.decision == "approve" and who in {d.approver.identity for d in self.decisions(rec["id"]) if d.decision == "approve"}:
            return (409, f"{who} already approved; the policy needs distinct approvers")
        return el


def proposal_digest_view(p: ActionProposal) -> str:
    return canonical(p.action().model_dump())
