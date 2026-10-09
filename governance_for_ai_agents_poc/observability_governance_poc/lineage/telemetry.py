"""OpenTelemetry for every process in a scenario: real SDK, real W3C trace-context propagation, a JSON-lines exporter.

    tracer, meter = setup(sdir, role="agent-target", seed_key=...)

* Spans are exported with a SimpleSpanProcessor the moment they end, one JSON line each, flushed.  A span that has not
  ended when a process is SIGKILLed is never exported: the run keeps exactly what a real process would lose.
* Trace and span ids come from a seeded IdGenerator, so the recorded run and its replay produce the same ids.
* Context crosses process boundaries the standard way: the tool gateway injects `traceparent` into the HTTP request, the
  deployment API extracts it; a restarted runtime continues the trace from the context saved in its checkpoint.
* Metrics use an InMemoryMetricReader dumped at clean exit.  A SIGKILLed process loses its metrics; that is recorded.

Attribute names follow the OpenTelemetry semantic conventions (see lineage/semconv.py and research/sources.md).  No
governance attribute (policy version, approver, verified effect) is put on a span: that is what L2 is for, and keeping
it off the spans is what lets the run measure what standard telemetry alone can answer.
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Sequence

from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.id_generator import IdGenerator
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from .common import sha

_READER: InMemoryMetricReader | None = None
_METRICS_PATH: Path | None = None


class SeededIds(IdGenerator):
    def __init__(self, key: str) -> None:
        self.r = random.Random(int(sha(key)[:16], 16))

    def generate_span_id(self) -> int:
        return self.r.getrandbits(64) or 1

    def generate_trace_id(self) -> int:
        return self.r.getrandbits(128) or 1


class JsonlExporter(SpanExporter):
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with open(self.path, "a", encoding="utf-8") as fh:
            for s in spans:
                ctx = s.get_span_context()
                rec = {
                    "name": s.name,
                    "trace_id": format(ctx.trace_id, "032x"),
                    "span_id": format(ctx.span_id, "016x"),
                    "parent_span_id": format(s.parent.span_id, "016x") if s.parent else None,
                    "parent_is_remote": bool(s.parent.is_remote) if s.parent else None,
                    "kind": s.kind.name,
                    "start_ns": s.start_time,
                    "end_ns": s.end_time,
                    "status": s.status.status_code.name,
                    "attributes": dict(s.attributes or {}),
                    "events": [{"name": e.name, "attributes": dict(e.attributes or {})} for e in s.events],
                    "links": [{"trace_id": format(l.context.trace_id, "032x"), "span_id": format(l.context.span_id, "016x"),
                               "attributes": dict(l.attributes or {})} for l in s.links],
                    "resource": {k: v for k, v in s.resource.attributes.items() if k.startswith("service.")},
                    "pid": os.getpid(),
                }
                fh.write(json.dumps(rec, separators=(",", ":"), default=str) + "\n")
            fh.flush()
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


def setup(sdir: Path, role: str, service: str, version: str, seed_key: str):
    global _READER, _METRICS_PATH
    resource = Resource.create({"service.name": service, "service.version": version, "service.instance.id": f"{role}-{os.getpid()}"})
    tp = TracerProvider(resource=resource, id_generator=SeededIds(seed_key))
    tp.add_span_processor(SimpleSpanProcessor(JsonlExporter(sdir / "telemetry" / f"spans-{role}.jsonl")))
    trace.set_tracer_provider(tp)
    _READER = InMemoryMetricReader()
    mp = MeterProvider(metric_readers=[_READER], resource=resource)
    _METRICS_PATH = sdir / "telemetry" / f"metrics-{role}-{os.getpid()}.json"
    return trace.get_tracer("lineage", version), mp.get_meter("lineage", version)


def dump_metrics() -> None:
    """Called on clean exit only.  A SIGKILLed process never gets here."""
    if _READER is None or _METRICS_PATH is None:
        return
    data = _READER.get_metrics_data()
    out = []
    for rm in data.resource_metrics if data else []:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                pts = []
                for p in m.data.data_points:
                    v = getattr(p, "value", None)
                    if v is None:
                        v = {"count": p.count, "sum": p.sum, "min": p.min, "max": p.max}
                    pts.append({"attributes": dict(p.attributes), "value": v})
                out.append({"name": m.name, "unit": m.unit, "description": m.description, "points": pts})
    _METRICS_PATH.write_text(json.dumps(out, indent=1, default=str))
    trace.get_tracer_provider().shutdown()


def inject_headers(headers: dict) -> dict:
    inject(headers)
    return headers


def extract_context(headers: dict):
    return extract({k.lower(): v for k, v in headers.items()})


def remote_parent(trace_id_hex: str, span_id_hex: str):
    """A context whose parent is a span from an earlier (possibly killed) process: continue its trace."""
    sc = SpanContext(trace_id=int(trace_id_hex, 16), span_id=int(span_id_hex, 16), is_remote=True, trace_flags=TraceFlags(TraceFlags.SAMPLED))
    return trace.set_span_in_context(NonRecordingSpan(sc))


def current_ids() -> tuple[str | None, str | None]:
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None, None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")
