"""Embedding retrieval with a local model served by Ollama, cached on disk.

`nomic-embed-text` is used by default: small, local and free of API keys. Embeddings are cached by
(model digest, prefix, text) so repeated benchmark runs are exact and cheap.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

import httpx
import numpy as np

from control_plane.paths import CACHE_DIR

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


class OllamaEmbedder:
    def __init__(self, model: str = "nomic-embed-text", base_url: str = OLLAMA_URL, cache_path: str | Path | None = CACHE_DIR / "embeddings.sqlite",
                 document_prefix: str = "search_document: ", query_prefix: str = "search_query: "):
        self.model, self.base_url = model, base_url
        self.document_prefix, self.query_prefix = document_prefix, query_prefix
        # a shared Ollama may be swapping models; a slow load is not a failure
        self._client = httpx.Client(timeout=httpx.Timeout(900, connect=10))
        self.digest = self._digest()
        self._db = None
        if cache_path:
            Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(cache_path), check_same_thread=False, isolation_level=None)
            self._db.execute("CREATE TABLE IF NOT EXISTS emb (key TEXT PRIMARY KEY, vec TEXT)")

    def _digest(self) -> str:
        tags = self._client.get(f"{self.base_url}/api/tags").json().get("models", [])
        for m in tags:
            if m["name"] in (self.model, f"{self.model}:latest"):
                return m["digest"]
        raise RuntimeError(f"embedding model {self.model} is not pulled; run `ollama pull {self.model}`")

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.digest}|{text}".encode()).hexdigest()

    def embed(self, texts: Sequence[str], *, query: bool = False) -> np.ndarray:
        prefixed = [(self.query_prefix if query else self.document_prefix) + t for t in texts]
        out: list[list[float] | None] = [None] * len(prefixed)
        missing = []
        for i, t in enumerate(prefixed):
            row = self._db.execute("SELECT vec FROM emb WHERE key = ?", (self._key(t),)).fetchone() if self._db else None
            if row:
                out[i] = json.loads(row[0])
            else:
                missing.append(i)
        for start in range(0, len(missing), 64):
            batch = missing[start:start + 64]
            resp = self._client.post(f"{self.base_url}/api/embed", json={"model": self.model, "input": [prefixed[i] for i in batch]})
            resp.raise_for_status()
            for i, vec in zip(batch, resp.json()["embeddings"]):
                out[i] = vec
                if self._db:
                    self._db.execute("INSERT OR REPLACE INTO emb VALUES (?, ?)", (self._key(prefixed[i]), json.dumps(vec)))
        arr = np.asarray(out, dtype=np.float32)
        return arr / np.maximum(np.linalg.norm(arr, axis=1, keepdims=True), 1e-9)


class EmbeddingIndex:
    def __init__(self, documents: Mapping[str, str], embedder: OllamaEmbedder):
        self.embedder = embedder
        self.ids = list(documents)
        self._pos = {doc_id: i for i, doc_id in enumerate(self.ids)}
        self.matrix = embedder.embed([documents[i] for i in self.ids])

    def search(self, query: str, k: int = 10, restrict_to: Iterable[str] | None = None) -> list[tuple[str, float]]:
        q = self.embedder.embed([query], query=True)[0]
        if restrict_to is None:
            idx = np.arange(len(self.ids))
        else:
            idx = np.array([self._pos[i] for i in restrict_to if i in self._pos], dtype=int)
            if idx.size == 0:
                return []
        sims = self.matrix[idx] @ q
        order = sorted(range(len(idx)), key=lambda j: (-float(sims[j]), self.ids[idx[j]]))[:k]
        return [(self.ids[idx[j]], float(sims[j])) for j in order]
