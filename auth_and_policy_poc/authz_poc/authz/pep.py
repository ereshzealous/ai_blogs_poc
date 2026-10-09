"""Policy enforcement point: the tool gateway. Every tool call passes through `invoke`; there is no other path.

    request -> PDP -> DENY                   -> block, explain (agent-facing only), log (everything)
                   -> ALLOW                  -> credential for this call, execute, log
                   -> ALLOW_WITH_CONSTRAINTS -> reshape the call to fit the constraints, credential, execute, log
                   -> ALLOW_WITH_APPROVAL    -> open an approval bound to this exact call, log, stop.
                                                The agent re-submits the same call with the approval id:
                                                check the binding, authorize again, then credential and execute.

Fail closed: if the PDP raises or returns something that is not one of the four outcomes, the gateway denies.

Non-bypassable: the runtime holds no tool credentials. Tools accept only a credential the broker issued for exactly
this call, after a permitting decision (authz/broker.py). In production, network policy must also leave the runtime no
other route to the tools; the POC models the credential half of that, not the network half.
"""

from __future__ import annotations

from typing import Any

from .approvals import ApprovalGate
from .audit import AuditLog
from .broker import CredentialBroker
from .model import APPROVAL, DENY, STRICTNESS, Decision, Request, digest
from .pdp import PDP
from .pip import SOURCES, ts


class Gateway:
    def __init__(self, pdp: PDP, approvals: ApprovalGate, tools: dict[str, Any], audit: AuditLog, broker: CredentialBroker):
        self.pdp, self.approvals, self.tools, self.audit, self.broker = pdp, approvals, tools, audit, broker

    def invoke(self, req: Request) -> dict[str, Any]:
        d = self._decide(req)
        self._log_decision(req, d)
        if d.decision == DENY:
            return {"status": "denied", **d.public()}
        if d.decision == APPROVAL:
            apr = self.approvals.open(req, d)
            self.audit.write("approval.requested", req.context["time"], apr)
            return {"status": "pending_approval", "approval_id": apr["approval_id"], **d.public()}
        return self._execute(req, d)

    def approve(self, approval_id: str, approver: str, time: str) -> dict[str, Any]:
        ok, why = self.approvals.decide(approval_id, approver, time)
        self.audit.write("approval.granted" if ok else "approval.rejected", time,
                         {"approval_id": approval_id, "approver": approver, "result": why})
        return {"approved": ok, "reason": why}

    def execute_approved(self, approval_id: str, req: Request) -> dict[str, Any]:
        """The agent re-submits the call. The approval covers it only if it is the exact call that was approved, under
        the same incident and policy version, unused and in date; and policy, evaluated again now, still says
        ALLOW_WITH_APPROVAL. An approval can satisfy an approval obligation. It can never turn a DENY into anything."""
        apr = self.approvals.pending.get(approval_id)
        now = req.context["time"]
        problem = (
            "unknown approval" if apr is None else
            "approval already used" if apr["status"] == "used" else
            "approval not granted" if apr["status"] != "approved" else
            "approval does not cover this call" if req.fingerprint() != apr["request_fingerprint"] else
            "approval is for another incident" if req.context.get("incident_id") != apr["incident_id"] else
            "policy changed since approval" if self.pdp.policy["version"] != apr["policy_version"] else
            "approval expired" if ts(now) >= ts(apr["expires_at"]) else None
        )
        if problem:
            self.audit.write("approval.binding_failed", now, {"approval_id": approval_id, "problem": problem,
                                                              "request_fingerprint": req.fingerprint()})
            return {"status": "denied", "code": "APPROVAL_NOT_APPLICABLE", "reason": problem}
        d = self._decide(req)  # time of check is not time of use
        self._log_decision(req, d, recheck_of=apr["decision_id"])
        if d.decision != APPROVAL:  # the world changed while we waited (a freeze started, the incident closed ...)
            return {"status": "denied", **d.public()}
        out = self._execute(req, d, approval=apr)
        self.approvals.consume(approval_id, now)
        return out

    # ------------------------------------------------------------------------------------------------------------
    def _decide(self, req: Request) -> Decision:
        """Ask the PDP. No answer, or an answer that is not one of the four outcomes, is a DENY."""
        try:
            d = self.pdp.evaluate(req)
            if d.decision not in STRICTNESS or not isinstance(d.constraints, dict):
                raise ValueError(f"invalid policy response {d.decision!r}")
            return d
        except Exception as e:  # noqa: BLE001  (fail closed on anything)
            d = Decision(DENY, [f"Policy decision unavailable: {type(e).__name__}: {e}"], "POLICY_UNAVAILABLE",
                         "Authorization is unavailable", "Retry later or escalate to a human operator", {},
                         str(getattr(self.pdp, "policy", {}).get("version", "unknown")), [], ["gateway.pdp-unavailable"], {})
            d.decision_id = "dec-" + digest([req.as_dict(), d.decision, d.matched], 10)
            return d

    def _execute(self, req: Request, d: Decision, approval: dict | None = None) -> dict[str, Any]:
        args, applied = dict(req.arguments), []
        if "maxPods" in d.constraints and len(args.get("pods", [])) > d.constraints["maxPods"]:
            applied.append(f"maxPods={d.constraints['maxPods']} (requested {len(args['pods'])})")
            args["pods"] = args["pods"][: d.constraints["maxPods"]]
        if "redact" in d.constraints:
            args["redact"] = d.constraints["redact"]
            applied.append("redact=" + ",".join(d.constraints["redact"]))
        now = req.context["time"]
        cred = self.broker.issue(d, req.action, req.resource, req.environment, args, now, approval)
        output = self.tools[req.action](resource=req.resource, environment=req.environment, now=now, credential=cred, **args)
        self.audit.write("tool.executed", now, {
            "decision_id": d.decision_id, "action": req.action, "resource": req.resource, "environment": req.environment,
            "arguments": args, "constraints_applied": applied,
            "approval_id": approval and approval["approval_id"], "approved_by": approval and approval["approved_by"],
            "credential": {"id": cred["id"], "expires_at": cred["expires_at"], "single_use": True},
            "output": output,
        })
        return {"status": "executed", "decision": d.decision, "constraints_applied": applied, "output": output}

    def _log_decision(self, req: Request, d: Decision, recheck_of: str | None = None) -> None:
        self.audit.write("policy.decision", req.context["time"], {
            "decision_id": d.decision_id, "recheck_of": recheck_of,
            "principal": req.principal, "acting_for": req.acting_for,
            "action": req.action, "resource": req.resource, "environment": req.environment,
            "arguments": req.arguments, "request_fingerprint": req.fingerprint(),
            "policy_version": d.policy_version, "grants": d.grants, "delegation_chain": d.delegation_chain,
            "matched_rules": d.matched, "attributes": d.attributes,
            "attribute_sources": {k: SOURCES.get(k, "unknown") for k in d.attributes},
            "decision": d.decision, "reason": d.reason, "constraints": d.constraints,
            "agent_view": d.public(),
        })
