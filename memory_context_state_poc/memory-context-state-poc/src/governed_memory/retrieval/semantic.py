"""Semantic candidate retrieval, shared by both arms: one embedding index, cosine similarity, top-N.

Similarity finds candidates. It says nothing about whether a candidate is valid; that is the gates' job.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from governed_memory.models.record import MemoryRecord


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class Candidate:
    record: MemoryRecord
    similarity: float


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def document_text(r: MemoryRecord) -> str:
    return f"search_document: {r.content}"  # nomic-embed-text task prefix, as in F2's knowledge retrieval


class SemanticIndex:
    """Embeds each distinct document once (the cache is keyed by id and content) and ranks by cosine similarity."""

    def __init__(self, embedder: Embedder):
        self.embedder = embedder
        self._vectors: dict[tuple[str, str], list[float]] = {}
        self.records: list[MemoryRecord] = []

    async def build(self, records: list[MemoryRecord]) -> None:
        self.records = sorted(records, key=lambda r: r.id)
        todo = [r for r in self.records if (r.id, r.content) not in self._vectors]
        if todo:
            vectors = await self.embedder.embed([document_text(r) for r in todo])
            for r, v in zip(todo, vectors):
                self._vectors[(r.id, r.content)] = v

    async def candidates(self, query_text: str, n: int) -> list[Candidate]:
        [qv] = await self.embedder.embed([f"search_query: {query_text}"])
        scored = [Candidate(r, round(cosine(qv, self._vectors[(r.id, r.content)]), 6)) for r in self.records]
        return sorted(scored, key=lambda c: (-c.similarity, c.record.id))[:n]
