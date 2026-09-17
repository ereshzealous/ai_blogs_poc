"""What a channel may ask for.

The channel reports who it saw (`actor.channel` + `actor.channel_subject`). It never states who that is in the
enterprise, and it never states that anything was approved: the boundary resolves the principal, and approvals exist
only as platform state. `extra="forbid"` makes a smuggled field such as `approved: true` an invalid request rather
than a silently ignored one.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Operation(StrEnum):
    START = "start"  # begin a new workflow for the capability
    GET = "get"      # read a workflow's current capability state
    ACT = "act"      # take one of the workflow's available_actions


class Actor(Strict):
    channel: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,31}$")
    channel_subject: str = Field(min_length=1, max_length=200)  # Slack user id, OIDC subject, CLI token subject, ...


class ChannelContext(Strict):
    """Channel-owned references. The platform stores them to reach the channel again; they are never workflow state."""

    thread_ref: str | None = Field(default=None, max_length=300)    # Slack thread, Teams conversation, browser tab
    reply_to: str | None = Field(default=None, max_length=500)      # where the channel wants completion delivered
    idempotency_key: str | None = Field(default=None, max_length=200)  # e.g. a Slack event_id, an alert fingerprint


class CapabilityRequest(Strict):
    schema_version: str = "1.0"
    capability: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
    operation: Operation
    actor: Actor
    input: dict[str, Any] = Field(default_factory=dict)
    workflow_id: str | None = None
    action_id: str | None = None
    binding: str | None = None  # the available_action's binding the channel displayed; a stale one is a CONFLICT
    channel_context: ChannelContext = Field(default_factory=ChannelContext)

    @model_validator(mode="after")
    def _shape(self) -> CapabilityRequest:
        if self.operation is Operation.START and (self.workflow_id or self.action_id):
            raise ValueError("start creates a workflow; it takes no workflow_id or action_id")
        if self.operation in (Operation.GET, Operation.ACT) and not self.workflow_id:
            raise ValueError(f"{self.operation.value} needs a workflow_id")
        if self.operation is Operation.ACT and not self.action_id:
            raise ValueError("act needs an action_id")
        return self
