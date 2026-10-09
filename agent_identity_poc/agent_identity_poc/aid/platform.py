"""The composition root: one simulated enterprise and one agent platform, in one of three identity modes.

    chain          the production pattern: token exchange, delegation, attested runtimes, broker, gateway, full audit
    shared_sa      the anti-pattern: one automation account for everything
    impersonation  the agent is handed the human's token

The runtime side of an execution lives here too: it presents its workload's SVID with every call, and when a token
has expired it re-exchanges it (or, in the unsafe variant used by I7, extends it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from aid.approvals import Approvals
from aid.attestation import Attestor
from aid.audit import AuditLog
from aid.baselines import baseline_record, shared_credentials, user_credentials
from aid.broker import TokenBroker
from aid.config import Clock, load, short_id
from aid.contracts import CapabilityCall, Decision, EventProvenance, ExecutionToken, ToolCredential
from aid.directory import Directory
from aid.gateway import CapabilityGateway, chain_fields
from aid.tools import build_tools
from aid.trust import TrustError, TrustLayer

Mode = Literal["chain", "shared_sa", "impersonation"]


@dataclass
class Execution:
    execution_id: str
    agent: str
    mode: str
    invoker: str
    on_behalf_of: str | None
    token: ExecutionToken | None = None
    creds: dict[str, ToolCredential] = field(default_factory=dict)
    halted: str | None = None
    refresh: Literal["reexchange", "extend"] = "reexchange"
    ctx: dict[str, Any] = field(default_factory=dict)


class Platform:
    def __init__(self, mode: Mode = "chain", clock: Clock | None = None):
        self.mode = mode
        self.clock = clock or Clock()
        self.d = Directory()
        self.att = Attestor(self.clock, [r["spiffe"] for r in self.d.runtimes.values()])
        self.trust = TrustLayer(self.d, self.att, self.clock)
        self.broker = TokenBroker(self.clock)
        self.approvals = Approvals(self.d, self.clock)
        self.audit = AuditLog(self.clock)
        self.tools = build_tools(self.clock)
        self.gateway = CapabilityGateway(self.trust, self.broker, self.approvals, self.audit, self.tools)
        self.caps = load("capabilities.yaml")["capabilities"]
        self.sa_generation = 0
        self.shared = shared_credentials(self.clock)
        self._n = 0

    # ---- ingress + identity ------------------------------------------------------------------------------------------
    def start(self, channel: str, credential: str, agent: str, sso: str | None = None,
              provenance: EventProvenance | None = None) -> Execution:
        invoker = self.d.authenticate(credential, channel)
        obo = self.d.authenticate(sso, "sso") if sso else None
        self._n += 1
        xid = short_id("exe", invoker, obo, agent, self.clock.now(), self._n)
        ex = Execution(xid, agent, self.mode, invoker, obo)
        if self.mode == "chain":
            ex.token = self.trust.exchange(xid, invoker, credential, agent, obo, provenance)
            self.audit.record("execution.started", **chain_fields(ex.token), execution_id=xid)
        elif self.mode == "shared_sa":
            ex.creds = self.shared
            self.audit.record("execution.started", execution_id=xid, credential=self.shared["kubernetes"].principal)
        else:
            if obo:
                ex.creds, ex.ctx["subject"] = user_credentials(self.clock, self.d.oidc(obo), xid), obo
            else:
                ex.creds = self.shared
            self.audit.record("execution.started", execution_id=xid, subject=ex.ctx.get("subject"),
                              fallback=None if obo else "shared account")
        return ex

    def delegate(self, parent: Execution, to_agent: str) -> Execution:
        self._n += 1
        xid = short_id("exe", parent.execution_id, to_agent, self.clock.now(), self._n)
        ex = Execution(xid, to_agent, self.mode, parent.invoker, parent.on_behalf_of, creds=parent.creds, ctx=dict(parent.ctx))
        if self.mode == "chain":
            ex.token = self.trust.delegate(parent.token, to_agent, xid)
            self.audit.record("execution.delegated", **chain_fields(ex.token), execution_id=xid, parent=parent.execution_id)
        return ex

    # ---- one capability call ------------------------------------------------------------------------------------------
    def svid(self, ex: Execution) -> str:
        return self.att.current(ex.token.cnf) if ex.token else ""

    def call(self, ex: Execution, call: CapabilityCall, approval_id: str | None = None, presenter_svid: str | None = None) -> Decision:
        if ex.halted:
            return Decision(effect="REJECTED", rule="halted", reason=ex.halted)
        if self.mode == "chain":
            if ex.token.exp <= self.clock.now() and presenter_svid is None:
                try:
                    ex.token = self.trust.reexchange(ex.token) if ex.refresh == "reexchange" else self.trust.extend(ex.token)
                    self.audit.record("token.refreshed", **chain_fields(ex.token), execution_id=ex.execution_id, how=ex.refresh)
                except TrustError as e:
                    ex.halted = f"re-exchange refused: {e}"
                    self.audit.record("execution.halted", execution_id=ex.execution_id, reason=ex.halted)
                    return Decision(effect="REJECTED", rule="re-exchange", reason=ex.halted)
            return self.gateway.call(ex.token, presenter_svid or self.svid(ex), call, approval_id)
        return self._baseline_call(ex, call, approval_id)

    def _baseline_call(self, ex: Execution, call: CapabilityCall, approval_id: str | None) -> Decision:
        cap = self.caps.get(call.capability)
        if cap is None:
            return Decision(effect="DENY", rule="P0-unregistered", reason="unregistered")
        authorized_by = None
        if cap["risk"] == "high" and cap["kind"] == "write":
            dg = self.approvals.call_digest(ex.execution_id, call.capability, call.arguments)
            if approval_id is None:
                a = self.approvals.request(ex.execution_id, call.capability, call.arguments, "incident-commander", cap["grant"], ex.agent)
                self.audit.record("approval.requested", execution_id=ex.execution_id, capability=call.capability, approval_id=a["approval_id"],
                                  requested_by=self.shared["kubernetes"].principal if not ex.ctx.get("subject") else ex.ctx["subject"])
                return Decision(effect="REQUIRE_APPROVAL", rule="P2-high-risk-production", reason="needs incident-commander",
                                approval_id=a["approval_id"])
            a = self.approvals.consume(approval_id, dg)
            if a is None:
                return Decision(effect="REJECTED", rule="P2-high-risk-production", reason="approval invalid for this call")
            authorized_by = a["decided_by"]
        cred = ex.creds[cap["system"]]
        status, msg = self.tools[cap["system"]].call(cred, cap["verb"], call.arguments)
        self.audit.record("capability.call", **baseline_record(self.mode, ex.ctx, call.capability, call.arguments, cred, authorized_by,
                                                                approval_id if authorized_by else None, status == 200))
        return Decision(effect="EXECUTED" if status == 200 else "REJECTED", rule="baseline" if status == 200 else f"tool-{status}", reason=msg,
                        output={"tool_principal": cred.principal, "credential_id": cred.credential_id})

    def approve(self, approval_id: str, who: str, dg: str | None = None) -> tuple[bool, str]:
        ok, why = self.approvals.decide(approval_id, who, dg)
        self.audit.record("approval.decided", approval_id=approval_id, decided_by=who, accepted=ok, reason=why)
        return ok, why

    # ---- revocation levers, one per layer ---------------------------------------------------------------------------
    def revoke_delegation(self, human: str) -> None:
        self.d.revoked_grants.add(TrustLayer.grant_id(human))
        self.audit.record("revoked", layer="delegation", target=human)

    def revoke_invoker_credential(self, credential: str) -> None:
        self.d.revoked_credentials.add(credential)
        self.audit.record("revoked", layer="invoker_credential", target=credential)

    def disable_agent(self, agent: str) -> None:
        self.d.disabled_agents.add(self.d.agent_ref(agent))
        self.audit.record("revoked", layer="agent", target=self.d.agent_ref(agent))

    def quarantine_runtime(self, runtime: str) -> None:
        self.att.quarantined.add(self.d.spiffe(runtime))
        self.audit.record("revoked", layer="workload", target=self.d.spiffe(runtime))

    def disable_tool_identity(self, tool_identity: str) -> None:
        self.broker.disabled.add(tool_identity)
        ident = self.broker.identities[tool_identity]
        self.tools[ident["system"]].disabled_principals.add(ident["principal"])
        self.audit.record("revoked", layer="tool_identity", target=tool_identity)

    def rotate_shared_account(self) -> None:
        """The only lever the shared account has: every old secret dies, for every agent, until each is redeployed."""
        for s, c in self.shared.items():
            self.tools[s].revoked_credentials.add(c.credential_id)
        self.sa_generation += 1
        self.audit.record("revoked", layer="shared_account", target="ai-automation", generation=self.sa_generation)
