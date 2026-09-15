"""Audit log and OpenTelemetry tracing for the control plane."""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

_provider: TracerProvider | None = None


class JsonlSpanExporter(SpanExporter):
    """Writes finished spans as one JSON object per line. No collector needed."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with self._lock, open(self.path, "a", encoding="utf-8") as fh:
            for s in spans:
                fh.write(json.dumps({
                    "name": s.name,
                    "trace_id": format(s.context.trace_id, "032x"),
                    "span_id": format(s.context.span_id, "016x"),
                    "parent_id": format(s.parent.span_id, "016x") if s.parent else None,
                    "start": s.start_time,
                    "end": s.end_time,
                    "duration_ms": round((s.end_time - s.start_time) / 1e6, 3) if s.end_time else None,
                    "attributes": dict(s.attributes or {}),
                }, default=str) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:  # pragma: no cover - nothing to release
        return None


def configure_tracing(spans_path: str | Path | None) -> None:
    """Install a tracer provider once. With no path, spans are created but not exported."""
    global _provider
    if _provider is not None:
        return
    _provider = TracerProvider(resource=Resource.create({"service.name": "mcp-capability-control-plane"}))
    if spans_path:
        _provider.add_span_processor(SimpleSpanProcessor(JsonlSpanExporter(spans_path)))
    trace.set_tracer_provider(_provider)


def tracer() -> trace.Tracer:
    return trace.get_tracer("control_plane")


def _attr(value: Any) -> Any:
    if isinstance(value, (str, bool, int, float)):
        return value
    return json.dumps(value, default=str, sort_keys=True)


@contextmanager
def span(name: str, **attributes: Any):
    with tracer().start_as_current_span(name) as s:
        for k, v in attributes.items():
            if v is not None:
                s.set_attribute(k, _attr(v))
        yield s


class AuditLog:
    """Append-only record of every discovery, policy decision, approval and execution."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.entries: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def write(self, event: str, **fields: Any) -> dict[str, Any]:
        entry = {"ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "event": event, **fields}
        with self._lock:
            self.entries.append(entry)
            if self.path:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, default=str) + "\n")
        return entry
