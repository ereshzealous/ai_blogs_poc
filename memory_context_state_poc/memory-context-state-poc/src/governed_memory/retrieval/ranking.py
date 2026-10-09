"""Gate 4: rank surviving candidates by authority tier, then freshness, then similarity, then id (the fixed tie-break)."""

from __future__ import annotations

from governed_memory.models.authority import AuthorityPolicy
from governed_memory.retrieval.semantic import Candidate


def rank(candidates: list[Candidate], policy: AuthorityPolicy) -> list[Candidate]:
    return sorted(candidates, key=lambda c: (policy.tier(c.record).rank, -c.record.created_at.timestamp(),
                                             -c.similarity, c.record.id))
