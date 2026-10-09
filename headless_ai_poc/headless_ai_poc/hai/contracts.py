"""The contracts of the headless boundary.

Every head (chat, web, API, event, workflow, scheduler, CI/CD, another agent) speaks exactly two of these:
it sends an InvocationEnvelope and it receives an ExecutionView.  Nothing else crosses the boundary.  All models are
extra="forbid": a head that invents a field is rejected, not silently accepted.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


Intent = Literal["investigate_incident", "health_sweep", "release_check"]
Channel = Literal["chat", "web", "api", "event", "workflow", "scheduler", "cicd", "agent"]


# ---- consumer -> runtime -----------------------------------------------------------------------------------------------


class Subject(Strict):
    service: str
    environment: Literal["production", "staging"]
    signal: dict[str, Any] = Field(default_factory=dict, description="What the head observed, e.g. {'error_rate': 0.14}")


class InvocationEnvelope(Strict):
    """One request for intelligence, whatever head it came from."""

    envelope_version: Literal["1.0"] = "1.0"
    event_id: str = Field(description="Unique per delivery source; the dedupe key together with source")
    source: str = Field(description="Where it came from, e.g. monitoring/datadog or chat/slack")
    channel: Channel
    intent: Intent
    subject: Subject
    fingerprint: str = Field(description="Stable key of the underlying situation (a re-fired alert keeps it)")
    invoker: str = Field(description="The authenticated principal that invoked; resolved at ingress, never taken from the payload")
    on_behalf_of: str | None = Field(default=None, description="A human the invocation acts for, if any")
    correlation_id: str
    causation_id: str | None = None
    reply_to: str | None = None
    question: str | None = None


# ---- identity -----------------------------------------------------------------------------------------------------------


class ExecutionIdentity(Strict):
    """Who is acting, and with whose authority.  Built by token exchange at the start of every execution."""

    invoker: str                      # who triggered it (a workload, a human, another agent)
    on_behalf_of: str | None          # a human whose authority is delegated, if any
    agent: str                        # the agent identity doing the reasoning, with version
    workload: str                     # the runtime workload the code runs as
    scopes: list[str]                 # intersection of delegable(invoker) and agent scopes
    token_id: str
    issued_at: float
    expires_at: float


# ---- capability calls --------------------------------------------------------------------------------------------------


class CapabilityCall(Strict):
    capability: str
    arguments: dict[str, Any]
    step: str


class PolicyDecision(Strict):
    effect: Literal["ALLOW", "DENY", "APPROVAL_REQUIRED"]
    rule: str
    reason: str
    required_role: str | None = None
    required_scope: str | None = None


class CapabilityResult(Strict):
    capability: str
    status: Literal["ok", "denied", "approval_required", "error"]
    decision: PolicyDecision | None = None
    output: Any = None
    error: str | None = None
    attempts: int = 0
    untrusted: bool = False
    approval_id: str | None = None


# ---- reasoning outputs (data, never instructions) ----------------------------------------------------------------------


class Hypothesis(Strict):
    id: str
    statement: str
    evidence: list[str]
    against: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]


class Assessment(Strict):
    service: str
    environment: str
    summary: str
    hypotheses: list[Hypothesis]
    leading: str
    recommendation: dict[str, Any] | None = None


# ---- runtime -> consumer ----------------------------------------------------------------------------------------------


class ExecutionView(Strict):
    execution_id: str
    correlation_id: str
    intent: Intent
    status: Literal["ACCEPTED", "RUNNING", "WAITING_APPROVAL", "COMPLETED", "ESCALATED", "REJECTED", "FAILED"]
    step: str
    invoker: str
    channel: str
    assessment: Assessment | None = None
    incident_id: str | None = None
    approval: dict[str, Any] | None = None
    action: dict[str, Any] | None = None
    verdict: dict[str, Any] | None = None
    joined: bool = False               # true when this delivery joined an execution that already existed


class Accepted(Strict):
    execution_id: str
    status_url: str
    duplicate: bool = False


class Rejected(Strict):
    reason: str
    stage: Literal["authenticate", "validate", "authorize_invocation", "dead_letter"]


class ApprovalDecision(Strict):
    approval_id: str
    decided_by: str
    approve: bool
    digest: str = Field(description="The digest of the exact call being approved; a mismatch is a forgery")
    reason: str = ""
