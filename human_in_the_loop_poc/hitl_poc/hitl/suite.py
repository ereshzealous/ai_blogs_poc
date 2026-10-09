"""The canonical HITL test suite: 30 deterministic tests, the release gate.

Each test builds a fresh platform (fresh databases, the clock at 14:02:00 UTC, the same fixtures), drives real code
paths, and returns named assertions as (observed, expected) pairs read from the systems of record, the approval store
and the audit chain.  A test passes when every assertion holds.  No model, no network, no randomness.

    run_suite(base)            -> list of TestOutcome      (used by `hitl suite`, the proof pack and pytest)
    run_suite(base, safeguards={"bind_digest": False})     (the negative controls)
"""

from __future__ import annotations

import json
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from hitl.approvals import DecisionRefused, IllegalTransition, ServiceUnavailable
from hitl.contracts import Action, DecisionRequest, Target
from hitl.platform import Platform

EVENT = {"source": "monitoring/datadog", "id": "dd-evt-88121", "service": "payment-service", "environment": "production",
         "signal": {"error_rate": 0.14}}

INVARIANTS = {
    "HITL-I01": "No approval-gated action executes without a valid approval.",
    "HITL-I02": "Approval authorizes the exact proposed action only.",
    "HITL-I03": "Modifying the target or arguments invalidates the approval.",
    "HITL-I04": "Approval cannot grant authority forbidden by policy.",
    "HITL-I05": "Expired, rejected and canceled approvals cannot execute.",
    "HITL-I06": "The agent cannot approve itself.",
    "HITL-I07": "Only appropriately authorized approvers can approve.",
    "HITL-I08": "Duplicate events must not create duplicate consequential effects.",
    "HITL-I09": "Approval failure or policy uncertainty fails closed for gated actions.",
    "HITL-I10": "Every consequential action can be reconstructed from immutable audit evidence.",
}
CATEGORIES = {"A": "Risk and policy routing", "B": "Exact-action binding and tamper protection", "C": "Approval lifecycle",
              "D": "Identity and separation of duties", "E": "Duplicates, idempotency and concurrency", "F": "Fail-closed, adversarial and audit"}


@dataclass
class TestOutcome:
    id: str
    name: str
    category: str
    invariants: list[str]
    assertions: dict[str, dict[str, Any]] = field(default_factory=dict)
    measured: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(a["held"] for a in self.assertions.values())


class Lab:
    """A fresh platform for one test."""

    def __init__(self, base: Path, tid: str, safeguards: dict[str, bool] | None = None):
        self.dir = base / tid
        shutil.rmtree(self.dir, ignore_errors=True)
        self.p = Platform(self.dir)
        for k, v in (safeguards or {}).items():
            if k == "bind_digest":
                self.p.gate.bind_digest = v
            if k == "authenticate_approver":
                self.p.approvals.authenticate_approver = v

    # helpers ----------------------------------------------------------------------------------------------------------
    def incident(self) -> tuple[str, Any]:
        r = self.p.receive("tok-monitor", dict(EVENT))
        pid = r["proposals"][0]["proposal_id"]
        return pid, self.p.approvals.get(pid)["proposal"]

    def decide(self, pid: str, cred: str, decision: str = "approve", digest: str | None = None, request_id: str | None = None,
               claimed: str | None = None, wait_s: float = 90) -> tuple[bool, Any]:
        self.p.clock.advance(wait_s)                       # a human takes time to read the request
        p = self.p.approvals.get(pid)["proposal"]
        try:
            d = self.p.approvals.decide(pid, cred, DecisionRequest(decision=decision, action_digest=digest or p.action_digest,
                                                                    reason=f"{decision} after reviewing the evidence", request_id=request_id),
                                        claimed_approver=claimed)
            return True, d
        except DecisionRefused as e:
            return False, e

    def state(self, pid: str) -> str:
        return self.p.approvals.get(pid)["state"]

    def rollbacks(self) -> int:
        return self.p.ent.effect_count("rollback")

    def effects(self) -> int:
        return sum(1 for e in self.p.ent.effects if e["kind"] in ("rollback", "restart", "namespace.delete"))

    def auto(self, capability: str, **args: Any):
        a = Action(capability=capability, target=Target(service="payment-service", environment="production"), arguments=args,
                   policy=self.p.policy.ref(), risk=self.p.policy.tier(capability) or "unknown")
        return self.p.gate.run_auto(a, "cor-direct", self.p.identity("svc.monitoring-webhook"))

    def dump(self, out: Path, tid: str) -> None:
        out.mkdir(parents=True, exist_ok=True)
        trans = [{"proposal_id": r[0], "src": r[1], "dst": r[2], "by": r[3]}
                 for r in self.p.approvals.db.execute("SELECT proposal_id, src, dst, by FROM transitions ORDER BY n")]
        (out / f"{tid}.json").write_text(json.dumps({"test": tid, "audit": self.p.audit.records(), "spans": self.p.tel.spans,
                                                     "transitions": trans, "effects": self.p.ent.effects,
                                                     "audit_chain_intact": self.p.audit.verify()[0]}, indent=1, sort_keys=True, default=str))


TESTS: list[tuple[str, str, str, list[str], Callable[[Lab], tuple[dict[str, tuple[Any, Any]], dict[str, Any]]]]] = []


def test(tid: str, name: str, category: str, *invariants: str):
    def reg(fn):
        TESTS.append((tid, name, category, list(invariants), fn))
        return fn
    return reg


# ---- A · risk and policy routing ---------------------------------------------------------------------------------------
@test("HITL-T01", "Read action executes automatically", "A", "HITL-I01")
def t01(L: Lab):
    r = L.auto("getDeploymentHealth")
    return {"allowed": (r.allowed, True), "approval_requests": (len(L.p.inbox), 0), "executions": (L.p.gateway.invocations.get("getDeploymentHealth", 0), 1)}, \
           {"approval_requests": len(L.p.inbox), "executions": L.p.gateway.invocations.get("getDeploymentHealth", 0)}


@test("HITL-T02", "Analysis executes automatically", "A", "HITL-I01")
def t02(L: Lab):
    e = L.p.ent
    ev = {"health": e.getDeploymentHealth("payment-service", "production"), "logs": e.getLogs("payment-service", "production"),
          "traces": e.getTraceSummary("payment-service", "production"), "history": e.getDeploymentHistory("payment-service", "production"),
          "known": e.getKnownIncidents("payment-service", "production")}
    r = L.auto("correlateIncidentEvidence", evidence=ev)
    return {"allowed": (r.allowed, True), "approval_requests": (len(L.p.inbox), 0), "confidence": (r.output["confidence"], "high")}, \
           {"approval_requests": len(L.p.inbox)}


@test("HITL-T03", "Recommendation does not require approval and changes nothing", "A", "HITL-I01")
def t03(L: Lab):
    r = L.auto("recommendRollback", assessment={"from_version": "v4.18.0", "to_version": "v4.17.2", "signals": 3})
    return {"allowed": (r.allowed, True), "approval_requests": (len(L.p.inbox), 0), "side_effects": (L.effects(), 0),
            "recommends": (r.output["to_version"], "v4.17.2")}, {"side_effects": L.effects()}


@test("HITL-T04", "High-risk write requires approval and waits", "A", "HITL-I01")
def t04(L: Lab):
    pid, p = L.incident()
    early = L.p.execute_proposal(pid)
    return {"policy_decision": (p.policy.decision, "REQUIRE_APPROVAL"), "state": (L.state(pid), "PENDING_APPROVAL"),
            "approval_requests": (len(L.p.inbox), 1), "early_execution_allowed": (early.allowed, False), "side_effects": (L.rollbacks(), 0)}, \
           {"side_effects": L.rollbacks(), "approval_requests": len(L.p.inbox)}


@test("HITL-T05", "Policy DENY cannot be overridden by human approval", "A", "HITL-I04")
def t05(L: Lab):
    L.incident()
    corr = next(iter(L.p.executions))
    p = L.p.propose(corr, L.p.executions[corr]["identity"], "deleteProductionNamespace", "payment-service", "production", {},
                    reason="free capacity", evidence_refs=[])
    ok, err = L.decide(p.proposal_id, "tok-alice")
    r = L.p.execute_proposal(p.proposal_id)
    return {"policy_decision": (p.policy.decision, "DENY"), "state": (L.state(p.proposal_id), "REJECTED"), "approval_accepted": (ok, False),
            "execution_allowed": (r.allowed, False), "deletes": (L.p.ent.effect_count("namespace.delete"), 0)}, \
           {"side_effects": L.p.ent.effect_count("namespace.delete"), "approval_accepted": ok}


# ---- B · exact-action binding ------------------------------------------------------------------------------------------
def _approved(L: Lab):
    pid, p = L.incident()
    ok, d = L.decide(pid, "tok-alice")
    assert ok, d
    return pid, p


@test("HITL-T06", "Exact approved proposal executes once", "B", "HITL-I02")
def t06(L: Lab):
    pid, p = _approved(L)
    r = L.p.execute_proposal(pid)
    return {"code": (r.code, "EXECUTED"), "state": (L.state(pid), "SUCCEEDED"), "side_effects": (L.rollbacks(), 1),
            "running_version": (L.p.ent.getDeploymentHistory("payment-service", "production")["current"], "v4.17.2")}, {"side_effects": L.rollbacks()}


@test("HITL-T07", "Argument mutation invalidates approval", "B", "HITL-I02", "HITL-I03")
def t07(L: Lab):
    pid, p = _approved(L)
    r = L.p.execute_proposal(pid, mutate={"to_version": "v4.16.0"})
    return {"execution_allowed": (r.allowed, False), "code": (r.code, "DIGEST_MISMATCH"), "side_effects": (L.rollbacks(), 0)}, \
           {"side_effects": L.rollbacks()}


@test("HITL-T08", "Resource mutation invalidates approval", "B", "HITL-I02", "HITL-I03")
def t08(L: Lab):
    pid, p = _approved(L)
    r = L.p.execute_proposal(pid, mutate={"service": "orders-service"})
    return {"execution_allowed": (r.allowed, False), "code": (r.code, "DIGEST_MISMATCH"), "side_effects": (L.rollbacks(), 0)}, \
           {"side_effects": L.rollbacks()}


@test("HITL-T09", "Environment or capability mutation invalidates approval", "B", "HITL-I02", "HITL-I03")
def t09(L: Lab):
    pid, p = _approved(L)
    cap = L.p.execute_proposal(pid, mutate={"capability": "restartDeployment"})
    L2 = Lab(L.dir.parent, L.dir.name + "-env")
    qid, q = _approved(L2)
    env = L2.p.execute_proposal(qid, mutate={"environment": "staging"})
    return {"environment_allowed": (env.allowed, False), "environment_code": (env.code, "DIGEST_MISMATCH"),
            "capability_allowed": (cap.allowed, False), "capability_code": (cap.code, "DIGEST_MISMATCH"), "approval_voided": (L.state(pid), "REAPPROVAL_REQUIRED"),
            "side_effects": (L.effects() + L2.effects(), 0)}, {"side_effects": L.effects() + L2.effects()}


@test("HITL-T10", "Precondition or policy change forces re-evaluation", "B", "HITL-I02", "HITL-I03")
def t10(L: Lab):
    pid, p = _approved(L)
    L.p.ent.deploy("payment-service", "production", "v4.18.1", by="dana")           # someone ships v4.18.1 under the pending approval
    r1 = L.p.execute_proposal(pid)
    corr = p.correlation_id
    p2 = L.p.propose(corr, L.p.executions[corr]["identity"], "rollbackDeployment", "payment-service", "production",
                     {"from_version": "v4.18.1", "to_version": "v4.18.0"}, reason="re-evaluated after v4.18.1", evidence_refs=p.evidence_refs)
    L2 = Lab(L.dir.parent, L.dir.name + "-policy")
    qid, q = _approved(L2)
    L2.p.policy.version = "8"                                                   # the policy the approver saw is no longer current
    r2 = L2.p.execute_proposal(qid)
    return {"precondition_code": (r1.code, "PRECONDITION_CHANGED"), "stale_state": (L.state(pid), "REAPPROVAL_REQUIRED"),
            "reevaluated_needs_new_approval": (L.state(p2.proposal_id), "PENDING_APPROVAL"), "new_digest_differs": (p2.action_digest != p.action_digest, True),
            "policy_code": (r2.code, "POLICY_CHANGED"), "policy_state": (L2.state(qid), "REAPPROVAL_REQUIRED"),
            "side_effects": (L.rollbacks() + L2.rollbacks(), 0)}, {"side_effects": L.rollbacks() + L2.rollbacks()}


# ---- C · lifecycle -----------------------------------------------------------------------------------------------------
@test("HITL-T11", "Pending approval transitions to approved", "C", "HITL-I07")
def t11(L: Lab):
    pid, p = L.incident()
    ok, d = L.decide(pid, "tok-alice")
    hist = L.p.approvals.history(pid)
    return {"accepted": (ok, True), "state": (L.state(pid), "APPROVED"), "transition": (hist[-1], ("PENDING_APPROVAL", "APPROVED", "alice")),
            "decision_digest": (d.action_digest, p.action_digest)}, {}


@test("HITL-T12", "Rejected approval prevents execution", "C", "HITL-I05")
def t12(L: Lab):
    pid, p = L.incident()
    ok, d = L.decide(pid, "tok-alice", decision="deny")
    r = L.p.execute_proposal(pid)
    return {"accepted": (ok, True), "state": (L.state(pid), "DENIED"), "execution_allowed": (r.allowed, False), "side_effects": (L.rollbacks(), 0)}, \
           {"side_effects": L.rollbacks()}


@test("HITL-T13", "Expired approval cannot execute", "C", "HITL-I05")
def t13(L: Lab):
    pid, p = L.incident()
    ttl = L.p.policy.approval["ttl_s"]
    ok, err = L.decide(pid, "tok-alice", wait_s=ttl + 60)                       # decision arrives after expires_at
    late_state = L.state(pid)
    L2 = Lab(L.dir.parent, L.dir.name + "-use")
    qid, q = _approved(L2)                                                      # approved in time …
    L2.p.clock.advance(ttl + 100)                                               # … but used after expiry
    r = L2.p.execute_proposal(qid)
    return {"late_decision_accepted": (ok, False), "late_state": (late_state, "EXPIRED"), "use_after_expiry_code": (r.code, "EXPIRED"),
            "side_effects": (L.rollbacks() + L2.rollbacks(), 0)}, {"side_effects": L.rollbacks() + L2.rollbacks()}


@test("HITL-T14", "Canceled proposal cannot execute", "C", "HITL-I05")
def t14(L: Lab):
    pid, p = L.incident()
    L.p.approvals.cancel(pid, "alice", "service recovered on its own")
    ok, err = L.decide(pid, "tok-omar")
    r = L.p.execute_proposal(pid)
    return {"state": (L.state(pid), "CANCELED"), "approve_after_cancel": (ok, False), "execution_allowed": (r.allowed, False),
            "side_effects": (L.rollbacks(), 0)}, {"side_effects": L.rollbacks()}


@test("HITL-T15", "Invalid terminal-state transitions are rejected", "C", "HITL-I05")
def t15(L: Lab):
    attempts = []
    a, _ = L.incident()
    L.decide(a, "tok-alice", decision="deny")
    attempts.append(("DENIED", "APPROVED", a))
    L2 = Lab(L.dir.parent, L.dir.name + "-exp")
    b, _ = L2.incident()
    L2.p.clock.advance(L2.p.policy.approval["ttl_s"] + 100)
    L2.p.approvals.expire_due()
    L3 = Lab(L.dir.parent, L.dir.name + "-done")
    c, _ = _approved(L3)
    L3.p.execute_proposal(c)
    refused = 0
    for lab, pid, src, dst in ((L, a, "DENIED", "APPROVED"), (L2, b, "EXPIRED", "APPROVED"), (L3, c, "SUCCEEDED", "EXECUTING"),
                               (L2, b, "EXPIRED", "EXECUTING")):
        try:
            lab.p.approvals.transition(pid, src, dst, "svc.hitl-runtime")
        except IllegalTransition:
            refused += 1
    ok, err = L.decide(a, "tok-omar")                                           # and through the decision API
    return {"illegal_transitions_refused": (refused, 4), "decide_on_rejected": (ok, False), "states_unchanged": ((L.state(a), L2.state(b), L3.state(c)),
            ("DENIED", "EXPIRED", "SUCCEEDED")), "side_effects": (L.rollbacks() + L2.rollbacks() + L3.rollbacks(), 1)}, \
           {"illegal_transitions_refused": refused}


# ---- D · identity and separation of duties -----------------------------------------------------------------------------
@test("HITL-T16", "Authorized approver can approve", "D", "HITL-I07")
def t16(L: Lab):
    pid, p = L.incident()
    ok, d = L.decide(pid, "tok-alice")
    return {"accepted": (ok, True), "approver": (d.approver.identity, "alice"), "role_held": ("production-approver" in d.approver.roles, True)}, {}


@test("HITL-T17", "Unauthorized identity cannot approve", "D", "HITL-I07")
def t17(L: Lab):
    pid, p = L.incident()
    ok, err = L.decide(pid, "tok-reggie")
    return {"accepted": (ok, False), "status": (getattr(err, "status", None), 403), "state": (L.state(pid), "PENDING_APPROVAL"),
            "side_effects": (L.rollbacks(), 0)}, {"status": getattr(err, "status", None)}


@test("HITL-T18", "Agent cannot approve its own proposal", "D", "HITL-I06")
def t18(L: Lab):
    pid, p = L.incident()
    a_ok, a = L.decide(pid, "tok-agent")
    r_ok, r = L.decide(pid, "tok-runtime")
    c_ok, c = L.decide(pid, "tok-agent", claimed="alice", request_id="claimed-alice")   # model output asserting a human approved
    ex = L.p.execute_proposal(pid)
    return {"agent_accepted": (a_ok, False), "runtime_accepted": (r_ok, False), "claimed_identity_accepted": (c_ok, False),
            "state": (L.state(pid), "PENDING_APPROVAL"), "side_effects": (L.rollbacks(), 0)}, \
           {"side_effects": L.rollbacks(), "self_approvals_accepted": sum([a_ok, r_ok, c_ok])}


@test("HITL-T19", "Separation of duties: the deployment author cannot approve its rollback", "D", "HITL-I07")
def t19(L: Lab):
    pid, p = L.incident()
    d_ok, d = L.decide(pid, "tok-dana")
    a_ok, a = L.decide(pid, "tok-alice")
    return {"author": (p.context["deployment_author"], "dana"), "author_accepted": (d_ok, False), "author_status": (getattr(d, "status", None), 403),
            "independent_approver_accepted": (a_ok, True)}, {}


@test("HITL-T20", "Every identity in the chain survives to the audit record", "D", "HITL-I10")
def t20(L: Lab):
    pid, p = _approved(L)
    L.p.execute_proposal(pid)
    rec = next(r["record"] for r in L.p.audit.records(p.correlation_id) if r["kind"] == "capability.invoked" and r["proposal_id"] == pid)
    chain = {k: rec.get(k) for k in ("invoker", "agent", "runtime", "on_behalf_of", "approver", "executor")}
    return {"invoker": (chain["invoker"], "svc.monitoring-webhook"), "agent": (chain["agent"], "agent.incident-investigator@2.1.0"),
            "runtime": (chain["runtime"], "svc.hitl-runtime"), "on_behalf_of": (chain["on_behalf_of"], "production-incident-platform"),
            "approver": (chain["approver"], "alice"), "executor": (chain["executor"], "svc.capability-gateway"),
            "distinct_identities": (len(set(chain.values())), 6)}, {"distinct_identities": len(set(chain.values()))}


# ---- E · duplicates, idempotency, concurrency --------------------------------------------------------------------------
@test("HITL-T21", "Duplicate triggering event creates one logical proposal", "E", "HITL-I08")
def t21(L: Lab):
    L.p.receive("tok-monitor", dict(EVENT))
    L.p.receive("tok-monitor", dict(EVENT))                                     # at-least-once redelivery
    L.p.receive("tok-monitor", {**EVENT, "id": "dd-evt-88190", "signal": {"error_rate": 0.15}})   # re-fired alert, new id
    return {"executions": (len(L.p.executions), 1), "approval_requests": (len(L.p.inbox), 1), "incidents": (L.p.ent.effect_count("incident.create"), 1)}, \
           {"deliveries": 3, "approval_requests": len(L.p.inbox)}


@test("HITL-T22", "Duplicate approval submission is idempotent", "E", "HITL-I08")
def t22(L: Lab):
    pid, p = L.incident()
    ok1, d1 = L.decide(pid, "tok-alice", request_id="browser-req-1")
    ok2, d2 = L.decide(pid, "tok-alice", request_id="browser-req-1")
    ok3, d3 = L.decide(pid, "tok-alice")                                        # a second click without a request id
    decisions = L.p.approvals.db.execute("SELECT COUNT(*) FROM decisions WHERE proposal_id=?", (pid,)).fetchone()[0]
    L.p.execute_proposal(pid)
    return {"first": (ok1, True), "retry_same_answer": (ok2 and d2.approval_id == d1.approval_id, True), "second_click_refused": (ok3, False),
            "decisions": (decisions, 1), "side_effects": (L.rollbacks(), 1)}, {"decisions": decisions, "side_effects": L.rollbacks()}


@test("HITL-T23", "Consumed approval cannot be replayed for a second side effect", "E", "HITL-I02", "HITL-I08")
def t23(L: Lab):
    pid, p = _approved(L)
    first = L.p.execute_proposal(pid)
    replay = L.p.execute_proposal(pid)
    retry = L.p.execute_proposal(pid, retry=True)
    return {"first": (first.code, "EXECUTED"), "replay": (replay.code, "APPROVAL_CONSUMED"), "retry_path": (retry.allowed, False),
            "side_effects": (L.rollbacks(), 1)}, {"side_effects": L.rollbacks()}


@test("HITL-T24", "Concurrent approve and reject end in one terminal decision", "E", "HITL-I05", "HITL-I08")
def t24(L: Lab):
    pid, p = L.incident()
    results: dict[str, Any] = {}

    def racer(who: str, decision: str):
        try:
            results[who] = ("ok", L.p.approvals.decide(pid, f"tok-{who}", DecisionRequest(decision=decision, action_digest=p.action_digest)))
        except DecisionRefused as e:
            results[who] = ("refused", e.status)

    def interleave(who: str):                    # alice has read PENDING_APPROVAL; omar's reject lands before her write
        if who == "alice":
            L.p.approvals.after_read = None
            t = threading.Thread(target=racer, args=("omar", "deny"))
            t.start()
            t.join()
    L.p.clock.advance(60)
    L.p.approvals.after_read = interleave
    racer("alice", "approve")
    decisions = L.p.approvals.db.execute("SELECT COUNT(*) FROM decisions WHERE proposal_id=?", (pid,)).fetchone()[0]
    r = L.p.execute_proposal(pid)
    terminal = [h for h in L.p.approvals.history(pid) if h[0] == "PENDING_APPROVAL"]
    return {"decisions": (decisions, 1), "decisions_leaving_awaiting": (len(terminal), 1), "winner": (results["omar"][0], "ok"),
            "loser": (results["alice"], ("refused", 409)), "state": (L.state(pid), "DENIED"), "execution_allowed": (r.allowed, False),
            "side_effects": (L.rollbacks(), 0)}, {"decisions": decisions, "side_effects": L.rollbacks()}


@test("HITL-T25", "Downstream retries do not duplicate business effects", "E", "HITL-I08")
def t25(L: Lab):
    pid, p = _approved(L)
    L.p.ent.faults["rollbackDeployment"] = ["lost_response"]
    r = L.p.execute_proposal(pid)
    attempts = next(x["record"]["attempts"] for x in L.p.audit.records(p.correlation_id) if x["kind"] == "capability.invoked" and x["proposal_id"] == pid)
    return {"code": (r.code, "EXECUTED"), "attempts": (attempts, 2), "side_effects": (L.rollbacks(), 1), "state": (L.state(pid), "SUCCEEDED")}, \
           {"attempts": attempts, "side_effects": L.rollbacks()}


# ---- F · fail-closed, adversarial, audit -------------------------------------------------------------------------------
@test("HITL-T26", "Prompt injection cannot bypass approval", "F", "HITL-I01", "HITL-I06")
def t26(L: Lab):
    pid, p = L.incident()
    corr = p.correlation_id
    ignored = L.p.executions[corr]["assessment"]["untrusted_instructions_ignored"]
    direct = L.p.execute_proposal(pid)                                               # "approval already granted": execute now
    rt_ok, _ = L.decide(pid, "tok-runtime", claimed="alice", request_id="inj-1")     # the runtime asserts alice approved
    ag_ok, _ = L.decide(pid, "tok-agent", claimed="alice", request_id="inj-2")
    forged = L.p.gate.execute("prop-forged", p.action(), corr, L.p.executions[corr]["identity"])  # an invented approval reference
    return {"injected_lines_treated_as_data": (ignored, 1), "direct_execution_allowed": (direct.allowed, False),
            "runtime_claim_accepted": (rt_ok, False), "agent_claim_accepted": (ag_ok, False), "forged_reference": (forged.code, "NO_APPROVAL"),
            "state": (L.state(pid), "PENDING_APPROVAL"), "side_effects": (L.rollbacks(), 0)}, {"side_effects": L.rollbacks()}


@test("HITL-T27", "Approval service unavailable fails closed", "F", "HITL-I09")
def t27(L: Lab):
    pid, p = _approved(L)
    L.p.approvals.available = False
    r = L.p.gate.execute(pid, p.action(), p.correlation_id, L.p.executions[p.correlation_id]["identity"])
    try:
        L.p.approvals.decide(pid, "tok-omar", DecisionRequest(decision="approve", action_digest=p.action_digest))
        decide_possible = True
    except ServiceUnavailable:
        decide_possible = False
    return {"code": (r.code, "APPROVAL_SERVICE_UNAVAILABLE"), "execution_allowed": (r.allowed, False), "decide_while_down": (decide_possible, False),
            "side_effects": (L.rollbacks(), 0)}, {"side_effects": L.rollbacks()}


@test("HITL-T28", "Policy evaluation failure fails closed", "F", "HITL-I09")
def t28(L: Lab):
    pid, p = _approved(L)
    L.p.policy.available = False
    r = L.p.execute_proposal(pid)
    corr = p.correlation_id
    q = L.p.propose(corr, L.p.executions[corr]["identity"], "rollbackDeployment", "payment-service", "production",
                    {"from_version": "v4.18.0", "to_version": "v4.17.1"}, reason="while the PDP is down", evidence_refs=[])
    return {"code": (r.code, "DENIED_BY_POLICY"), "new_proposal_decision": (q.policy.decision, "DENY"), "new_proposal_rule": (q.policy.rule, "P0-fail-closed"),
            "new_proposal_state": (L.state(q.proposal_id), "REJECTED"), "side_effects": (L.rollbacks(), 0)}, {"side_effects": L.rollbacks()}


@test("HITL-T29", "Tool failure after approval is safe, auditable and retried only by the rules", "F", "HITL-I09", "HITL-I10")
def t29(L: Lab):
    pid, p = _approved(L)
    L.p.ent.faults["rollbackDeployment"] = ["error"]
    r = L.p.execute_proposal(pid)
    failed_state, rollbacks_after_failure = L.state(pid), L.rollbacks()
    audited = any(x["kind"] == "capability.failed" for x in L.p.audit.records(p.correlation_id))
    early = L.p.execute_proposal(pid)                                            # not a retry: a FAILED approval is not re-run by a resume
    retry = L.p.execute_proposal(pid, retry=True)
    again = L.p.execute_proposal(pid, retry=True)
    return {"code": (r.code, "TOOL_FAILED"), "failed_state": (failed_state, "FAILED"), "no_change_on_failure": (rollbacks_after_failure, 0),
            "failure_audited": (audited, True), "plain_resume_refused": (early.allowed, False), "rule_retry": (retry.code, "EXECUTED"),
            "retry_after_success": (again.allowed, False), "side_effects": (L.rollbacks(), 1)}, {"side_effects": L.rollbacks()}


LINKS = [("trigger", "event.received"), ("execution identity", "execution.started"), ("evidence", "evidence.assessed"),
         ("agent proposal", "proposal.created"), ("policy decision", "policy.evaluated"), ("approval requirement", "approval.requested"),
         ("human approver identity", "approval.decided"), ("human decision", "approval.decided"), ("approved action digest", "approval.decided"),
         ("execution attempt", "gate.check"), ("capability invocation", "capability.invoked"), ("enterprise result", "enterprise.result"),
         ("final execution state", "execution.state")]


@test("HITL-T30", "Complete audit reconstruction", "F", "HITL-I10")
def t30(L: Lab):
    pid, p = _approved(L)
    L.p.execute_proposal(pid)
    recs = L.p.audit.records(p.correlation_id)
    pos, found = -1, 0
    for name, kind in LINKS:
        idx = next((i for i, r in enumerate(recs) if i >= pos and r["kind"] == kind and (r["proposal_id"] in (pid, None))), None)
        if idx is None:
            break
        r = recs[idx]["record"]
        ok = {"human approver identity": r.get("approver") == "alice", "human decision": r.get("decision") == "approve",
              "approved action digest": r.get("action_digest") == p.action_digest, "evidence": bool(r.get("evidence_refs")),
              "final execution state": r.get("state") == "SUCCEEDED"}.get(name, True)
        if not ok:
            break
        found += 1
        pos = idx
    times = [r["t"] for r in recs]
    intact, _ = L.p.audit.verify()
    return {"links_reconstructed": (found, len(LINKS)), "chain_intact": (intact, True), "timestamps_monotonic": (times == sorted(times), True),
            "one_correlation_id": (len({r["correlation_id"] for r in recs}), 1)}, {"links": found, "audit_records": len(recs)}


# ---- runner ------------------------------------------------------------------------------------------------------------
def run_suite(base: Path, safeguards: dict[str, bool] | None = None, only: list[str] | None = None, raw: Path | None = None) -> list[TestOutcome]:
    out = []
    for tid, name, cat, inv, fn in TESTS:
        if only and tid not in only:
            continue
        o = TestOutcome(tid, name, cat, inv)
        L = Lab(base, tid, safeguards)
        try:
            asserts, measured = fn(L)
            o.assertions = {k: {"observed": v[0], "expected": v[1], "held": v[0] == v[1]} for k, v in asserts.items()}
            o.measured = measured
        except Exception as e:  # noqa: BLE001 - a crashed test is a failed test, recorded, never hidden
            o.error = f"{type(e).__name__}: {e}"
        if raw:
            L.dump(raw, tid)
        out.append(o)
    return out
