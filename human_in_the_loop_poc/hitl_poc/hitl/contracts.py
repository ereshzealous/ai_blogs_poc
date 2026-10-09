"""The HITL contracts.  extra="forbid" everywhere: a field nobody declared is an error, not a silent extension.

The objects that matter are the ActionProposal (what the machine intends, bound to an action digest), the
ApprovalDecision (what a human decided about exactly that digest) and the ApprovalArtifact (the POC's explicit approval
contract: one record that binds request, action, policy decision, identity context and decision).  The approver's
identity in a decision is always the authenticated principal, never a value taken from a request body or model output.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from hitl.base import canonical, iso, sha256


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Target(Strict):
    service: str
    environment: Literal["production", "staging"]


class Action(Strict):
    """The consequential side effect, and nothing else.  Its digest is what a human approves."""

    capability: str
    target: Target
    arguments: dict[str, Any] = Field(default_factory=dict)
    preconditions: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, str]                       # {"policy_id": ..., "version": ...}
    risk: str

    def digest(self) -> str:
        return sha256(canonical(self.model_dump()))


class Requester(Strict):
    agent_id: str
    runtime: str
    invoker: str


class Party(Strict):
    type: Literal["service", "human", "workload"]
    id: str


class PolicyRef(Strict):
    policy_id: str
    version: str
    decision: Literal["ALLOW", "DENY", "REQUIRE_APPROVAL"]
    rule: str
    decision_id: str = ""
    required_approvals: int = 0


class ActionProposal(Strict):
    proposal_id: str
    execution_id: str
    correlation_id: str
    incident_id: str = ""
    requested_by: Requester
    acting_on_behalf_of: Party
    delegation_chain_ref: str = ""
    capability: str
    target: Target
    arguments: dict[str, Any]
    risk: str
    reason: str
    evidence_refs: list[str]
    preconditions: dict[str, Any]
    context: dict[str, Any] = Field(default_factory=dict, description="Display context for the approver: impact, recovery, deployment author, severity")
    policy: PolicyRef
    created_at: float
    expires_at: float
    idempotency_key: str
    action_digest: str

    def action(self) -> Action:
        return Action(capability=self.capability, target=self.target, arguments=self.arguments, preconditions=self.preconditions,
                      policy={"policy_id": self.policy.policy_id, "version": self.policy.version}, risk=self.risk)


class Approver(Strict):
    identity: str
    roles: list[str]
    eligible_because: str = ""                   # the role and relationship that made this principal eligible


class ApprovalDecision(Strict):
    approval_id: str
    proposal_id: str
    action_digest: str
    decision: Literal["approve", "deny"]
    approver: Approver
    decided_at: float
    reason: str
    channel: str = "api"                         # how the decision arrived: api, inbox, slack


class DecisionRequest(Strict):
    """What a client sends to POST /approvals/{id}/decision.  It cannot name the approver: that comes from the credential."""

    decision: Literal["approve", "deny"]
    action_digest: str
    reason: str = ""
    request_id: str | None = None


class GateResult(Strict):
    allowed: bool
    code: str
    state: str | None = None
    output: Any = None
    detail: str = ""
    checks: list[dict[str, Any]] = Field(default_factory=list)


class ApprovalArtifact(Strict):
    """The POC's approval contract (not an industry standard).  No credential or secret is ever part of it."""

    approval_id: str
    request_id: str
    incident_id: str
    subject: str                                 # the agent that asked, as a URI
    delegation_chain_ref: str
    policy_decision_id: str
    action: str
    resource: str
    parameters: dict[str, Any]
    action_digest: str
    risk: str
    environment: str
    requested_at: str
    expires_at: str
    approver: str
    approver_eligibility: str
    decision: Literal["APPROVED", "DENIED"]
    decision_at: str
    reason: str
    single_use: bool = True

    @classmethod
    def build(cls, p: ActionProposal, d: ApprovalDecision) -> "ApprovalArtifact":
        return cls(approval_id=d.approval_id, request_id=p.proposal_id, incident_id=p.incident_id, subject=f"agent://{p.requested_by.agent_id}",
                   delegation_chain_ref=p.delegation_chain_ref, policy_decision_id=p.policy.decision_id, action=p.capability,
                   resource=f"k8s://{p.target.environment}/{p.target.service}", parameters=dict(p.arguments), action_digest=f"sha256:{p.action_digest}",
                   risk=p.risk, environment=p.target.environment, requested_at=iso(p.created_at), expires_at=iso(p.expires_at),
                   approver=f"user://{d.approver.identity}", approver_eligibility=d.approver.eligible_because,
                   decision="APPROVED" if d.decision == "approve" else "DENIED", decision_at=iso(d.decided_at), reason=d.reason)
