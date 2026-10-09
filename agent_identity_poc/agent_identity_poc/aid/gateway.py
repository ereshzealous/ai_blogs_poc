"""The capability gateway: the only path from an agent to a tool, and the last place the whole chain is visible.

For every call:  validate the execution token and its presenter  ->  registered?  ->  scope held?  ->  high-risk
production write needs an approval bound to this exact call  ->  mint a tool credential for this capability class
->  call the tool  ->  write the audit record with the full chain.

Policy here is deliberately minimal (config/policies.yaml).  Authorization and policy are the next article; this module
exists to show what identity has to hand to them.
"""

from __future__ import annotations

from typing import Any

from aid.approvals import Approvals
from aid.audit import AuditLog
from aid.broker import BrokerError, TokenBroker
from aid.config import load
from aid.contracts import CapabilityCall, Decision, ExecutionToken
from aid.tools import Tool
from aid.trust import TrustLayer


def chain_fields(tok: ExecutionToken) -> dict[str, Any]:
    p = tok.provenance
    return {"event_source": p.source if p else None, "event_id": p.event_id if p else None, "event_rule": p.rule if p else None,
            "invoker": tok.invoker, "invoker_credential": tok.invoker_credential, "on_behalf_of": tok.on_behalf_of,
            "grant_id": tok.grant_id, "agent": tok.act.sub, "act_chain": tok.act.chain(), "workload": tok.cnf,
            "scopes": list(tok.scopes), "token_id": tok.token_id}


class CapabilityGateway:
    def __init__(self, trust: TrustLayer, broker: TokenBroker, approvals: Approvals, audit: AuditLog, tools: dict[str, Tool],
                 env: str = "production"):
        self.trust, self.broker, self.approvals, self.audit, self.tools, self.env = trust, broker, approvals, audit, tools, env
        self.caps = load("capabilities.yaml")["capabilities"]
        self.rules = load("policies.yaml")["rules"]

    def _policy(self, tok: ExecutionToken, name: str) -> tuple[str, str]:
        cap = self.caps.get(name)
        for r in self.rules:
            m = r["match"]
            if m == "unregistered" and cap is None:
                return r["effect"], r["id"]
            if m == "scope_not_held" and cap and cap["scope"] not in tok.scopes:
                return r["effect"], r["id"]
            if isinstance(m, dict) and cap and cap["risk"] == m["risk"] and self.env == m["env"] and cap["kind"] == "write":
                return r["effect"], r["id"]
            if m == "any":
                return r["effect"], r["id"]
        return "DENY", "P9-default"

    def call(self, tok: ExecutionToken, svid: str, call: CapabilityCall, approval_id: str | None = None) -> Decision:
        base = chain_fields(tok) | {"capability": call.capability, "arguments": call.arguments}
        why = self.trust.validate(tok, svid)
        if why:
            self.audit.record("capability.rejected", **base, reason=why, presenter=self.trust.att.verify(svid))
            return Decision(effect="REJECTED", rule="identity", reason=why)
        effect, rule = self._policy(tok, call.capability)
        if effect == "DENY":
            self.audit.record("capability.denied", **base, rule=rule)
            return Decision(effect="DENY", rule=rule, reason=f"{rule} for {call.capability} with scopes {list(tok.scopes)}")
        cap = self.caps[call.capability]
        authorized_by = None
        if effect == "REQUIRE_APPROVAL":
            dg = self.approvals.call_digest(tok.execution_id, call.capability, call.arguments)
            if approval_id is None:
                role = next(r["approver_role"] for r in self.rules if r["id"] == rule)
                a = self.approvals.request(tok.execution_id, call.capability, call.arguments, role, cap["grant"], tok.act.sub)
                self.audit.record("approval.requested", **base, rule=rule, approval_id=a["approval_id"], digest=dg)
                return Decision(effect="REQUIRE_APPROVAL", rule=rule, reason=f"needs {role} for {cap['grant']}", approval_id=a["approval_id"])
            a = self.approvals.consume(approval_id, dg)
            if a is None:
                self.audit.record("capability.rejected", **base, reason="approval missing, not approved, used or for another call")
                return Decision(effect="REJECTED", rule=rule, reason="approval invalid for this call")
            authorized_by = a["decided_by"]
        try:
            cred = self.broker.mint(tok, cap["class"])
        except BrokerError as e:
            self.audit.record("capability.rejected", **base, reason=str(e))
            return Decision(effect="REJECTED", rule="tool-identity", reason=str(e))
        status, msg = self.tools[cap["system"]].call(cred, cap["verb"], call.arguments)
        ok = status == 200
        self.audit.record("capability.call", **base, rule=rule, system=cap["system"], kind=cap["kind"], tool_principal=cred.principal,
                          tool_identity=cred.tool_identity, credential_id=cred.credential_id, credential_exp=cred.exp,
                          authorized_by=authorized_by, approval_id=approval_id if authorized_by else None, status="ok" if ok else f"tool {status}",
                          effect={"verb": cap["verb"], "object": call.arguments} if ok else None,
                          revocation={"delegation": tok.grant_id, "invoker_credential": tok.invoker_credential, "agent": tok.act.sub,
                                      "workload": tok.cnf, "tool_identity": cred.tool_identity})
        return Decision(effect="EXECUTED" if ok else "REJECTED", rule=rule if ok else f"tool-{status}", reason=msg,
                        output={"tool_principal": cred.principal, "credential_id": cred.credential_id})
