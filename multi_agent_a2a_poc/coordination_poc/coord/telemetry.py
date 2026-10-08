"""OpenTelemetry tracing with a crash-safe JSONL exporter, one file per process (adapted from F2's tracing.py).

Each finished span is appended and fsynced to <home>/traces/<trace_id>.<pid>.jsonl, so a trace survives SIGKILL and
processes never interleave writes.  Across the A2A boundary the W3C `traceparent` header carries the context: the host
injects it into the delegation's HTTP headers and the agent server extracts it, so one incident is one trace across
four processes.  Attributes: `c1.*` (workflow, arch, component, delegation, a2a task) and OTel GenAI `gen_ai.*`.
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
from opentelemetry.trace import Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_lock = threading.Lock()
_state: dict[str, Any] = {}
_prop = TraceContextTextMapPropagator()


class JsonlSpanExporter(SpanExporter):
    def __init__(self, directory: Path, service: str):
        self.directory, self.service = directory, service
        directory.mkdir(parents=True, exist_ok=True)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with _lock:
            for s in spans:
                ctx = s.get_span_context()
                rec = {"trace_id": format(ctx.trace_id, "032x"), "span_id": format(ctx.span_id, "016x"),
                       "parent_id": format(s.parent.span_id, "016x") if s.parent else None, "name": s.name,
                       "start_ns": s.start_time, "end_ns": s.end_time, "status": s.status.status_code.name,
                       "service": self.service, "attributes": dict(s.attributes or {}), "pid": os.getpid()}
                with open(self.directory / f"{rec['trace_id']}.{os.getpid()}.jsonl", "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, default=str) + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


def setup(directory: Path, service: str) -> None:
    if "exporter" in _state:
        _state["exporter"].directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        return
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    exporter = JsonlSpanExporter(directory, service)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _state["exporter"] = exporter


def _clean(attrs: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in attrs.items():
        if v is None:
            continue
        out[k] = v if isinstance(v, (str, bool, int, float)) else json.dumps(v, default=str)[:2000]
    return out


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[trace.Span]:
    with trace.get_tracer("c1").start_as_current_span(name, attributes=_clean(attributes), record_exception=True) as s:
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


def inject_headers() -> dict[str, str]:
    carrier: dict[str, str] = {}
    _prop.inject(carrier)
    return carrier


@contextmanager
def extracted(headers: dict[str, str]) -> Iterator[None]:
    """Make a remote parent (from an incoming `traceparent` header) the current context."""
    ctx = _prop.extract({k.lower(): v for k, v in headers.items()})
    token = otel_context.attach(ctx)
    try:
        yield
    finally:
        otel_context.detach(token)
