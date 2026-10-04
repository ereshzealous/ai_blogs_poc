"""OpenTelemetry tracing with a crash-safe JSONL exporter.

Every finished span is appended (and fsynced) to <dir>/<trace_id>.jsonl, so a trace survives SIGKILL.  A workflow
stores its trace id and root span id; a resumed process parents its spans on them, so one incident is one trace even
when three processes worked on it.  Attributes use the `f2.*` namespace: f2.request_id, f2.workflow_id, f2.step,
f2.agent, f2.capability, f2.policy.effect, f2.op_id, f2.checkpoint.seq.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import NonRecordingSpan, SpanContext, Status, StatusCode, TraceFlags

_lock = threading.Lock()
_state: dict[str, Any] = {}


class JsonlSpanExporter(SpanExporter):
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with _lock:
            for s in spans:
                ctx = s.get_span_context()
                rec = {"trace_id": format(ctx.trace_id, "032x"), "span_id": format(ctx.span_id, "016x"),
                       "parent_id": format(s.parent.span_id, "016x") if s.parent else None, "name": s.name,
                       "start_ns": s.start_time, "end_ns": s.end_time, "status": s.status.status_code.name,
                       "attributes": dict(s.attributes or {}), "pid": os.getpid()}
                with open(self.directory / f"{rec['trace_id']}.jsonl", "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, default=str) + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


def setup(directory: Path) -> None:
    """Configure the process-wide tracer once; later calls only redirect the output directory."""
    if "exporter" in _state:
        _state["exporter"].directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "f2-layered-platform"}))
    exporter = JsonlSpanExporter(directory)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _state["exporter"] = exporter


def _clean(attrs: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in attrs.items():
        if v is None:
            continue
        out[k] = v if isinstance(v, (str, bool, int, float)) else json.dumps(v, default=str)[:1500]
    return out


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[trace.Span]:
    with trace.get_tracer("f2").start_as_current_span(name, attributes=_clean(attributes), record_exception=True) as s:
        try:
            yield s
        except BaseException as exc:
            s.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            raise


def annotate(**attributes: Any) -> None:
    trace.get_current_span().set_attributes(_clean(attributes))


def current_ids() -> tuple[str, str]:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


@contextmanager
def continue_trace(trace_id: str | None, span_id: str | None) -> Iterator[None]:
    if not trace_id or not span_id:
        yield
        return
    sc = SpanContext(int(trace_id, 16), int(span_id, 16), is_remote=True, trace_flags=TraceFlags(TraceFlags.SAMPLED))
    token = otel_context.attach(trace.set_span_in_context(NonRecordingSpan(sc)))
    try:
        yield
    finally:
        otel_context.detach(token)
