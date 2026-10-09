"""The memory write path. Remembering is a write operation, so it is a trust boundary.

The governed writer classifies each event by its source (policy/write_rules.yaml) and attaches provenance, scope,
expiry and a source class, or refuses to remember it. The naive writer remembers everything as plain text.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from governed_memory.models.authority import POLICY_DIR
from governed_memory.models.record import MemoryRecord


@dataclass(frozen=True)
class WriteDecision:
    event_id: str
    persisted: bool
    record: MemoryRecord | None
    reason: str


class WritePolicy:
    def __init__(self, raw: dict[str, Any]):
        self.rules = raw["rules"]

    @classmethod
    def load(cls, path: Path | None = None) -> WritePolicy:
        return cls(yaml.safe_load((path or POLICY_DIR / "write_rules.yaml").read_text()))

    def apply(self, event: dict[str, Any], clock: datetime) -> WriteDecision:
        rule = self.rules.get(event["kind"])
        if rule is None:
            return WriteDecision(event["id"], False, None, "no_rule")
        actor, refs = event.get("actor") or {}, list(event.get("evidence_refs") or [])
        cond = rule.get("persist_if")
        if cond == "registered_tool" and not actor.get("registered"):
            return WriteDecision(event["id"], False, None, "unregistered_tool")
        if cond == "has_evidence_refs" and not refs:
            return WriteDecision(event["id"], False, None, "no_evidence")
        if cond == "verified_with_evidence" and not (actor.get("verified") and refs):
            return WriteDecision(event["id"], False, None, "unverified_outcome")

        s = event["scope"]
        scope = {"tenant": s["tenant"], "environment": s["environment"], "entities": s["entities"]}
        if rule["scope"] == "user_session":
            scope |= {"environment": "all", "user": actor.get("user"), "session": actor.get("session")}
        ttl = timedelta(hours=rule["ttl_hours"]) if "ttl_hours" in rule else timedelta(days=rule["ttl_days"])
        record = MemoryRecord.from_dict({
            "id": f"mem-{event['id']}", "memory_type": rule["memory_type"], "content": event["content"],
            "source": {"type": event["kind"], "id": event["id"]},
            "provenance": {"created_by": "memory-writer", "evidence_refs": refs or [event["id"]]},
            "scope": scope, "created_at": clock, "expires_at": clock + ttl,
            "trust": {"source_class": rule["source_class"]}, "claim_type": rule["claim_type"],
        })
        return WriteDecision(event["id"], True, record, f"persisted:{rule['source_class']}")


def naive_write(event: dict[str, Any], clock: datetime) -> MemoryRecord:
    """The naive writer: remember the text. Scope and trust default to 'visible everywhere, trusted'."""
    s = event["scope"]
    return MemoryRecord.from_dict({
        "id": f"naive-{event['id']}", "memory_type": "episode", "content": event["content"],
        "source": {"type": "memory", "id": event["id"]}, "provenance": {"created_by": "memory-writer", "evidence_refs": [event["id"]]},
        "scope": {"tenant": s["tenant"], "environment": s["environment"], "entities": s["entities"]},
        "created_at": clock, "expires_at": None, "trust": {"source_class": "platform-verified"}, "claim_type": "incident_history",
    })
