"""The governed memory record: content plus the metadata governance needs (source, provenance, scope, lifecycle,
trust class, claim type, and frozen relations to other records). A record is evidence, not truth."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def parse_time(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class Scope:
    tenant: str
    environment: str                 # production | staging | all
    entities: tuple[str, ...]        # service names, or "*" for estate-wide
    user: str | None = None          # set for user- or session-scoped memory
    session: str | None = None


@dataclass(frozen=True)
class Provenance:
    created_by: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    memory_type: str                 # episode | knowledge | user_assertion
    content: str
    source: dict[str, Any]
    provenance: Provenance | None
    scope: Scope
    created_at: datetime
    expires_at: datetime | None
    source_class: str                # trust.source_class, mapped to an authority tier by policy
    claim_type: str
    contradicts: tuple[str, ...] = ()
    superseded_by: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MemoryRecord:
        p = d.get("provenance")
        s = d["scope"]
        return cls(
            id=d["id"], memory_type=d["memory_type"], content=" ".join(str(d["content"]).split()),
            source=dict(d.get("source") or {}),
            provenance=Provenance(p.get("created_by") or "", tuple(p.get("evidence_refs") or ())) if p else None,
            scope=Scope(s["tenant"], s["environment"], tuple(s.get("entities") or ()), s.get("user"), s.get("session")),
            created_at=parse_time(d["created_at"]), expires_at=parse_time(d.get("expires_at")),
            source_class=(d.get("trust") or {}).get("source_class", "unverified-external"),
            claim_type=d["claim_type"], contradicts=tuple(d.get("contradicts") or ()),
            superseded_by=d.get("superseded_by"),
        )

    def source_label(self) -> str:
        return f"{self.source.get('type', 'unknown')} {self.source.get('id', '')}".strip()


@dataclass(frozen=True)
class Query:
    text: str
    tenant: str
    environment: str
    entities: tuple[str, ...]
    user: str
    session: str
    clock: datetime
    meta: dict[str, Any] = field(default_factory=dict, compare=False)
