"""The execution gate (arm C, the revalidated protocol) and the capability gateway.

The gate never trusts model output or a caller's word that something was approved.  When a paused, approval-gated action
resumes, it consumes the approval atomically (APPROVED → REVALIDATING, compare-and-set: one worker wins), then re-checks
everything the approval depended on, all of it, and fails closed:

    identity      the agent is still enabled; the runtime resuming the workflow is registered for that agent
    delegation    the delegation the agent acts under is still active
    policy        the current policy still says REQUIRE_APPROVAL, at the version and approval count the human saw
    resource      the system's state still matches the preconditions the human saw (time of check vs time of use)
    approval      approved by enough distinct humans, not expired, each approver still eligible
    digest        the action being executed is exactly the approved action
    idempotency   one execution record and one idempotency key per approval; a crashed attempt is reconciled, not re-run

Authority lost (identity, delegation, policy DENY) → REJECTED.  The world, the policy or the approver changed, or the
action did → REAPPROVAL_REQUIRED.  Expired → EXPIRED.  Only when every check holds does the gateway mint a narrow,
short-lived tool credential and call the enterprise system with the approval's idempotency key.
"""

from __future__ import annotations

from typing import Any, Callable

from hitl.approvals import ApprovalService, IllegalTransition, ServiceUnavailable
from hitl.base import AuditLog, Clock, Directory, Telemetry, iso, short_id
from hitl.contracts import Action, GateResult
from hitl.enterprise import Conflict, Enterprise, ToolError
from hitl.policy import PolicyEngine

EXECUTOR = "svc.capability-gateway"
STANDING = "svc.capability-gateway:standing-kubernetes-credential"
AUTHORITY = ("agent enabled", "runtime registered for the agent", "delegation active")


class WorkerCrash(Exception):
    """The worker died after the enterprise system committed the write and before the result was recorded."""


class CapabilityGateway:
    """The only path to enterprise systems.  Holds the system credentials; retries timeouts with the same key."""

    def __init__(self, enterprise: Enterprise, telemetry: Telemetry, retries: int = 2):
        self.ent, self.tel, self.retries = enterprise, telemetry, retries
        self.invocations: dict[str, int] = {}
        self.crash_after_commit = 0          # fault injection: the next N writes crash the worker after the commit

    def invoke(self, capability: str, target: dict[str, str], arguments: dict[str, Any], key: str | None, trace: str,
               credential: str = STANDING) -> tuple[Any, int]:
        fn = getattr(self.ent, capability)
        attempts = 0
        while True:
            attempts += 1
            self.ent.clock.advance(1)                      # every call takes one simulated second
            self.invocations[capability] = self.invocations.get(capability, 0) + 1
            with self.tel.span("tool", trace, capability, attempt=attempts):
                try:
                    kwargs = {**target, **arguments, **({"idempotency_key": key} if key else {})}
                    if capability in self.ent.WRITES:
                        kwargs["credential"] = credential
                    out = fn(**kwargs)
                except TimeoutError:
                    if attempts > self.retries:
                        raise ToolError(f"{capability}: no answer after {attempts} attempts")
                    self.ent.clock.advance(2)
                    continue
            if capability in self.ent.WRITES and self.crash_after_commit:
                self.crash_after_commit -= 1
                raise WorkerCrash(f"{capability}: worker lost after the write committed")
            return out, attempts


class ExecutionGate:
    def __init__(self, approvals: ApprovalService, policy: PolicyEngine, directory: Directory, enterprise: Enterprise,
                 gateway: CapabilityGateway, audit: AuditLog, telemetry: Telemetry, clock: Clock):
        self.approvals, self.policy, self.directory, self.ent = approvals, policy, directory, enterprise
        self.gateway, self.audit, self.tel, self.clock = gateway, audit, telemetry, clock
        self.bind_digest = True              # the safeguard a negative control removes: exact-action binding
        self.after_read: Callable[[], None] | None = None     # test hook: a second worker runs between read and consume

    # ---- automatic path (no human) -----------------------------------------------------------------------------------
    def run_auto(self, action: Action, corr: str, ident: dict[str, str]) -> GateResult:
        d = self.policy.evaluate(action.capability, action.target.service, action.target.environment)
        self.audit.record("policy.evaluated", corr, None, capability=action.capability, decision=d.decision, rule=d.rule, tier=d.tier,
                          policy_decision_id=d.decision_id, **ident)
        if d.decision != "ALLOW":
            return GateResult(allowed=False, code=f"POLICY_{d.decision}", detail=d.reason)
        out, attempts = self.gateway.invoke(action.capability, action.target.model_dump(), action.arguments, None, corr)
        self.audit.record("capability.invoked", corr, None, capability=action.capability, target=action.target.model_dump(), arguments=action.arguments,
                          attempts=attempts, executor=EXECUTOR, approval=None, **ident)
        return GateResult(allowed=True, code="EXECUTED", output=out)

    # ---- the approval-gated path -------------------------------------------------------------------------------------
    def execute(self, pid: str | None, action: Action, corr: str, ident: dict[str, str], retry: bool = False, recover: bool = False,
                request_id: str | None = None) -> GateResult:
        """`request_id` is the approval request of the workflow that is resuming; an approval issued for another request is
        refused before it is consumed (request binding, as in arm B)."""
        with self.tel.span("gate", corr, action.capability, proposal=pid):
            res = self._execute(pid, action, corr, ident, retry, recover, request_id)
        self.audit.record("gate.result", corr, pid, allowed=res.allowed, code=res.code, state=res.state, detail=res.detail)
        return res

    def _check(self, corr: str, pid: str | None, name: str, ok: bool, detail: str = "") -> bool:
        self.audit.record("gate.check", corr, pid, check=name, ok=ok, detail=detail)
        return ok

    def _execute(self, pid: str | None, action: Action, corr: str, ident: dict[str, str], retry: bool, recover: bool,
                 request_id: str | None = None) -> GateResult:
        d = self.policy.evaluate(action.capability, action.target.service, action.target.environment)
        if not self._check(corr, pid, "policy", d.decision != "DENY", f"{d.decision} by {d.rule}"):
            return GateResult(allowed=False, code="DENIED_BY_POLICY", detail=d.reason)
        if d.decision == "ALLOW":
            return self.run_auto(action, corr, ident)
        if not self._check(corr, pid, "proposal referenced", pid is not None):
            return GateResult(allowed=False, code="NO_APPROVAL", detail="approval required and no proposal referenced")
        try:
            rec = self.approvals.get(pid)
            decisions = self.approvals.decisions(pid) if rec else []
        except ServiceUnavailable as e:
            self._check(corr, pid, "approval service reachable", False, str(e))
            return GateResult(allowed=False, code="APPROVAL_SERVICE_UNAVAILABLE", detail="cannot verify approval; failing closed")
        if not self._check(corr, pid, "proposal exists", rec is not None):
            return GateResult(allowed=False, code="NO_APPROVAL", detail="unknown proposal")
        p, state = rec["proposal"], rec["state"]
        if not self._check(corr, pid, "request binding", request_id in (None, pid), f"approval for {pid}, presented by request {request_id}"):
            return GateResult(allowed=False, code="REQUEST_MISMATCH", state=state, detail="the approval belongs to another request")
        if state == "EXECUTING" and recover:
            return self._reconcile(pid, p, corr, ident, decisions)
        if state in ("SUCCEEDED", "REVALIDATING", "EXECUTING"):
            self._check(corr, pid, "single use", False, f"approval already {'used' if state == 'SUCCEEDED' else 'in use'} ({state})")
            return GateResult(allowed=False, code="APPROVAL_CONSUMED" if state == "SUCCEEDED" else "CONCURRENT_EXECUTION", state=state,
                              detail="one approval authorizes one execution")
        want = "FAILED" if retry else "APPROVED"
        if not self._check(corr, pid, f"state is {want}", state == want, state):
            return GateResult(allowed=False, code=f"NOT_EXECUTABLE_{state}", state=state, detail=f"proposal is {state}")
        if retry and not (rec["failure"] or {}).get("retryable"):
            self._check(corr, pid, "failure is retryable", False, str(rec["failure"]))
            return GateResult(allowed=False, code="NOT_RETRYABLE", state=state)
        if self.after_read:
            hook, self.after_read = self.after_read, None
            hook()
        try:                                                   # single-use consumption: exactly one worker leaves APPROVED
            self.approvals.transition(pid, state, "REVALIDATING", EXECUTOR, note="approval consumed; revalidating")
        except IllegalTransition as e:
            self._check(corr, pid, "single use (compare-and-set)", False, str(e))
            return GateResult(allowed=False, code="CONCURRENT_EXECUTION", detail=str(e))
        checks, code = self.revalidate(p, action, decisions, ident, d)
        self.audit.record("revalidation", corr, pid, checks=checks, outcome=code or "VALID", action_digest=p.action_digest,
                          runtime=ident.get("runtime"), at=iso(self.clock.now()))
        if code:
            failed = [c["check"] for c in checks if not c["ok"]]
            dst = ("REJECTED" if code in ("AGENT_DISABLED", "RUNTIME_UNREGISTERED", "DELEGATION_REVOKED", "DENIED_BY_POLICY")
                   else "EXPIRED" if code == "EXPIRED" else "REAPPROVAL_REQUIRED")
            self.approvals.transition(pid, "REVALIDATING", dst, "svc.hitl-runtime", note="; ".join(failed))
            return GateResult(allowed=False, code=code, state=dst, checks=checks, detail="revalidation failed: " + "; ".join(failed))
        self.approvals.transition(pid, "REVALIDATING", "EXECUTING", EXECUTOR, note="all revalidation checks hold")
        return self._invoke(pid, p, action, corr, ident, decisions, checks)

    def revalidate(self, p, action: Action, decisions, ident: dict[str, str], d) -> tuple[list[dict[str, Any]], str | None]:
        """Every check, recorded with its observed value; the code of the first failure in precedence order, or None."""
        agent = p.requested_by.agent_id
        runtime = ident.get("runtime", p.requested_by.runtime)
        approvers = [x.approver.identity for x in decisions if x.decision == "approve"]
        need = max(1, d.required_approvals or 1)
        cur = self.ent.getDeploymentHistory(action.target.service, action.target.environment)["current"]
        inel = {a: self.approvals.eligibility(a, p) for a in approvers}
        rows = [
            ("agent enabled", self.directory.agent_enabled(agent), agent, "AGENT_DISABLED"),
            ("runtime registered for the agent", self.directory.runtime_registered(agent, runtime), runtime, "RUNTIME_UNREGISTERED"),
            ("delegation active", self.directory.delegation_active(p.delegation_chain_ref), p.delegation_chain_ref, "DELEGATION_REVOKED"),
            ("not expired", self.clock.now() <= p.expires_at, f"expires {iso(p.expires_at)}", "EXPIRED"),
            ("action digest matches the approval", (action.digest() == p.action_digest) or not self.bind_digest,
             f"{action.digest()[:12]} vs approved {p.action_digest[:12]}", "DIGEST_MISMATCH"),
            ("policy version unchanged", self.policy.version == p.policy.version, f"approved under v{p.policy.version}, now v{self.policy.version}",
             "POLICY_CHANGED"),
            ("policy still requires this approval", d.decision == "REQUIRE_APPROVAL" and need <= len(set(approvers)),
             f"{d.decision}, {need} approver(s) needed, {len(set(approvers))} approved", "POLICY_CHANGED"),
            ("resource state unchanged", cur == p.preconditions.get("current_version"), f"running {cur}, approved against {p.preconditions.get('current_version')}",
             "PRECONDITION_CHANGED"),
            ("approver still eligible", bool(approvers) and all(isinstance(v, str) for v in inel.values()),
             "; ".join(f"{a}: {'eligible' if isinstance(v, str) else v[1]}" for a, v in inel.items()) or "no approval", "APPROVER_INELIGIBLE"),
        ]
        checks = [{"check": n, "ok": bool(ok), "observed": obs} for n, ok, obs, _ in rows]
        code = next((c for n, ok, obs, c in rows if not ok), None)
        return checks, code

    def _invoke(self, pid, p, action: Action, corr, ident, decisions, checks) -> GateResult:
        cred = {"credential_id": short_id("cred", pid, p.action_digest), "audience": "kubernetes", "scope": f"{action.capability}:{action.target.service}",
                "minted_at": iso(self.clock.now()), "expires_at": iso(self.clock.now() + 300)}
        approver = ",".join(x.approver.identity for x in decisions if x.decision == "approve")
        chain = {**ident, "approver": approver, "approval_id": decisions[-1].approval_id, "executor": EXECUTOR}
        self.audit.record("credential.minted", corr, pid, **cred)
        self.audit.record("execution.started", corr, pid, idempotency_key=p.idempotency_key, credential_id=cred["credential_id"])
        try:
            out, attempts = self.gateway.invoke(action.capability, action.target.model_dump(), action.arguments, p.idempotency_key, corr,
                                                credential=cred["credential_id"])
        except ToolError as e:
            retryable = not isinstance(e, Conflict)
            self.approvals.transition(pid, "EXECUTING", "FAILED", EXECUTOR, failure={"error": str(e), "retryable": retryable})
            self.audit.record("capability.failed", corr, pid, capability=action.capability, error=str(e), retryable=retryable,
                              action_digest=p.action_digest, **chain)
            return GateResult(allowed=True, code="TOOL_FAILED", state="FAILED", detail=str(e), checks=checks)
        self.audit.record("capability.invoked", corr, pid, capability=action.capability, target=action.target.model_dump(),
                          arguments=action.arguments, attempts=attempts, idempotency_key=p.idempotency_key, action_digest=p.action_digest,
                          credential_id=cred["credential_id"], **chain)
        self.audit.record("enterprise.result", corr, pid, system=self.policy.capabilities[action.capability]["system"], result=out)
        self.approvals.transition(pid, "EXECUTING", "SUCCEEDED", EXECUTOR)
        self.audit.record("execution.state", corr, pid, state="SUCCEEDED")
        return GateResult(allowed=True, code="EXECUTED", state="SUCCEEDED", output=out, checks=checks)

    def _reconcile(self, pid, p, corr, ident, decisions) -> GateResult:
        """A retried workflow step found its own execution record: ask the system with the same idempotency key."""
        started = [r for r in self.audit.records(corr) if r["kind"] == "execution.started" and r["proposal_id"] == pid]
        if not self._check(corr, pid, "execution record exists", bool(started), "reconcile with the recorded idempotency key"):
            return GateResult(allowed=False, code="NO_EXECUTION_RECORD", state="EXECUTING")
        cred = started[-1]["record"]["credential_id"]
        a = p.action()
        out, attempts = self.gateway.invoke(a.capability, a.target.model_dump(), a.arguments, p.idempotency_key, corr, credential=cred)
        approver = ",".join(x.approver.identity for x in decisions if x.decision == "approve")
        self.audit.record("capability.invoked", corr, pid, capability=a.capability, target=a.target.model_dump(), arguments=a.arguments,
                          attempts=attempts, idempotency_key=p.idempotency_key, action_digest=p.action_digest, credential_id=cred, reconciled=True,
                          **{**ident, "approver": approver, "approval_id": decisions[-1].approval_id, "executor": EXECUTOR})
        self.audit.record("enterprise.result", corr, pid, system=self.policy.capabilities[a.capability]["system"], result=out)
        self.approvals.transition(pid, "EXECUTING", "SUCCEEDED", EXECUTOR, note="reconciled after a worker crash")
        self.audit.record("execution.state", corr, pid, state="SUCCEEDED")
        return GateResult(allowed=True, code="RECONCILED", state="SUCCEEDED", output=out)

    def retry(self, pid: str, action: Action, corr: str, ident: dict[str, str]) -> GateResult:
        """Documented retry rule: only a FAILED, retryable execution; revalidated like a resume; the same idempotency key."""
        return self.execute(pid, action, corr, ident, retry=True)
