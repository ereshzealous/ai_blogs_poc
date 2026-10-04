"""Structured outputs of the agents. Orchestration consumes these; it never parses free text."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class Evidence(BaseModel):
    tool: str = Field(description="Tool that produced the finding, e.g. database.get_connection_pool_stats")
    finding: str = Field(description="One-sentence finding with the key number")


class DiagnosisReport(BaseModel):
    summary: str = Field(description="Two-sentence summary of what happened")
    root_cause: str = Field(description="The mechanism that causes the symptom")
    suspect_service: str
    suspect_version: str = Field(description="Version that introduced the problem, e.g. v4.17")
    suspect_deployment_id: str = Field(description="Deployment id, e.g. DEP-88213")
    previous_version: str = Field(description="Version that ran before the suspect deployment, e.g. v4.16")
    evidence: list[Evidence] = Field(min_length=3, max_length=8, description="3 to 8 findings, each with a number")
    ruled_out: list[str] = Field(min_length=1, description="Plausible causes that the evidence rules out, each with the reason")
    confidence: Literal["low", "medium", "high"]


class RemediationProposal(BaseModel):
    tool_id: Literal["source_control.rollback_release", "kubernetes.rollback_deployment"]
    service: str
    environment: Literal["production", "staging"]
    target_version: str | None = Field(default=None, description="For rollback_release: the release to return to, e.g. v4.16")
    revision: int | None = Field(default=None, description="For rollback_deployment: the ReplicaSet revision")
    rationale: str
    citations: list[str] = Field(description="Runbook citations such as 'RB-CHK-007 §Rolling back checkout-api'")

    @model_validator(mode="after")
    def _arguments_complete(self) -> RemediationProposal:
        if self.tool_id == "source_control.rollback_release" and not (self.target_version or "").startswith("v"):
            raise ValueError("rollback_release needs target_version, the previous release, e.g. 'v4.16'")
        if self.tool_id == "kubernetes.rollback_deployment" and not self.revision:
            raise ValueError("rollback_deployment needs a revision number")
        return self

    def arguments(self) -> dict[str, Any]:
        if self.tool_id == "source_control.rollback_release":
            return {"service": self.service, "environment": self.environment, "target_version": self.target_version or "",
                    "reason": self.rationale[:200]}
        return {"service": self.service, "environment": self.environment, "revision": self.revision or 0}


class IncidentNote(BaseModel):
    status: Literal["mitigated", "resolved"]
    note: str = Field(description="Work note: cause, action taken, verification result. Under 600 characters.")


@dataclass
class AgentTask:
    """Everything an agent may know about the step, handed over by orchestration."""

    workflow_id: str
    step: str
    incident_id: str
    service: str
    environment: str
    request: str
    user_id: str
    session_id: str | None
    step_view: dict[str, Any] = field(default_factory=dict)
    feedback: list[str] = field(default_factory=list)


@dataclass
class AgentOutcome:
    output: Any
    steps: int
    tool_calls: list[dict[str, Any]]
    context_manifest: dict[str, Any]
    repaired: bool = False
