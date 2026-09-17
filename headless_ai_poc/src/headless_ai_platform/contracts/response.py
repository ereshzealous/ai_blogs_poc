"""What the platform answers, whatever channel asked.

`workflow_id` and `state` are platform-owned. `available_actions` lists what can happen next, with the role each
needs and whether this actor holds it, so a channel can show or grey out a button; the platform still checks the role
when the action arrives.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Status(StrEnum):
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


TERMINAL = frozenset({Status.COMPLETED, Status.REJECTED})


class ActionType(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    RETRY = "RETRY"


class AvailableAction(Frozen):
    action_id: str
    type: ActionType
    label: str
    required_role: str | None = None
    allowed_for_actor: bool
    binding: str | None = None  # digest of the exact invocation an approval applies to


class RecommendedAction(Frozen):
    tool: str
    target: str | None = None
    environment: str | None = None
    description: str


class ResolvedActor(Frozen):
    principal_id: str
    channel: str


class CapabilityState(Frozen):
    incident_id: str
    service: str | None = None
    environment: str | None = None
    summary: str | None = None          # the diagnosis, in one sentence
    suspect: str | None = None          # e.g. "checkout-api v4.17 (dep-...)"
    confidence: str | None = None      # low / medium / high
    recommended_action: RecommendedAction | None = None
    policy_decision: str | None = None  # ALLOW / REQUIRE_APPROVAL / DENY, decided by the platform
    policy_rule: str | None = None
    approval_status: str | None = None
    approval_required_role: str | None = None
    approved_by: str | None = None
    remediation_status: str | None = None
    verified: bool | None = None
    p95_ms: float | None = None
    slo_p95_ms: float | None = None
    incident_note: str | None = None
    current_step: str | None = None


class CapabilityResponse(Frozen):
    schema_version: str = "1.0"
    capability: str
    capability_version: str
    workflow_id: str
    status: Status
    state: CapabilityState
    available_actions: list[AvailableAction] = []
    actor: ResolvedActor               # who this response was produced for
    started_by: ResolvedActor          # who started the workflow, and from which channel
    trace_id: str | None = None
    updated_at: str | None = None

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL

    def action(self, type_: ActionType) -> AvailableAction | None:
        return next((a for a in self.available_actions if a.type is type_), None)
