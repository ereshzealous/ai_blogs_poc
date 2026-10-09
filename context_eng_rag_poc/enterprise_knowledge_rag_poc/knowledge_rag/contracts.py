"""Typed contracts: the knowledge request (from the headless envelope), the evidence packet, and the answer.

The answer schema is also the JSON schema the model server is asked to emit (Ollama structured outputs), so every arm
returns the same shape and the scorer never parses prose.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from knowledge_rag.util import config

ACTIONS = list(config("vocabulary.yaml")["actions"])
Status = Literal["answer", "partial", "escalate", "abstain"]
Kind = Literal["cause", "procedure", "approval", "history", "fact", "gap", "conflict"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ---- the request, as the headless boundary (F3) delivers it ------------------------------------------------------------
class KnowledgeRequest(Strict):
    """What a head sends. Identity is the authenticated invoker; the question is data and never decides authorization."""
    request_id: str
    channel: Literal["chat", "web", "api", "event", "workflow", "agent"]
    invoker: str                      # authenticated principal (resolved by the identity provider)
    on_behalf_of: str | None = None
    environment: Literal["production", "staging"]
    question: str
    budget_tokens: int = Field(gt=0)
    correlation_id: str


# ---- the evidence packet -------------------------------------------------------------------------------------------------
class EvidenceItem(Strict):
    evidence_id: str                  # E1..En, what the model cites
    unit_id: str                      # doc@version#section or a structured record id
    doc_key: str
    source_system: str
    kind: Literal["document", "record"]
    role: str                         # procedure | approval | history | change_fact | ownership | change_summary | advisory | reference
    authority_tier: int | None        # procedure only: 1 runbook of record, 2 owner runbook
    status: str
    valid_from: str | None
    valid_to: str | None
    content_hash: str | None
    locator: dict                     # section heading and character span, or the record id
    ingested_at: str | None           # None: fetched live from the source or a system of record
    acl_checked_at: str               # the authoritative recheck time
    tokens: int
    qualifier: bool
    text: str


class EvidencePacket(Strict):
    packet_id: str
    request_id: str
    tenant: str
    environment: str
    service: str | None
    as_of: str
    budget_tokens: int
    used_tokens: int
    target_procedure_key: str | None
    evidence: list[EvidenceItem]
    conflicts: list[dict]
    gaps: list[str]
    excluded_counts: dict[str, int]   # by gate, authorization excluded (never shown to the model)


# ---- the answer ------------------------------------------------------------------------------------------------------------
class Citation(Lenient):
    evidence_id: str = ""
    quote: str = ""


class Claim(Lenient):
    text: str = ""
    kind: str = "fact"
    citations: list[Citation] = Field(default_factory=list)


class RecommendedAction(Lenient):
    action: str = "none"
    target: str = ""
    approval_required: bool = False
    approver: str = ""


class Answer(Lenient):
    status: str = "abstain"
    summary: str = ""
    recommended_action: RecommendedAction = Field(default_factory=RecommendedAction)
    claims: list[Claim] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["answer", "partial", "escalate", "abstain"]},
        "summary": {"type": "string"},
        "recommended_action": {
            "type": "object",
            "properties": {"action": {"type": "string", "enum": ACTIONS}, "target": {"type": "string"},
                           "approval_required": {"type": "boolean"}, "approver": {"type": "string"}},
            "required": ["action", "target", "approval_required", "approver"],
        },
        "claims": {"type": "array", "items": {
            "type": "object",
            "properties": {"text": {"type": "string"},
                           "kind": {"type": "string", "enum": ["cause", "procedure", "approval", "history", "fact", "gap", "conflict"]},
                           "citations": {"type": "array", "items": {"type": "object",
                                                                    "properties": {"evidence_id": {"type": "string"}, "quote": {"type": "string"}},
                                                                    "required": ["evidence_id", "quote"]}}},
            "required": ["text", "kind", "citations"]}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "conflicts": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "summary", "recommended_action", "claims", "gaps", "conflicts"],
}
