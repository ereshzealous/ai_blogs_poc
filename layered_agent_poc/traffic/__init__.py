"""Record and replay model traffic, so the POC can run without Ollama.

    LAP_MODEL_TRAFFIC=record:<dir>   every model response is appended to <dir>
    LAP_MODEL_TRAFFIC=replay:<dir>   model responses come from <dir>; no model server is needed

Chat responses replay in the order they were recorded, one sequence per caller (an agent name, or "monolith"). The rest
of a run is deterministic (the mock enterprise systems, policy, workflow), so the same responses in the same order
reproduce the same run: real MCP calls, real SQLite state, real crashes and retries. Embeddings replay by a digest of
their inputs. Each recorded request carries a digest with volatile ids and timestamps removed; a replay that sees a
different request still answers, and counts a mismatch.

Several processes may record into, or replay from, the same directory (the crash experiment uses three). Cursors are
per process, which fits because no agent's calls span two processes in the POC's scenarios.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ENV = "LAP_MODEL_TRAFFIC"
_VOLATILE = [
    (re.compile(r"\b(wf|ses|apr)-[0-9a-f]{10}\b"), r"\1-*"),
    (re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d(\.\d+)?)?(Z|[+-]\d\d:\d\d)?"), "<time>"),
    (re.compile(r"\b[0-9a-f]{16,64}\b"), "<hex>"),
]


class TrafficMissing(LookupError):
    """The recording has no response for this request."""


def normalize(text: str) -> str:
    for pattern, repl in _VOLATILE:
        text = pattern.sub(repl, text)
    return text


def digest(obj: Any, normalized: bool = True) -> str:
    text = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256((normalize(text) if normalized else text).encode()).hexdigest()[:16]


class Traffic:
    def __init__(self, mode: str, directory: str | Path):
        if mode not in ("record", "replay"):
            raise ValueError(f"{ENV} mode must be record or replay, not {mode!r}")
        self.mode, self.dir = mode, Path(directory)
        self.chat_file, self.embed_file = self.dir / "chat.jsonl", self.dir / "embed.jsonl"
        self.cursor: Counter[str] = Counter()
        self.mismatches = 0
        self.chats: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.embeds: dict[str, list[list[float]]] = {}
        self.embed_models: set[str] = set()
        if mode == "record":
            self.dir.mkdir(parents=True, exist_ok=True)
        else:
            if not self.chat_file.exists() and not self.embed_file.exists():
                raise FileNotFoundError(f"no recorded model traffic in {self.dir}")
            for line in _lines(self.chat_file):
                self.chats[line["caller"]].append(line)
            for line in _lines(self.embed_file):
                self.embeds[line["key"]] = line["vectors"]
                self.embed_models.add(line["model"])

    # ---------------------------------------------------------------- chat
    def record_chat(self, caller: str, model: str, request: Any, response: dict[str, Any], latency_ms: float) -> None:
        _append(self.chat_file, {"caller": caller, "model": model, "request": digest(request),
                                 "latency_ms": round(latency_ms, 1), "response": response})

    def replay_chat(self, caller: str, model: str, request: Any) -> tuple[dict[str, Any], float]:
        seq, i = self.chats.get(caller, []), self.cursor[caller]
        if i >= len(seq):
            raise TrafficMissing(f"{self.dir}: no recorded response #{i + 1} for {caller}")
        self.cursor[caller] += 1
        entry = seq[i]
        if entry["request"] != digest(request):
            self.mismatches += 1
            print(f"[traffic] {caller} call #{i + 1}: request differs from the recording; replaying the recorded answer",
                  file=sys.stderr)
        return entry["response"], float(entry.get("latency_ms", 0.0))

    # ---------------------------------------------------------------- embeddings
    def record_embed(self, model: str, texts: list[str], vectors: list[list[float]]) -> None:
        _append(self.embed_file, {"key": digest([model, texts], normalized=False), "model": model, "inputs": len(texts),
                                  "vectors": [[round(x, 6) for x in v] for v in vectors]})

    def replay_embed(self, model: str, texts: list[str]) -> list[list[float]]:
        key = digest([model, texts], normalized=False)
        if key not in self.embeds:
            raise TrafficMissing(f"{self.dir}: no recorded embeddings for these {len(texts)} input(s)")
        return self.embeds[key]

    def models(self) -> set[str]:
        return {e["model"] for seq in self.chats.values() for e in seq} | self.embed_models


def from_env() -> Traffic | None:
    value = os.environ.get(ENV, "").strip()
    if not value:
        return None
    mode, _, directory = value.partition(":")
    return Traffic(mode, directory)


def _append(path: Path, obj: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
