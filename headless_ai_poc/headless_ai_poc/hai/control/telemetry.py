"""Observability: spans for every unit of work, linked by trace id (= correlation id) and parent span.

Span kinds follow the chain the article draws: request/event -> run -> reasoning -> retrieval -> tool call ->
approval -> action -> result.  Written as JSON lines; in production these would be OpenTelemetry spans.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from hai.config import Clock, short_id


class Telemetry:
    def __init__(self, path: Path, clock: Clock):
        self.path, self.clock = path, clock
        self.stack: list[str] = []
        self.spans: list[dict[str, Any]] = []
        self.counters: dict[str, int] = {}

    @contextmanager
    def span(self, kind: str, trace_id: str, name: str, **attrs: Any) -> Iterator[dict[str, Any]]:
        sid = short_id("sp", trace_id, kind, name, len(self.spans))
        s = {"trace_id": trace_id, "span_id": sid, "parent": self.stack[-1] if self.stack else None, "kind": kind, "name": name,
             "start": self.clock.now(), "attrs": attrs, "status": "ok"}
        self.stack.append(sid)
        try:
            yield s
        except Exception as e:
            s["status"] = f"error: {type(e).__name__}"
            raise
        finally:
            self.stack.pop()
            s["end"] = self.clock.now()
            self.spans.append(s)
            with self.path.open("a") as f:
                f.write(json.dumps(s, sort_keys=True, default=str) + "\n")

    def count(self, key: str, n: int = 1) -> None:
        self.counters[key] = self.counters.get(key, 0) + n
