"""Okapi BM25 over tool documents. Pure Python, transparent, deterministic.

At a few thousand short documents an in-process index answers in well under a millisecond, so a
search engine or SQLite FTS would add operational surface without changing results.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping

from control_plane.discovery.text import tokenize


class BM25Index:
    def __init__(self, documents: Mapping[str, str], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self._tf: dict[str, Counter[str]] = {doc_id: Counter(tokenize(text)) for doc_id, text in documents.items()}
        self._len = {doc_id: sum(tf.values()) for doc_id, tf in self._tf.items()}
        self._avg = sum(self._len.values()) / max(1, len(self._len))
        df: Counter[str] = Counter()
        for tf in self._tf.values():
            df.update(tf.keys())
        n = len(self._tf)
        self._idf = {term: math.log(1 + (n - d + 0.5) / (d + 0.5)) for term, d in df.items()}

    def score(self, query_terms: list[str], doc_id: str) -> float:
        tf, length = self._tf[doc_id], self._len[doc_id]
        s = 0.0
        for term in query_terms:
            f = tf.get(term)
            if f:
                s += self._idf[term] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * length / self._avg))
        return s

    def search(self, query: str, k: int = 10, restrict_to: Iterable[str] | None = None) -> list[tuple[str, float]]:
        terms = tokenize(query)
        ids = self._tf.keys() if restrict_to is None else [i for i in restrict_to if i in self._tf]
        scored = [(doc_id, self.score(terms, doc_id)) for doc_id in ids]
        scored = [x for x in scored if x[1] > 0]
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:k]
