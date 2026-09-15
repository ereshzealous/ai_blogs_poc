"""Hybrid retrieval: BM25 and embeddings fused with reciprocal rank fusion (RRF).

RRF needs no score calibration between the two retrievers: each contributes 1 / (k + rank).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from control_plane.discovery.bm25 import BM25Index
from control_plane.discovery.semantic import EmbeddingIndex


@dataclass(frozen=True)
class Scored:
    tool_id: str
    score: float
    lexical_rank: int | None
    semantic_rank: int | None


class HybridRetriever:
    def __init__(self, lexical: BM25Index, semantic: EmbeddingIndex | None, rrf_k: int = 60, depth: int = 50):
        self.lexical, self.semantic, self.rrf_k, self.depth = lexical, semantic, rrf_k, depth

    def search(self, query: str, k: int = 10, restrict_to: Iterable[str] | None = None, mode: str = "hybrid") -> list[Scored]:
        ids = list(restrict_to) if restrict_to is not None else None
        lex = self.lexical.search(query, self.depth, ids) if mode in ("hybrid", "bm25") else []
        sem = self.semantic.search(query, self.depth, ids) if mode in ("hybrid", "semantic") and self.semantic else []
        lex_rank = {doc: r for r, (doc, _) in enumerate(lex, start=1)}
        sem_rank = {doc: r for r, (doc, _) in enumerate(sem, start=1)}
        fused = []
        for doc in set(lex_rank) | set(sem_rank):
            score = sum(1 / (self.rrf_k + rank[doc]) for rank in (lex_rank, sem_rank) if doc in rank)
            fused.append(Scored(doc, score, lex_rank.get(doc), sem_rank.get(doc)))
        fused.sort(key=lambda s: (-s.score, s.tool_id))
        return fused[:k]
