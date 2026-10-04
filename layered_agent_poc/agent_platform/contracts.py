"""Commands the experience layer sends to the platform. Channels translate their own formats into these."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StartInvestigation(BaseModel):
    incident_id: str = Field(pattern=r"^INC-\d+$")
    request: str = Field(min_length=3, max_length=2000)
    user_id: str
    channel: str
    session_id: str | None = None


class ApprovalDecision(BaseModel):
    workflow_id: str
    approver_id: str
    approve: bool
    comment: str = ""
