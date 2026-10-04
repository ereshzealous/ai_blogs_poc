"""Knowledge retrieval: authoritative runbooks, chunked by section and embedded with the model gateway.

Knowledge is owned by document owners and cited, never rewritten by an agent.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from agent_platform.models.types import EmbeddingPort
from agent_platform.telemetry.tracing import span


@dataclass(frozen=True)
class Passage:
    doc_id: str
    title: str
    section: str
    text: str
    score: float = 0.0

    @property
    def citation(self) -> str:
        return f"{self.doc_id} §{self.section}"


def _chunks(path: Path) -> list[Passage]:
    raw = path.read_text(encoding="utf-8")
    title = raw.splitlines()[0].lstrip("# ").strip()
    doc_id = title.split(" · ")[0]
    out = []
    for block in re.split(r"^## ", raw, flags=re.M)[1:]:
        head, _, body = block.partition("\n")
        out.append(Passage(doc_id, title, head.strip(), " ".join(body.split())))
    return out


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class KnowledgeBase:
    def __init__(self, directory: Path, index_path: Path, embedder: EmbeddingPort):
        self.directory = directory
        self.index_path = index_path
        self.embedder = embedder
        self.passages: list[Passage] = []
        self.vectors: list[list[float]] = []

    async def ensure_index(self) -> None:
        if self.passages:
            return
        passages = [p for f in sorted(self.directory.glob("*.md")) for p in _chunks(f)]
        cache: dict[str, list[float]] = {}
        if self.index_path.exists():
            cache = json.loads(self.index_path.read_text())
        keys = [hashlib.sha256(f"{p.title}|{p.section}|{p.text}".encode()).hexdigest()[:16] for p in passages]
        missing = [i for i, k in enumerate(keys) if k not in cache]
        if missing:
            vectors = await self.embedder.embed([f"search_document: {passages[i].title}. {passages[i].section}. {passages[i].text}"
                                                 for i in missing])
            for i, v in zip(missing, vectors):
                cache[keys[i]] = v
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            self.index_path.write_text(json.dumps(cache))
        self.passages = passages
        self.vectors = [cache[k] for k in keys]

    async def retrieve(self, query: str, k: int = 3) -> list[Passage]:
        with span("knowledge.retrieve", **{"lap.knowledge.query": query[:200], "lap.knowledge.k": k}) as s:
            await self.ensure_index()
            [qv] = await self.embedder.embed([f"search_query: {query}"])
            scored = sorted(((_cos(qv, v), p) for v, p in zip(self.vectors, self.passages)), key=lambda t: -t[0])[:k]
            out = [Passage(p.doc_id, p.title, p.section, p.text, round(score, 3)) for score, p in scored]
            s.set_attribute("lap.knowledge.citations", [p.citation for p in out])
            return out
