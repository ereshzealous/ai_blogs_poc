"""Candidate retrieval over the index: vector (real embeddings, cosine), BM25, and their Reciprocal Rank Fusion.

A ranking is a candidate list, not a decision. Every method takes an optional pre-filter (a predicate over a unit's
indexed metadata) that is applied *before* ranking, the way a search engine's security-trimming filter works: a unit
the filter rejects never takes a slot in the top k.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Callable

from knowledge_rag.embed import Embedder, cosine
from knowledge_rag.util import config

CFG = config("retrieval.yaml")
TOKEN = re.compile(r"[a-z0-9]+(?:[._\-/][a-z0-9]+)*")
STOP = set("""a an and are as at be by can do does for from has have how i if in into is it its of on or our should so that the
their them then there these this to us was we what when where which who why will with you your""".split())

Filter = Callable[[dict], bool]


def analyze(text: str) -> list[str]:
    """Lowercase word tokens; a compound token (4.17.0, rb-srch-040, threeds2.eu) is kept whole AND split into its parts,
    like a search engine's word-delimiter filter with preserve_original."""
    out = []
    for m in TOKEN.finditer(text.lower()):
        t = m.group(0)
        if t not in STOP:
            out.append(t)
        parts = [p for p in re.split(r"[._\-/]", t) if p]
        if len(parts) > 1:
            out += [p for p in parts if p not in STOP]
    return out


class Retriever:
    def __init__(self, units: list[dict], embedder: Embedder) -> None:
        self.units = units
        self.by_id = {u["unit_id"]: u for u in units}
        self.embedder = embedder
        self.vectors = dict(zip((u["unit_id"] for u in units), embedder.document([u["index_text"] for u in units])))
        self.tf = {u["unit_id"]: Counter(analyze(u["index_text"])) for u in units}
        self.dl = {k: sum(v.values()) for k, v in self.tf.items()}
        self.avgdl = sum(self.dl.values()) / len(self.dl)
        df: Counter = Counter()
        for c in self.tf.values():
            df.update(c.keys())
        n = len(units)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def _pool(self, filt: Filter | None) -> list[dict]:
        return [u for u in self.units if filt is None or filt(u)]

    def vector(self, query: str, filt: Filter | None = None) -> list[tuple[str, float]]:
        q = self.embedder.query(query)
        scored = [(u["unit_id"], cosine(q, self.vectors[u["unit_id"]])) for u in self._pool(filt)]
        return sorted(scored, key=lambda x: (-x[1], x[0]))

    def bm25(self, query: str, filt: Filter | None = None) -> list[tuple[str, float]]:
        k1, b = CFG["bm25"]["k1"], CFG["bm25"]["b"]
        terms = analyze(query)
        scored = []
        for u in self._pool(filt):
            tf, dl = self.tf[u["unit_id"]], self.dl[u["unit_id"]]
            s = 0.0
            for t in terms:
                f = tf.get(t, 0)
                if f:
                    s += self.idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / self.avgdl))
            scored.append((u["unit_id"], s))
        return sorted(scored, key=lambda x: (-x[1], x[0]))

    def hybrid(self, query: str, filt: Filter | None = None) -> list[tuple[str, float]]:
        """RRF: score(d) = sum over rankings of 1 / (k + rank(d)), rank from 1, each ranking cut at `depth`. A BM25 score
        of zero is not a ranking position: units without a single matching term do not get lexical credit."""
        k, depth = CFG["fusion"]["k"], CFG["fusion"]["depth"]
        fused: dict[str, float] = {}
        vec = self.vector(query, filt)[:depth]
        lex = [x for x in self.bm25(query, filt) if x[1] > 0][:depth]
        for ranking in (vec, lex):
            for r, (uid, _) in enumerate(ranking, start=1):
                fused[uid] = fused.get(uid, 0.0) + 1.0 / (k + r)
        return sorted(fused.items(), key=lambda x: (-x[1], x[0]))

    def search(self, method: str, query: str, k: int, filt: Filter | None = None) -> list[tuple[str, float]]:
        fn = {"vector": self.vector, "bm25": self.bm25, "hybrid": self.hybrid}[method]
        out = fn(query, filt)
        if method == "bm25":
            out = [x for x in out if x[1] > 0]
        return out[:k]
