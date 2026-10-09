"""Contracts between the layers: requests, views, agent outputs, and the two ports the runtime depends on.

Nothing here imports an implementation.  A layer depends on these types, never on another layer's internals.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, model_validator

# ---- experience <-> platform ------------------------------------------------------------------------------------------


class StartRequest(BaseModel):
    incident_id: str
    requested_by: str
    channel: str = "cli"
    request_id: str
    instructions: str = "Investigate the incident and remediate it safely."


class ApprovalDecision(BaseModel):
    workflow_id: str
    decided_by: str
    approve: bool
    reason: str = ""


class WorkflowView(BaseModel):
    workflow_id: str
    request_id: str
    incident_id: str
    status: str
    step: str
    diagnosis: dict[str, Any] | None = None
    proposal: dict[str, Any] | None = None
    policy: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None
    action: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    report: str | None = None


# ---- agent outputs (validated; the model's answer is data, not an instruction) ---------------------------------------


class DiagnosisReport(BaseModel):
    summary: str = Field(description="One or two sentences on what is wrong")
    root_cause: str = Field(description="The cause, in operational terms")
    suspect_service: str
    suspect_release: str | None = Field(description="Release id that introduced the fault, e.g. rel-1234, or null")
    evidence: list[str] = Field(description="Observations that support the root cause, with numbers")
    confidence: Literal["low", "medium", "high"]


class RemediationProposal(BaseModel):
    action: Literal["rollback_release", "restart_service", "scale_service", "none"]
    service: str
    environment: Literal["production", "staging"]
    target_release: str | None = Field(default=None, description="For rollback_release: the release to return to")
    rationale: str

    @model_validator(mode="after")
    def _target(self) -> RemediationProposal:
        if self.action == "rollback_release" and not self.target_release:
            raise ValueError("rollback_release needs target_release")
        return self


# ---- ports used by the runtime --------------------------------------------------------------------------------------


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any]


class ModelReply(BaseModel):
    content: str
    tool_calls: list[ToolCall] = []
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ModelPort(Protocol):
    """What reasoning code may ask of Model Services: a capability, not a provider."""

    async def generate(self, route: str, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]] | None = None,
                       schema: dict[str, Any] | None = None, caller: str = "", workflow_id: str = "") -> ModelReply: ...


class ToolPort(Protocol):
    """What reasoning code may ask of Tools + Actions: read capabilities, described for a model."""

    def definitions(self) -> list[dict[str, Any]]: ...

    async def call(self, name: str, arguments: dict[str, Any]) -> str: ...


# ---- actions ---------------------------------------------------------------------------------------------------------


class ActionContext(BaseModel):
    workflow_id: str
    step: str
    principal: str
    incident_environment: str = "production"
    approval_id: str | None = None


class PolicyDecision(BaseModel):
    effect: Literal["ALLOW", "DENY", "REQUIRE_APPROVAL"]
    rule: str
    reason: str
    required_role: str | None = None
