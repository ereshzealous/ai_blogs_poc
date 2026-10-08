"""Contracts.

1. The headless boundary, copied from F3 (headless_ai/headless_ai_poc/hai/contracts.py) without change of meaning: every
   consumer sends an InvocationEnvelope and receives an ExecutionView.  The same two shapes serve architectures A, B and
   C; no consumer ever sees an agent name.  extra="forbid".
2. Reasoning artifacts: what crosses a handoff between reasoning components (in-process in B, over A2A in C).  Each
   claim carries the evidence references (`ev-N`) of the gateway calls it rests on, so a receiver can check provenance
   instead of trusting a confident paragraph.  Parsed leniently (extra="ignore") because they are model output.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ---- the headless boundary (F3) -----------------------------------------------------------------------------------------

Intent = Literal["investigate_incident", "health_sweep", "release_check"]
Channel = Literal["chat", "web", "api", "event", "workflow", "scheduler", "cicd", "agent"]


class Subject(Strict):
    service: str
    environment: Literal["production", "staging"]
    signal: dict[str, Any] = Field(default_factory=dict)


class InvocationEnvelope(Strict):
    envelope_version: Literal["1.0"] = "1.0"
    event_id: str
    source: str
    channel: Channel
    intent: Intent
    subject: Subject
    fingerprint: str
    invoker: str
    on_behalf_of: str | None = None
    correlation_id: str
    causation_id: str | None = None
    reply_to: str | None = None
    question: str | None = None


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
    joined: bool = False


# ---- reasoning artifacts -----------------------------------------------------------------------------------------------

Category = Literal["deployment_regression", "config_change", "dependency_degradation", "db_saturation", "cache_degradation",
                   "resource_exhaustion", "capacity_surge", "no_fault", "undetermined"]
Confidence = Literal["low", "medium", "high"]
Decision = Literal["remediate", "no_action", "escalate"]
WriteTool = Literal["rollback_release", "restart_service", "scale_service", "flush_sessions", "revert_config", "set_feature_flag"]
ReadTool = Literal["get_incident", "get_runbook", "query_metrics", "search_logs", "get_dependencies", "list_deployments", "get_change_history"]


class RootCause(Lenient):
    category: Category
    summary: str
    affected_service: str = Field(description="The service where the cause lives (may differ from the alerting service)")
    evidence: list[str] = Field(default_factory=list, description="Evidence references (ev-N) this claim rests on")
    confidence: Confidence


class Alternative(Lenient):
    category: Category
    summary: str
    why_less_likely: str


class ActionSpec(Lenient):
    tool: WriteTool
    args: dict[str, Any]


class EvidenceRequest(Lenient):
    tool: ReadTool
    args: dict[str, Any]


class IncidentReport(Lenient):
    """Architecture A's final answer."""
    root_cause: RootCause
    alternatives: list[Alternative] = Field(default_factory=list)
    decision: Decision
    action_taken: ActionSpec | None = None
    rationale: str


class Diagnosis(Lenient):
    root_cause: RootCause
    alternatives: list[Alternative] = Field(default_factory=list)
    recommendation: Decision
    evidence_request: list[EvidenceRequest] = Field(default_factory=list,
                                                    description="Further read-only lookups needed before deciding (empty if none)")


class _Remediation(Lenient):
    """`tool` and `args` are required top-level fields: under constrained decoding a model reliably fills required keys
    and silently drops optional nested objects (dev-smoke F3).  `action` is derived, for code that wants one object."""

    decision: Decision
    tool: WriteTool | Literal["none"] = Field(description="The write tool to use when decision is remediate; 'none' otherwise")
    args: dict[str, Any] = Field(description="ALL arguments of the write tool, including service and environment ({} when tool is none)")
    rationale: str

    @model_validator(mode="after")
    def _action_when_remediating(self) -> "_Remediation":
        if self.decision == "remediate" and self.tool == "none":
            raise ValueError("decision is remediate but tool is 'none': give the write tool and all its arguments")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def action(self) -> ActionSpec | None:
        return ActionSpec(tool=self.tool, args=self.args) if self.decision == "remediate" and self.tool != "none" else None


class RemediationProposal(_Remediation):
    risk: Literal["low", "medium", "high"] = "medium"


class RemediationResult(_Remediation):
    executed: bool
    result_summary: str


class ReviewVerdict(Lenient):
    verdict: Literal["approve", "reject"]
    reasons: list[str]
    concerns: list[str] = Field(default_factory=list)
    evidence_request: list[EvidenceRequest] = Field(default_factory=list)


class EvidenceItem(Lenient):
    ref: str = Field(description="Evidence reference ev-N of the call")
    finding: str


class EvidenceArtifact(Lenient):
    items: list[EvidenceItem]
    summary: str
    suspected_causes: list[str] = Field(default_factory=list)


class CoordinatorFinish(Lenient):
    outcome: Literal["remediated", "no_action", "escalated"]
    root_cause_category: Category
    affected_service: str
    summary: str


ARTIFACT_MODELS: dict[str, type[Lenient]] = {
    "evidence": EvidenceArtifact,
    "diagnosis": Diagnosis,
    "remediation_proposal": RemediationProposal,
    "remediation_result": RemediationResult,
    "review": ReviewVerdict,
}
