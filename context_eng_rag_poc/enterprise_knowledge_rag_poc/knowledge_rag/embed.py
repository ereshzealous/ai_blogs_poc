"""Real embeddings (nomic-embed-text over Ollama), recorded to a tape so every later run replays them without a model.

The tape is index/embeddings.jsonl: one line per distinct (model, prefixed text), keyed by sha256 of both. Modes:

- record: embed what the tape lacks through Ollama (/api/embed), append it, return vectors;
- replay: read the tape only; a missing text is an error, never a silent fallback to a fake vector.

    uv run python -m knowledge_rag.embed record      # embed every index unit (and nothing else)
"""

from __future__ import annotations

import json
import math
import os
import sys
import urllib.request

from knowledge_rag.util import INDEX, config, sha256

CFG = config("retrieval.yaml")["embedding"]
TAPE = INDEX / "embeddings.jsonl"
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")


class EmbeddingMissing(KeyError):
    """Replay asked for a text the tape does not hold."""


def _key(text: str) -> str:
    return sha256(f"{CFG['model']}\x00{text}")


class Embedder:
    """Reads vectors from `tapes`; in record mode, embeds what they lack through Ollama and appends it to `record_to`.
    The index build records document vectors to index/embeddings.jsonl; a run records its query vectors to its own tape
    (runs/<id>/tape/query_embeddings.jsonl), so the frozen index tape never changes after the freeze."""

    def __init__(self, mode: str = "replay", tapes: list | None = None, record_to=None) -> None:
        if mode not in ("record", "replay"):
            raise ValueError(mode)
        self.mode = mode
        self.record_to = record_to or TAPE
        self.tape: dict[str, list[float]] = {}
        for path in tapes or [TAPE]:
            if path.exists():
                for line in path.read_text().splitlines():
                    if line.strip():
                        r = json.loads(line)
                        self.tape[r["key"]] = r["vector"]
        self.used: list[str] = []

    def _remote(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps({"model": CFG["model"], "input": texts}).encode()
        req = urllib.request.Request(f"{OLLAMA}/api/embed", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())["embeddings"]

    def embed(self, texts: list[str]) -> list[list[float]]:
        keys = [_key(t) for t in texts]
        missing = [(k, t) for k, t in zip(keys, texts) if k not in self.tape]
        if missing and self.mode == "replay":
            raise EmbeddingMissing(f"{len(missing)} text(s) not on the embedding tape, e.g. {missing[0][1][:80]!r}")
        if missing:
            uniq = dict(missing)
            items = list(uniq.items())
            self.record_to.parent.mkdir(parents=True, exist_ok=True)
            with self.record_to.open("a") as fh:
                for i in range(0, len(items), 32):
                    batch = items[i:i + 32]
                    vecs = self._remote([t for _, t in batch])
                    for (k, t), v in zip(batch, vecs):
                        self.tape[k] = v
                        fh.write(json.dumps({"key": k, "model": CFG["model"], "digest": CFG["digest"], "chars": len(t),
                                             "text_sha256": sha256(t), "vector": v}) + "\n")
        self.used += keys
        return [self.tape[k] for k in keys]

    def document(self, texts: list[str]) -> list[list[float]]:
        return self.embed([CFG["document_prefix"] + t for t in texts])

    def query(self, text: str) -> list[float]:
        return self.embed([CFG["query_prefix"] + text])[0]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


if __name__ == "__main__":
    from knowledge_rag.ingest import load_units
    mode = (sys.argv[1:] or ["replay"])[0]
    e = Embedder(mode)
    units = load_units()
    e.document([u["index_text"] for u in units])
    print(f"{len(units)} units embedded ({mode}); tape holds {len(e.tape)} vectors")
