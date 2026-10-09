"""Evidence plane: OpenTelemetry spans and a hash-chained governance record, correlated by one trace id.

Two records, on purpose (T5):
  trace.jsonl       operational telemetry: OpenTelemetry SDK spans (gen_ai.* attributes on model calls), exported as
                    they end.  A SIGKILLed process loses its open spans; that is what telemetry does.
  audit.jsonl       governance evidence: every consequential fact (identity, delegation, context, routing, proposal,
                    policy decision, approval, capability, execution, verification, memory write, budget, control-plane
                    change), appended with seq, prev_hash and hash.  Written before the step it describes completes.
Category files (policy/approvals/capability/events/model_io/context) hold the full payloads the audit events summarise.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from agentic_platform.canonical import canonical_json, sha256

CATEGORIES = ("policy", "approvals", "capability", "events", "model_io", "context")


class JsonlSpanExporter(SpanExporter):
    def __init__(self, path: Path):
        self.path = path

    def export(self, spans: list[ReadableSpan]) -> SpanExportResult:
        with self.path.open("a") as fh:
            for s in spans:
                fh.write(json.dumps({
                    "trace_id": f"{s.context.trace_id:032x}", "span_id": f"{s.context.span_id:016x}",
                    "parent_span_id": f"{s.parent.span_id:016x}" if s.parent else None, "name": s.name,
                    "start": s.start_time / 1e9, "end": s.end_time / 1e9, "duration_ms": round((s.end_time - s.start_time) / 1e6, 3),
                    "status": s.status.status_code.name, "attributes": dict(s.attributes or {}), "pid": os.getpid(),
                    "resource": dict(s.resource.attributes),
                }, default=str) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


_provider: TracerProvider | None = None


def tracer(run_dir: Path, service: str = "agent-runtime") -> trace.Tracer:
    """One provider per process; spans go to <run_dir>/trace.jsonl as they end."""
    global _provider
    if _provider is None:
        _provider = TracerProvider(resource=Resource.create({"service.name": service, "service.version": "1.0.0",
                                                             "deployment.environment": "production-simulated"}))
        _provider.add_span_processor(SimpleSpanProcessor(JsonlSpanExporter(run_dir / "trace.jsonl")))
    return _provider.get_tracer("agentic_platform")


def reset_tracer() -> None:
    global _provider
    if _provider:
        _provider.shutdown()
    _provider = None


def traceparent(span: trace.Span | None = None) -> str:
    ctx = (span or trace.get_current_span()).get_span_context()
    return f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-01"


def context_from_traceparent(tp: str):
    """Continue a trace after a restart: the new process parents its spans on the stored trace context."""
    _, tid, sid, _ = tp.split("-")
    sc = SpanContext(trace_id=int(tid, 16), span_id=int(sid, 16), is_remote=True, trace_flags=TraceFlags(1))
    return trace.set_span_in_context(NonRecordingSpan(sc))


class Evidence:
    """Append-only, hash-chained governance record for one experiment directory (safe across process restarts)."""

    def __init__(self, run_dir: Path, experiment: str):
        self.dir = Path(run_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.experiment = experiment
        self.audit = self.dir / "audit.jsonl"

    def _last(self) -> tuple[int, str]:
        if not self.audit.exists():
            return 0, "0" * 64
        last = None
        with self.audit.open() as fh:
            for line in fh:
                if line.strip():
                    last = line
        if not last:
            return 0, "0" * 64
        r = json.loads(last)
        return r["seq"], r["hash"]

    def record(self, event_type: str, payload: dict[str, Any], *, workflow_id: str | None = None, category: str | None = None,
               detail: dict[str, Any] | None = None) -> dict[str, Any]:
        span = trace.get_current_span().get_span_context()
        seq, prev = self._last()
        ev = {"seq": seq + 1, "at": time.time(), "experiment": self.experiment, "event_type": event_type, "workflow_id": workflow_id,
              "trace_id": f"{span.trace_id:032x}" if span.is_valid else None, "span_id": f"{span.span_id:016x}" if span.is_valid else None,
              "pid": os.getpid(), "payload": payload, "prev_hash": prev}
        ev["hash"] = sha256(prev + canonical_json({k: v for k, v in ev.items() if k != "hash"}))
        with self.audit.open("a") as fh:
            fh.write(json.dumps(ev, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        if category:
            self.write(category, {"seq": ev["seq"], "event_type": event_type, "workflow_id": workflow_id, "trace_id": ev["trace_id"],
                                  **(detail or payload)})
        return ev

    def write(self, category: str, row: dict[str, Any]) -> None:
        assert category in CATEGORIES, category
        with (self.dir / f"{category}.jsonl").open("a") as fh:
            fh.write(json.dumps({"at": time.time(), "experiment": self.experiment, **row}, default=str) + "\n")

    def event(self, event_type: str, **payload: Any) -> None:
        span = trace.get_current_span().get_span_context()
        self.write("events", {"event_type": event_type, "pid": os.getpid(), "trace_id": f"{span.trace_id:032x}" if span.is_valid else None, **payload})


def verify_chain(path: Path) -> tuple[bool, int, int | None]:
    """Recompute every hash.  Returns (intact, events, first_broken_seq)."""
    prev, n = "0" * 64, 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        n += 1
        want = sha256(prev + canonical_json({k: v for k, v in ev.items() if k != "hash"}))
        if ev["prev_hash"] != prev or ev["hash"] != want:
            return False, n, ev["seq"]
        prev = ev["hash"]
    return True, n, None


@contextmanager
def span(t: trace.Tracer, name: str, **attrs: Any):
    with t.start_as_current_span(name) as s:
        for k, v in attrs.items():
            if v is not None:
                s.set_attribute(k, v if isinstance(v, (str, int, float, bool)) else json.dumps(v, default=str))
        yield s
