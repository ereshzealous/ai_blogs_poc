"""Gate 5: conflicts. Relations are frozen data on the record (`contradicts`), never inferred by a model.

A record is contradicted when it names a record of a more authoritative tier. It is not deleted and not averaged with
the evidence it contradicts; it is marked and moved behind all uncontradicted evidence.
"""

from __future__ import annotations

from governed_memory.models.authority import AuthorityPolicy
from governed_memory.models.record import MemoryRecord


def contradicted_by(r: MemoryRecord, corpus: dict[str, MemoryRecord], policy: AuthorityPolicy) -> str | None:
    mine = policy.tier(r).rank
    for other_id in r.contradicts:
        other = corpus.get(other_id)
        if other is not None and policy.tier(other).rank < mine:
            return other_id
    return None
