"""Telemetry: OTel-shaped spans written as JSON lines, with redaction before anything is written.

A deliberately small tracer, not the OpenTelemetry SDK: T5 already measured the SDK.  What this article needs from
telemetry is narrower, and it is the point of the design: the operational facts a recovery decision rests on
(request_sent, response_received, execution certainty, failure class, recovery action, operation id) on the spans
of one trace that survives retries, a SIGKILL and resume.

Attribute names follow the OpenTelemetry GenAI semantic conventions where they exist (gen_ai.operation.name,
gen_ai.request.model, gen_ai.tool.name, gen_ai.usage.*, error.type; status: Development).  The recovery facts this
article adds have no convention and use the `recovery.*` namespace.

Spans carry no wall-clock time: start/end are logical sequence numbers, so a rerun is byte-identical.  Durations go to
the run's volatile.json.  A resumed worker restores the trace id from the journal and *links* its first span to the
interrupted worker's last span.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from .common import append_jsonl, hex_id

# Canary-shaped values never reach a span or the journal (I11): card numbers, e-mail addresses, provider tokens.
REDACT = [(re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[card]"), (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[email]"),
          (re.compile(r"sk_(?:live|test)_\w+"), "[token]")]


def redact(v: Any) -> Any:
    if isinstance(v, str):
        for rx, sub in REDACT:
            v = rx.sub(sub, v)
        return v
    if isinstance(v, dict):
        return {k: redact(x) for k, x in v.items()}
    if isinstance(v, list):
        return [redact(x) for x in v]
    return v


class Tracer:
    def __init__(self, path: Path, trace_id: str, worker: str, volatile: dict, redaction: bool = True):
        self.path, self.trace_id, self.worker, self.volatile, self.redaction = path, trace_id, worker, volatile, redaction
        self.seq = 0
        self.stack: list[str] = []
        self.last_span: str | None = None

    def span(self, name: str, **attrs) -> "Span":
        return Span(self, name, attrs)

    def _id(self) -> str:
        self.seq += 1
        return hex_id(8, self.trace_id, self.worker, self.seq)


class Span:
    def __init__(self, tracer: Tracer, name: str, attrs: dict):
        self.t, self.name, self.attrs = tracer, name, dict(attrs)
        self.events: list[dict] = []
        self.links: list[dict] = []
        self.status = "UNSET"

    def __enter__(self) -> "Span":
        t = self.t
        self.span_id = t._id()
        self.parent = t.stack[-1] if t.stack else None
        self.start = t.seq
        self.wall = time.monotonic()
        t.stack.append(self.span_id)
        return self

    def set(self, **attrs) -> None:
        self.attrs.update(attrs)

    def event(self, name: str, **attrs) -> None:
        self.events.append({"name": name, "seq": self.t.seq, "attributes": attrs})
        self.t.seq += 1

    def link(self, trace_id: str, span_id: str, reason: str) -> None:
        self.links.append({"trace_id": trace_id, "span_id": span_id, "attributes": {"recovery.link.reason": reason}})

    def __exit__(self, et, ev, tb) -> None:
        t = self.t
        t.stack.pop()
        if et is not None and self.status == "UNSET":
            self.status = "ERROR"
            self.attrs.setdefault("error.type", et.__name__)
        row = {"trace_id": t.trace_id, "span_id": self.span_id, "parent_span_id": self.parent, "name": self.name,
               "worker": t.worker, "start_seq": self.start, "end_seq": t.seq, "status": self.status,
               "attributes": self.attrs, "events": self.events, "links": self.links}
        if t.redaction:     # values only: identifiers are never rewritten
            row["attributes"], row["events"] = redact(row["attributes"]), redact(row["events"])
        append_jsonl(t.path, row)
        t.volatile.setdefault("span_ms", []).append([t.worker, self.name, round((time.monotonic() - self.wall) * 1000, 1)])
        t.last_span = self.span_id
        t.seq += 1
