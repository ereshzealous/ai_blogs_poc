"""Hybrid tool retrieval over what MCP servers PUBLISH (name, description, parameter names).

* lexical: BM25 (k1=1.2, b=0.75) over tokenised server/tool names, description, params
* semantic: ``nomic-embed-text`` via Ollama ``/api/embed`` (``search_document:`` /
  ``search_query:`` task prefixes), cosine similarity, cached on disk by text hash
* fusion: reciprocal-rank fusion (k=60) of the two rankings

This index is shared by the search-only arm and the control-plane arm, so any retrieval
miss affects both the same way.  It never reads the governance registry.
"""

from __future__ import annotations

import json
import math
import re
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from ..mcp_host import ToolInfo
from ..util import DATA_DIR, sha256_text

EMBED_MODEL = "nomic-embed-text"
RRF_K = 60
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"a", "an", "the", "of", "to", "for", "on", "in", "by", "and", "or", "is", "it", "e", "g", "with", "that", "be", "can", "this", "from", "at", "as"}


_SUFFIXES = ("ing", "ies", "ed", "es", "s", "e")


def stem(tok: str) -> str:
    """Tiny suffix stemmer so charge/charged/charges and duplicate/duplicated meet (both arms share it)."""
    for suf in _SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            return tok[: -len(suf)] + ("y" if suf == "ies" else "")
    return tok


def tokenize(text: str) -> list[str]:
    text = text.replace("_", " ").replace("-", " ").lower()
    return [stem(t) for t in _TOKEN.findall(text) if t not in _STOP]


def document_text(t: ToolInfo) -> str:
    params = " ".join((t.input_schema.get("properties") or {}).keys())
    return f"{t.server} {t.tool}. {t.description} Parameters: {params}"


class Embedder:
    def __init__(self, host: str = "http://localhost:11434", model: str = EMBED_MODEL, cache_dir: Path = DATA_DIR / "embeddings"):
        self.host, self.model = host, model
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path = cache_dir / f"{model.replace(':', '_')}.json"
        self._cache: dict[str, list[float]] = json.loads(self._cache_path.read_text()) if self._cache_path.exists() else {}
        self.calls = 0

    def embed(self, texts: list[str]) -> np.ndarray:
        missing = [t for t in texts if sha256_text(t) not in self._cache]
        for i in range(0, len(missing), 64):
            batch = missing[i : i + 64]
            body = json.dumps({"model": self.model, "input": batch, "truncate": True}).encode()
            req = urllib.request.Request(f"{self.host}/api/embed", data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as r:
                vecs = json.loads(r.read())["embeddings"]
            self.calls += 1
            for t, v in zip(batch, vecs):
                self._cache[sha256_text(t)] = v
        if missing:
            self._cache_path.write_text(json.dumps(self._cache))
        m = np.array([self._cache[sha256_text(t)] for t in texts], dtype=np.float64)
        n = np.linalg.norm(m, axis=1, keepdims=True)
        return m / np.where(n == 0, 1, n)


@dataclass(frozen=True)
class Hit:
    qualified: str
    score: float
    bm25_rank: int | None
    dense_rank: int | None


class ToolIndex:
    def __init__(self, tools: Iterable[ToolInfo], embedder: Embedder | None):
        self.tools = sorted(tools, key=lambda t: t.qualified)
        self.names = [t.qualified for t in self.tools]
        self.docs = [tokenize(document_text(t)) for t in self.tools]
        self.df = Counter(tok for d in self.docs for tok in set(d))
        self.avgdl = sum(len(d) for d in self.docs) / max(len(self.docs), 1)
        self.tf = [Counter(d) for d in self.docs]
        self.embedder = embedder
        self.doc_vecs = embedder.embed([f"search_document: {document_text(t)}" for t in self.tools]) if embedder else None

    def bm25(self, query: str, k1: float = 1.2, b: float = 0.75) -> np.ndarray:
        q = tokenize(query)
        n = len(self.docs)
        scores = np.zeros(n)
        for tok in set(q):
            df = self.df.get(tok, 0)
            if df == 0:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for i, tf in enumerate(self.tf):
                f = tf.get(tok, 0)
                if f:
                    dl = len(self.docs[i])
                    scores[i] += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / self.avgdl))
        return scores

    def search(self, query: str, top_k: int) -> list[Hit]:
        bm = self.bm25(query)
        bm_order = [i for i in np.argsort(-bm, kind="stable") if bm[i] > 0]
        bm_rank = {i: r for r, i in enumerate(bm_order)}
        dense_rank: dict[int, int] = {}
        if self.embedder is not None and self.doc_vecs is not None:
            qv = self.embedder.embed([f"search_query: {query}"])[0]
            sims = self.doc_vecs @ qv
            dense_rank = {i: r for r, i in enumerate(np.argsort(-sims, kind="stable"))}
        fused: dict[int, float] = {}
        for i, r in bm_rank.items():
            fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + r + 1)
        for i, r in dense_rank.items():
            fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + r + 1)
        order = sorted(fused, key=lambda i: (-fused[i], self.names[i]))[:top_k]
        return [Hit(self.names[i], round(fused[i], 6), bm_rank.get(i), dense_rank.get(i)) for i in order]
