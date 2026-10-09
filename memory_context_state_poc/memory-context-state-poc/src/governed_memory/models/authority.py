"""The authority policy (policy/authority.yaml): which tier a record belongs to, and what memory may never answer.

Authority comes from the source class and the claim type, not from how the record was retrieved or how similar it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from governed_memory.models.record import MemoryRecord

POLICY_DIR = Path(__file__).resolve().parent.parent / "policy"


@dataclass(frozen=True)
class Tier:
    name: str
    rank: int          # 1 = most authoritative
    label: str         # authoritative | advisory | contextual | unverified
    authoritative_for: tuple[str, ...]


class AuthorityPolicy:
    def __init__(self, raw: dict):
        self.tiers = {n: Tier(n, t["rank"], t["label"], tuple(t.get("authoritative_for") or ())) for n, t in raw["tiers"].items()}
        self.source_classes: dict[str, str] = dict(raw["source_classes"])
        self.never_from_memory = frozenset(raw.get("never_from_memory") or ())
        self.admit_unverified = bool(raw.get("admit_unverified", False))

    @classmethod
    def load(cls, path: Path | None = None) -> AuthorityPolicy:
        return cls(yaml.safe_load((path or POLICY_DIR / "authority.yaml").read_text()))

    def tier(self, record: MemoryRecord) -> Tier:
        return self.tiers[self.source_classes.get(record.source_class, "unverified")]
