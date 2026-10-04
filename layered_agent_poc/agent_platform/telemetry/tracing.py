"""OpenTelemetry tracing for the platform.

Spans follow the OpenTelemetry GenAI semantic conventions where they exist (status: Development, they may change):
`invoke_workflow`, `invoke_agent`, `chat`, `embeddings`, `execute_tool`. Platform spans (`workflow.step`, `policy.evaluate`,
`checkpoint.save`, ...) carry `lap.*` attributes.

Every finished span is appended to `runs/traces/<trace_id>.jsonl`, so a trace survives a process crash. A resumed
workflow continues the same trace: the orchestrator stores the trace id and parents new spans on it.
Set OTEL_EXPORTER_OTLP_ENDPOINT to also export over OTLP/HTTP (e.g. to Jaeger, see docker-compose.yml).
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
from opentelemetry.trace import NonRecordingSpan, SpanContext, SpanKind, Status, StatusCode, TraceFlags

_lock = threading.Lock()
_configured: dict[str, Any] = {}


class JsonlSpanExporter(SpanExporter):
    """Writes each finished span as one JSON line, one file per trace."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with _lock:
            for s in spans:
                ctx = s.get_span_context()
                rec = {
                    "trace_id": format(ctx.trace_id, "032x"),
                    "span_id": format(ctx.span_id, "016x"),
                    "parent_id": format(s.parent.span_id, "016x") if s.parent else None,
                    "name": s.name,
                    "kind": s.kind.name,
                    "start_ns": s.start_time,
                    "end_ns": s.end_time,
                    "status": s.status.status_code.name,
                    "attributes": dict(s.attributes or {}),
                    "events": [{"name": e.name, "attributes": dict(e.attributes or {})} for e in s.events],
                    "pid": os.getpid(),
                }
                with open(self.directory / f"{rec['trace_id']}.jsonl", "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, default=str) + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:  # nothing buffered
        pass


def setup(runs_dir: Path, service_name: str = "layered-agent-platform") -> None:
    """Configure the global tracer provider once per process; later calls only move the JSONL output directory."""
    if _configured:
        _configured["exporter"].directory = runs_dir / "traces"
        _configured["exporter"].directory.mkdir(parents=True, exist_ok=True)
        return
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    exporter = JsonlSpanExporter(runs_dir / "traces")
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    _configured["exporter"] = exporter
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        except ImportError:  # optional extra: uv sync --extra otlp
            pass
    trace.set_tracer_provider(provider)
    _configured["provider"] = provider
    _configured["dir"] = runs_dir / "traces"


def tracer() -> trace.Tracer:
    return trace.get_tracer("agent_platform")


def _clean(attrs: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in attrs.items():
        if v is None:
            continue
        if isinstance(v, (str, bool, int, float)):
            out[k] = v
        elif isinstance(v, (list, tuple)) and all(isinstance(x, (str, int, float, bool)) for x in v):
            out[k] = list(v)
        else:
            out[k] = json.dumps(v, default=str)[:2000]
    return out


@contextmanager
def span(name: str, kind: SpanKind = SpanKind.INTERNAL, **attributes: Any) -> Iterator[trace.Span]:
    with tracer().start_as_current_span(name, kind=kind, attributes=_clean(attributes), record_exception=True) as s:
        try:
            yield s
        except BaseException as exc:
            s.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            raise


def set_attrs(s: trace.Span, **attributes: Any) -> None:
    s.set_attributes(_clean(attributes))


def current_ids() -> tuple[str, str]:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


@contextmanager
def continue_trace(trace_id: str | None, parent_span_id: str | None) -> Iterator[None]:
    """Parent new spans on a trace started by another (possibly crashed) process."""
    if not trace_id or not parent_span_id:
        yield
        return
    sc = SpanContext(int(trace_id, 16), int(parent_span_id, 16), is_remote=True, trace_flags=TraceFlags(TraceFlags.SAMPLED))
    token = otel_context.attach(trace.set_span_in_context(NonRecordingSpan(sc)))
    try:
        yield
    finally:
        otel_context.detach(token)


def read_trace(runs_dir: Path, trace_id: str) -> list[dict[str, Any]]:
    path = runs_dir / "traces" / f"{trace_id}.jsonl"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
