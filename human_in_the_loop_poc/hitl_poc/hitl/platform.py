"""The composition root and the incident runtime: event ingress, orchestration, the proposal builder and the reasoners.

The runtime (an agent running as svc.hitl-runtime) can read, analyze, recommend and keep records automatically.  For a
consequential write it can only *propose*: it builds an ActionProposal bound to an action digest and hands it to the
approval service.  It holds no approver credential and no enterprise credential.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from hitl.approvals import ApprovalService
from hitl.base import AuditLog, Clock, Directory, Telemetry, connect, sha256, short_id
from hitl.contracts import Action, ActionProposal, Party, PolicyRef, Requester, Target
from hitl.enterprise import Enterprise
from hitl.gate import CapabilityGateway, ExecutionGate
from hitl.policy import PolicyEngine

AGENT = "agent.incident-investigator"
RUNTIME = "svc.hitl-runtime"
ON_BEHALF_OF = "production-incident-platform"
DELEGATION = "dlg-incident-remediation"
INSTRUCTION = re.compile(r"(ignore (all |previous )?(instructions|policy)|SYSTEM:|approval already granted)", re.I)


class EvidenceReasoner:
    """Deterministic on purpose: the suite tests control semantics, not model intelligence.  A model plugs in here."""

    name = "evidence-reasoner-1.0"

    def assess(self, ev: dict[str, Any]) -> dict[str, Any]:
        hist, health = ev["history"], ev["health"]
        cur = hist["current"]
        prev = hist["history"][hist["history"].index(cur) - 1]
        errors = [l["line"] for l in ev["logs"] if l["level"] == "ERROR"]
        injected = [l["line"] for l in ev["logs"] if INSTRUCTION.search(l["line"])]
        return {"hypothesis": f"deployment {cur} caused the error rate rise to {health['error_rate']:.0%}", "confidence": "high",
                "from_version": cur, "to_version": prev, "signals": len(errors), "untrusted_instructions_ignored": len(injected),
                "evidence_refs": [f"deployment:{cur}", ev["traces"]["id"], "log-cluster:token-vault-timeout", ev["known"][0]["id"]]}


class Platform:
    def __init__(self, workdir: Path, clock: Clock | None = None, policy_file: str = "policy.yaml"):
        workdir.mkdir(parents=True, exist_ok=True)
        self.clock = clock or Clock()
        self.db = connect(workdir / "platform.db")
        self.audit = AuditLog(self.db, self.clock)
        self.tel = Telemetry(self.clock)
        self.directory = Directory()
        self.policy = PolicyEngine(policy_file)
        self.ent = Enterprise(self.clock)
        self.approvals = ApprovalService(workdir / "approvals.db", self.clock, self.directory, self.policy, self.audit)
        self.gateway = CapabilityGateway(self.ent, self.tel)
        self.gate = ExecutionGate(self.approvals, self.policy, self.directory, self.ent, self.gateway, self.audit, self.tel, self.clock)
        self.reasoner = EvidenceReasoner()
        self.inbox: list[str] = []
        self.events: dict[tuple[str, str], str] = {}          # (source, event_id) -> correlation id
        self.open: dict[str, str] = {}                         # fingerprint -> correlation id
        self.executions: dict[str, dict[str, Any]] = {}
        # runtime-local capabilities (analysis and recommendation run inside the runtime, still through the gateway)
        self.ent.correlateIncidentEvidence = lambda service, environment, evidence: self.reasoner.assess(evidence)
        self.ent.recommendRollback = lambda service, environment, assessment: {
            "capability": "rollbackDeployment", "from_version": assessment["from_version"], "to_version": assessment["to_version"],
            "reason": f"Error rate rose to 14% after {assessment['from_version']}; {assessment['signals']} matching error signals."}

    # ---- identity ------------------------------------------------------------------------------------------------
    def identity(self, invoker: str, runtime: str = RUNTIME) -> dict[str, str]:
        ver = self.directory.principals[AGENT].get("version", "0")
        return {"invoker": invoker, "agent": f"{AGENT}@{ver}", "runtime": runtime, "on_behalf_of": ON_BEHALF_OF, "delegation": DELEGATION}

    # ---- ingress -------------------------------------------------------------------------------------------------
    def receive(self, credential: str, event: dict[str, Any]) -> dict[str, Any]:
        invoker = self.directory.authenticate(credential)
        key = (event["source"], event["id"])
        if key in self.events:
            corr = self.events[key]
            self.audit.record("event.duplicate", corr, None, source=event["source"], event_id=event["id"])
            return {"correlation_id": corr, "duplicate": True, **self.view(corr)}
        fp = f"degradation:{event['service']}:{event['environment']}"
        if fp in self.open:
            corr = self.events[key] = self.open[fp]
            self.audit.record("event.joined", corr, None, source=event["source"], event_id=event["id"], fingerprint=fp)
            return {"correlation_id": corr, "joined": True, **self.view(corr)}
        corr = short_id("cor", fp, event["id"])
        self.events[key] = corr
        self.open[fp] = corr
        self.audit.record("event.received", corr, None, source=event["source"], event_id=event["id"], service=event["service"],
                          environment=event["environment"], signal=event.get("signal"))
        self.investigate(corr, event, invoker)
        return {"correlation_id": corr, **self.view(corr)}

    # ---- the incident workflow -----------------------------------------------------------------------------------
    def _auto(self, corr: str, ident: dict[str, str], capability: str, service: str, env: str, **args: Any) -> Any:
        a = Action(capability=capability, target=Target(service=service, environment=env), arguments=args, policy=self.policy.ref(),
                   risk=self.policy.tier(capability) or "unknown")
        r = self.gate.run_auto(a, corr, ident)
        if not r.allowed:
            raise RuntimeError(f"{capability}: {r.code}")
        return r.output

    def investigate(self, corr: str, event: dict[str, Any], invoker: str) -> None:
        svc, env = event["service"], event["environment"]
        ident = self.identity(invoker)
        x = self.executions[corr] = {"correlation_id": corr, "execution_id": short_id("exec", event["source"], event["id"]), "identity": ident,
                                     "service": svc, "environment": env, "proposals": []}
        self.audit.record("execution.started", corr, None, execution_id=x["execution_id"], **ident)
        with self.tel.span("run", corr, "incident-investigation"):
            ev = {"health": self._auto(corr, ident, "getDeploymentHealth", svc, env), "logs": self._auto(corr, ident, "getLogs", svc, env),
                  "traces": self._auto(corr, ident, "getTraceSummary", svc, env), "history": self._auto(corr, ident, "getDeploymentHistory", svc, env),
                  "known": self._auto(corr, ident, "getKnownIncidents", svc, env)}
            assessment = self._auto(corr, ident, "correlateIncidentEvidence", svc, env, evidence=ev)
            x["assessment"] = assessment
            self.audit.record("evidence.assessed", corr, None, hypothesis=assessment["hypothesis"], confidence=assessment["confidence"],
                              evidence_refs=assessment["evidence_refs"], untrusted_instructions_ignored=assessment["untrusted_instructions_ignored"])
            x["incident"] = self._auto(corr, ident, "createIncident", svc, env, title=f"{svc} error rate {ev['health']['error_rate']:.0%}")["incident_id"]
            rec = self._auto(corr, ident, "recommendRollback", svc, env, assessment=assessment)
            x["recommendation"] = rec
            p = self.propose(corr, ident, rec["capability"], svc, env, {"from_version": rec["from_version"], "to_version": rec["to_version"]},
                             reason=rec["reason"], evidence_refs=assessment["evidence_refs"], history=ev["history"])
            x["proposals"].append(p.proposal_id)

    def propose(self, corr: str, ident: dict[str, str], capability: str, service: str, env: str, arguments: dict[str, Any], *,
                reason: str, evidence_refs: list[str], history: dict[str, Any] | None = None) -> ActionProposal:
        """Build the ActionProposal, store it, evaluate policy and route it: DENIED, EXECUTING (allowed) or AWAITING_APPROVAL."""
        history = history or self.ent.getDeploymentHistory(service, env)
        cur = history["current"]
        caps = self.policy.capabilities.get(capability, {})
        d = self.policy.evaluate(capability, service, env)
        x = self.executions.get(corr, {})
        action = Action(capability=capability, target=Target(service=service, environment=env), arguments=arguments,
                        preconditions={"current_version": cur}, policy=self.policy.ref(), risk=d.tier)
        digest = action.digest()
        pid = short_id("prop", corr, digest)
        now = self.clock.now()
        p = ActionProposal(proposal_id=pid, execution_id=x.get("execution_id", short_id("exec", corr)), correlation_id=corr,
                           incident_id=x.get("incident") or "", requested_by=Requester(agent_id=AGENT, runtime=ident.get("runtime", RUNTIME), invoker=ident["invoker"]),
                           acting_on_behalf_of=Party(type="service", id=ON_BEHALF_OF), delegation_chain_ref=ident.get("delegation", DELEGATION), capability=capability,
                           target=action.target, arguments=arguments, risk=d.tier, reason=reason, evidence_refs=evidence_refs,
                           preconditions=action.preconditions,
                           context={"impact": caps.get("impact", ""), "recovery": caps.get("recovery", ""),
                                    "deployment_author": history["authors"].get(cur, "unknown"), "autonomy": self.policy.tiers.get(d.tier, {}).get("autonomy", ""),
                                    "severity": self.ent.severity(x["incident"]) if x.get("incident") else ""},
                           policy=PolicyRef(policy_id=self.policy.policy_id, version=self.policy.version, decision=d.decision, rule=d.rule,
                                            decision_id=d.decision_id, required_approvals=d.required_approvals),
                           created_at=now, expires_at=now + float(self.policy.approval["ttl_s"]), idempotency_key=sha256(f"idem|{pid}|{digest}"),
                           action_digest=digest)
        self.approvals.create(p)
        self.audit.record("proposal.created", corr, pid, capability=capability, target=p.target.model_dump(), arguments=arguments, risk=d.tier,
                          reason=reason, evidence_refs=evidence_refs, preconditions=p.preconditions, action_digest=digest, **ident)
        self.approvals.transition(pid, "PROPOSED", "POLICY_EVALUATED", RUNTIME)
        self.audit.record("policy.evaluated", corr, pid, capability=capability, decision=d.decision, rule=d.rule, tier=d.tier, reason=d.reason,
                          policy_id=self.policy.policy_id, policy_version=self.policy.version, policy_decision_id=d.decision_id,
                          required_approvals=d.required_approvals)
        if d.decision == "DENY":
            self.approvals.transition(pid, "POLICY_EVALUATED", "REJECTED", RUNTIME, note=f"policy DENY ({d.rule})")
        elif d.decision == "REQUIRE_APPROVAL":
            self.approvals.transition(pid, "POLICY_EVALUATED", "PENDING_APPROVAL", RUNTIME)
            self.inbox.append(pid)
            self.audit.record("approval.requested", corr, pid, required_role=d.required_role, required_approvals=d.required_approvals,
                              expires_at=p.expires_at, action_digest=digest, shown={"capability": capability, "target": p.target.model_dump(),
                              "arguments": arguments, "precondition": p.preconditions, "reason": reason, "severity": p.context.get("severity", ""),
                              "policy": f"{self.policy.policy_id} v{self.policy.version}", "requested_by": ident.get("agent"),
                              "authority": p.delegation_chain_ref, "expires_at": p.expires_at})
        return p

    def close(self, corr: str) -> None:
        """The incident is resolved: a later alert for the same service opens a new incident and a new workflow."""
        self.open = {k: v for k, v in self.open.items() if v != corr}

    def duplicate_workflow(self, corr: str) -> str:
        """A second workflow instance for the same incident (an operator re-runs it): same incident, own execution and request."""
        x = self.executions[corr]
        c2 = short_id("cor", corr, "second-instance")
        self.executions[c2] = {**x, "correlation_id": c2, "execution_id": short_id("exec", corr, "second-instance"), "proposals": []}
        self.audit.record("execution.started", c2, None, execution_id=self.executions[c2]["execution_id"], duplicate_of=corr, **x["identity"])
        rec = x["recommendation"]
        q = self.propose(c2, x["identity"], rec["capability"], x["service"], x["environment"],
                         {"from_version": rec["from_version"], "to_version": rec["to_version"]}, reason=rec["reason"],
                         evidence_refs=x["assessment"]["evidence_refs"])
        self.executions[c2]["proposals"].append(q.proposal_id)
        return q.proposal_id

    # ---- views ---------------------------------------------------------------------------------------------------
    def view(self, corr: str) -> dict[str, Any]:
        x = self.executions.get(corr, {})
        props = [self.approvals.get(pid) for pid in x.get("proposals", [])]
        return {"execution_id": x.get("execution_id"), "incident": x.get("incident"),
                "proposals": [{"proposal_id": r["id"], "state": r["state"], "capability": r["proposal"].capability} for r in props if r]}

    def presented_action(self, pid: str, mutate: dict[str, Any] | None = None) -> Action:
        """The action the agent presents for execution: the proposal's, or (to prove the gate notices) a mutated one."""
        p: ActionProposal = self.approvals.get(pid)["proposal"]
        a = p.action().model_dump()
        for k, v in (mutate or {}).items():
            if k in ("service", "environment"):
                a["target"][k] = v
            elif k == "capability":
                a["capability"] = v
                if v == "restartDeployment":
                    a["arguments"] = {}
            elif k == "service_only":
                a["target"]["service"] = v
            else:
                a["arguments"][k] = v
        if a["capability"] == "deleteProductionNamespace":
            a["arguments"], a["risk"] = {}, "prohibited"
        return Action.model_validate(a)

    def execute_proposal(self, pid: str, mutate: dict[str, Any] | None = None, retry: bool = False, runtime: str | None = None,
                         recover: bool = False) -> Any:
        """Ask the gate (arm C) to execute a proposal's action: the resume step of the paused workflow."""
        p: ActionProposal = self.approvals.get(pid)["proposal"]
        action = self.presented_action(pid, mutate)
        ident = dict(self.executions.get(p.correlation_id, {}).get("identity") or self.identity(p.requested_by.invoker))
        if runtime:
            ident["runtime"] = runtime
        if retry:
            return self.gate.retry(pid, action, p.correlation_id, ident)
        return self.gate.execute(pid, action, p.correlation_id, ident, recover=recover)
