"""Shared plumbing: canonical hashing, deterministic identifiers, configuration, and the application-log writer.

Every process in a scenario (agent runtimes, the deployment API, the scripted operator) imports this module.  Nothing
here decides anything; it only names, hashes and writes.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POC = Path(__file__).resolve().parents[1]
CONFIG = POC / "config"
EXPERIMENTS = POC / "experiments"


def canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha(obj: Any) -> str:
    return hashlib.sha256((obj if isinstance(obj, str) else canon(obj)).encode()).hexdigest()


def short(obj: Any, n: int = 10) -> str:
    return sha(obj)[:n]


def load(name: str) -> dict:
    return tomllib.loads((CONFIG / name).read_text())


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def now_iso() -> str:
    """Wall-clock time, millisecond precision, UTC.  The run is real; its timestamps are too."""
    t = time.time()
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(t * 1000) % 1000:03d}Z"


def jl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def append_jsonl(path: Path, rec: dict, fsync: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, separators=(",", ":"), ensure_ascii=False, default=str) + "\n")
        fh.flush()
        if fsync:
            os.fsync(fh.fileno())


# ---- identifiers --------------------------------------------------------------------------------------------------------
# Derived from what they identify, so a replay of the same scenario produces the same identifiers and the recorded run can
# be compared with its replay line by line.  Production systems would use random or time-ordered ids; nothing below
# depends on them being derived.

def execution_id(scenario: str, incident: str) -> str:
    return "exec-" + short({"scenario": scenario, "incident": incident}, 8)


def action_id(execution: str, step: str, action_digest: str) -> str:
    return "act-" + short({"execution": execution, "step": step, "action": action_digest}, 8)


def attempt_id(action: str, n: int) -> str:
    return f"{action}.a{n}"


# ---- application logs ---------------------------------------------------------------------------------------------------

class AppLog:
    """One component's own log file: JSON lines, flushed per line (as Python's logging.FileHandler does), not fsynced.

    Each line carries the component's own local identifiers.  When an OpenTelemetry span is active, the line also carries
    trace_id and span_id (OpenTelemetry log correlation).  The L0 investigator reads these files with those two fields
    removed; the L1 investigator reads them as written.
    """

    def __init__(self, sdir: Path, component: str, service_version: str | None = None) -> None:
        self.path = sdir / "logs" / f"{component}.log"
        self.component = component
        self.version = service_version

    def __call__(self, level: str, msg: str, **fields: Any) -> None:
        from opentelemetry import trace

        rec: dict[str, Any] = {"ts": now_iso(), "level": level, "component": self.component}
        if self.version:
            rec["service.version"] = self.version
        rec["msg"] = msg
        rec.update(fields)
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            rec["trace_id"] = format(ctx.trace_id, "032x")
            rec["span_id"] = format(ctx.span_id, "016x")
        append_jsonl(self.path, rec)
