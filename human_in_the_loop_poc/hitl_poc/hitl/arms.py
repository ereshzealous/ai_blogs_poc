"""The three approval protocols compared by the experiments (the only variable; everything else is the same Platform).

    A · NaiveBoolean   approval_request_id + approved = true.  The chat click is the decision; whoever clicks is recorded by
                       their chat handle; no digest, no expiry, no single use.  Resume runs the agent's pending action if
                       the stored boolean is true.  The anti-pattern, and the control.
    B · ActionBound    the approval artifact: the decision is bound to request, action, resource, parameters and digest,
                       made by an authenticated, eligible enterprise principal, with an expiry.  Resume checks the artifact
                       (request, digest, expiry, unused), calls the tool, then marks the approval used.  It does not re-check
                       identity, delegation, policy, resource state or approver eligibility, and its single use is
                       read-check-call-mark (no atomic consume, no idempotency key).
    C · Revalidated    B's decision path, and on resume the execution gate in gate.py: atomic consume, revalidation of
                       identity, delegation, policy, resource state, approval validity and digest, an idempotency key, a
                       credential minted only after revalidation.

All three run behind the same capability gateway, which enforces the current policy decision on every call (Authorization
& Policy, held constant): a policy DENY is refused in every arm.  What differs is what satisfies REQUIRE_APPROVAL.

Interface (each arm):  request(pid) · click(pid, slack_user, decision, request_id) · api_decide(pid, credential, decision,
claimed) · resume(pid, mutate, runtime, recover) → GateResult · records(pid) → what this design keeps for an investigator.
"""

from __future__ import annotations

from typing import Any, Callable

from hitl.approvals import DecisionRefused
from hitl.base import AuthError, iso
from hitl.contracts import DecisionRequest, GateResult
from hitl.enterprise import ToolError
from hitl.gate import STANDING, WorkerCrash
from hitl.platform import Platform

ARMS = {"A": "Naive boolean", "B": "Action-bound", "C": "Revalidated protocol"}


class Arm:
    key = "?"

    def __init__(self, P: Platform):
        self.P = P
        self.after_read: Callable[[], None] | None = None

    # the chat adapter: what the human sees, and the click it sends back
    def message(self, pid: str) -> dict[str, Any]:
        raise NotImplementedError

    def request(self, pid: str) -> dict[str, Any]:
        """The approval request goes out over the chat channel.  Returns what the human is shown."""
        msg = self.message(pid)
        self.P.audit.record("channel.posted", self.P.approvals.get(pid)["correlation_id"], pid, arm=self.key, channel="slack", shown=msg)
        return msg

    def _ident(self, pid: str, runtime: str | None) -> tuple[Any, dict[str, str]]:
        p = self.P.approvals.get(pid)["proposal"]
        ident = dict(self.P.executions.get(p.correlation_id, {}).get("identity") or self.P.identity(p.requested_by.invoker))
        if runtime:
            ident["runtime"] = runtime
        return p, ident


# ======================================================================================================================
class NaiveBoolean(Arm):
    key = "A"

    def __init__(self, P: Platform):
        super().__init__(P)
        self.store: dict[str, dict[str, Any]] = {}          # approval_request_id -> {incident_id, approved, clicked_by, clicked_at}
        self.log: list[dict[str, Any]] = []                  # the application log a naive implementation writes

    def message(self, pid: str) -> dict[str, Any]:
        p = self.P.approvals.get(pid)["proposal"]
        self.store.setdefault(pid, {"approval_request_id": pid, "incident_id": p.incident_id, "approved": None, "clicked_by": None, "clicked_at": None})
        self.log.append({"event": "approval.requested", "approval_request_id": pid, "incident_id": p.incident_id, "requested_by": p.requested_by.agent_id,
                         "at": iso(self.P.clock.now())})
        return {"text": "Production rollback requested.", "buttons": ["Approve", "Deny"]}

    def click(self, pid: str, slack_user: str, decision: str = "approve", request_id: str | None = None) -> dict[str, Any]:
        rec = self.store[pid]
        rec.update(approved=decision == "approve", clicked_by=f"slack:{slack_user}", clicked_at=iso(self.P.clock.now()))
        self.log.append({"event": "approval.clicked", "approval_request_id": pid, "approved": rec["approved"], "clicked_by": rec["clicked_by"],
                         "at": rec["clicked_at"]})
        return {"accepted": True, "approver": rec["clicked_by"]}

    def api_decide(self, pid: str, credential: str | None, decision: str = "approve", claimed: str | None = None) -> dict[str, Any]:
        rec = self.store[pid]
        rec.update(approved=decision == "approve", clicked_by=claimed or credential, clicked_at=iso(self.P.clock.now()))
        self.log.append({"event": "approval.api", "approval_request_id": pid, "approved": rec["approved"], "clicked_by": rec["clicked_by"], "at": rec["clicked_at"]})
        return {"accepted": True, "approver": rec["clicked_by"]}

    def resume(self, pid: str, mutate: dict | None = None, runtime: str | None = None, recover: bool = False, workflow: str | None = None) -> GateResult:
        """`if approved: execute(agent.next_action())`, behind the policy-enforcing gateway."""
        wf = workflow or pid
        p, ident = self._ident(wf, runtime)
        action = self.P.presented_action(wf, mutate)
        d = self.P.policy.evaluate(action.capability, action.target.service, action.target.environment)
        if d.decision == "DENY":
            return GateResult(allowed=False, code="DENIED_BY_POLICY", detail=d.reason)
        rec = self.store.get(pid)
        if not rec or rec["approved"] is not True:
            return GateResult(allowed=False, code="NOT_APPROVED" if not rec or rec["approved"] is None else "DENIED")
        if self.after_read:
            hook, self.after_read = self.after_read, None
            hook()
        try:
            out, _ = self.P.gateway.invoke(action.capability, action.target.model_dump(), action.arguments, None, p.correlation_id, credential=STANDING)
        except ToolError as e:
            return GateResult(allowed=True, code="TOOL_FAILED", detail=str(e))
        self.log.append({"event": "action.executed", "approval_request_id": pid, "capability": action.capability, "target": action.target.model_dump(),
                         "arguments": action.arguments, "credential": STANDING, "result": out, "at": iso(self.P.clock.now())})
        return GateResult(allowed=True, code="EXECUTED", output=out)

    def sweep(self) -> list[str]:
        """A has no expiry and no escalation: nothing to sweep."""
        return []

    def records(self, pid: str) -> dict[str, Any]:
        return {"approval_record": self.store.get(pid), "app_log": [x for x in self.log if x.get("approval_request_id") == pid]}


# ======================================================================================================================
class ActionBound(Arm):
    key = "B"

    def __init__(self, P: Platform):
        super().__init__(P)
        self.log: list[dict[str, Any]] = []

    def message(self, pid: str) -> dict[str, Any]:
        return evidence_card(self.P, pid)

    def click(self, pid: str, slack_user: str, decision: str = "approve", request_id: str | None = None) -> dict[str, Any]:
        """The chat adapter maps the click's user id to an enterprise principal, then the approval service decides."""
        p = self.P.approvals.get(pid)["proposal"]
        try:
            who = self.P.directory.principal_for_channel("slack", slack_user)
        except AuthError as e:
            self.P.audit.record("approval.refused", p.correlation_id, pid, approver=f"slack:{slack_user}", status=401, reason=str(e), channel="slack")
            return {"accepted": False, "status": 401, "reason": str(e)}
        try:
            d = self.P.approvals.decide_as(pid, who, DecisionRequest(decision=decision, action_digest=p.action_digest,
                                                                     reason=f"{decision} after reviewing the evidence card", request_id=request_id), channel="slack")
            return {"accepted": True, "approver": who, "approval_id": d.approval_id, "state": self.P.approvals.get(pid)["state"]}
        except DecisionRefused as e:
            return {"accepted": False, "status": e.status, "reason": e.reason}

    def api_decide(self, pid: str, credential: str | None, decision: str = "approve", claimed: str | None = None) -> dict[str, Any]:
        p = self.P.approvals.get(pid)["proposal"]
        try:
            d = self.P.approvals.decide(pid, credential, DecisionRequest(decision=decision, action_digest=p.action_digest), claimed_approver=claimed)
            return {"accepted": True, "approver": d.approver.identity}
        except DecisionRefused as e:
            return {"accepted": False, "status": e.status, "reason": e.reason}

    def resume(self, pid: str, mutate: dict | None = None, runtime: str | None = None, recover: bool = False, workflow: str | None = None) -> GateResult:
        wf = workflow or pid
        p, ident = self._ident(wf, runtime)
        action = self.P.presented_action(wf, mutate)
        d = self.P.policy.evaluate(action.capability, action.target.service, action.target.environment)
        if d.decision == "DENY":
            return GateResult(allowed=False, code="DENIED_BY_POLICY", detail=d.reason)
        rec = self.P.approvals.get(pid)
        art = self.P.approvals.artifact(pid)
        checks = [("approved", rec["state"] in ("APPROVED", "SUCCEEDED") and art is not None and art.decision == "APPROVED", rec["state"], "NOT_APPROVED"),
                  ("request binding", art is not None and art.request_id == wf, f"artifact for {art.request_id if art else None}, executing {wf}", "REQUEST_MISMATCH"),
                  ("action digest matches", art is not None and art.action_digest == f"sha256:{action.digest()}", "", "DIGEST_MISMATCH"),
                  ("not expired", self.P.clock.now() <= rec["proposal"].expires_at, "", "EXPIRED"),
                  ("not used", rec["state"] != "SUCCEEDED", rec["state"], "APPROVAL_CONSUMED")]
        for name, ok, obs, code in checks:
            self.P.audit.record("bound.check", p.correlation_id, pid, check=name, ok=bool(ok), detail=obs)
            if not ok:
                return GateResult(allowed=False, code=code, state=rec["state"])
        if self.after_read:
            hook, self.after_read = self.after_read, None
            hook()
        try:
            out, _ = self.P.gateway.invoke(action.capability, action.target.model_dump(), action.arguments, None, p.correlation_id, credential=STANDING)
        except ToolError as e:
            return GateResult(allowed=True, code="TOOL_FAILED", state=rec["state"], detail=str(e))
        self.log.append({"event": "action.executed", "approval_id": art.approval_id, "request_id": pid, "capability": action.capability,
                         "target": action.target.model_dump(), "arguments": action.arguments, "credential": STANDING, "result": out,
                         "at": iso(self.P.clock.now())})
        self.P.approvals.mark_used(pid, "arm-B")             # read, call, mark: the mark comes after the side effect
        return GateResult(allowed=True, code="EXECUTED", state="SUCCEEDED", output=out)

    def sweep(self) -> list[str]:
        """The scheduler: expire requests and approvals past expires_at; escalate unanswered requests."""
        return self.P.approvals.expire_due() + self.P.approvals.escalate_due()

    def records(self, pid: str) -> dict[str, Any]:
        art = self.P.approvals.artifact(pid)
        return {"artifact": art.model_dump() if art else None, "execution_log": [x for x in self.log if x["request_id"] == pid]}


# ======================================================================================================================
class Revalidated(ActionBound):
    key = "C"

    def resume(self, pid: str, mutate: dict | None = None, runtime: str | None = None, recover: bool = False, workflow: str | None = None) -> GateResult:
        wf = workflow or pid
        p, ident = self._ident(wf, runtime)
        action = self.P.presented_action(wf, mutate)
        self.P.gate.after_read = self.after_read
        self.after_read = None
        res = self.P.gate.execute(pid, action, p.correlation_id, ident, recover=recover, request_id=wf)
        if res.code == "DIGEST_MISMATCH":                    # EDIT or drift: the old approval is void; the new action needs its own
            q = self.P.propose(p.correlation_id, ident, action.capability, action.target.service, action.target.environment, action.arguments,
                               reason=f"re-proposed: the action presented on resume differs from approval {pid}", evidence_refs=p.evidence_refs)
            res.detail += f"; new request {q.proposal_id} ({self.P.approvals.get(q.proposal_id)['state']}, digest {q.action_digest[:12]})"
            res.output = {"reapproval_request": q.proposal_id, "state": self.P.approvals.get(q.proposal_id)["state"]}
        return res

    def records(self, pid: str) -> dict[str, Any]:
        rec = self.P.approvals.get(pid)
        return {"artifact": (a.model_dump() if (a := self.P.approvals.artifact(pid)) else None),
                "audit": [r for r in self.P.audit.records(rec["correlation_id"]) if r["proposal_id"] in (pid, None)],
                "transitions": self.P.approvals.transitions(pid), "audit_chain_intact": self.P.audit.verify()[0]}


def evidence_card(P: Platform, pid: str) -> dict[str, Any]:
    """What an approver sees in B and C: enough to decide without reconstructing a conversation."""
    p = P.approvals.get(pid)["proposal"]
    return {"incident": f"{p.incident_id} · {p.target.service}", "severity": p.context.get("severity", ""), "proposed_action": p.capability,
            "current": p.preconditions.get("current_version"), "target": p.arguments.get("to_version"), "environment": p.target.environment,
            "why": p.reason, "impact": p.context.get("impact", ""), "recovery": p.context.get("recovery", ""),
            "policy": f"{p.policy.policy_id} v{p.policy.version} · {p.policy.rule}", "requested_by": f"{p.requested_by.agent_id} via {p.requested_by.runtime}",
            "authority": p.delegation_chain_ref, "approvals_needed": p.policy.required_approvals, "expires": iso(p.expires_at),
            "action_digest": f"sha256:{p.action_digest}", "buttons": ["Approve exact action", "Deny"]}


def make(arm: str, P: Platform) -> Arm:
    return {"A": NaiveBoolean, "B": ActionBound, "C": Revalidated}[arm](P)


def run_crashing(arm: Arm, pid: str, **kw) -> GateResult:
    """Resume once; if the worker crashes after the write committed, report it (the workflow engine will retry)."""
    try:
        return arm.resume(pid, **kw)
    except WorkerCrash as e:
        return GateResult(allowed=True, code="WORKER_CRASHED", detail=str(e))

