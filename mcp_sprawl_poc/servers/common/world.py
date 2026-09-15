"""Shared, deterministic world state for the mock enterprise backends.

Each MCP server is its own process, but they simulate one company: a rollback executed through
source-control-mcp must change what observability-mcp reports. Backends therefore share a small
SQLite event store. Every benchmark case and agent run uses its own `run_id` (sent as MCP
`_meta.run_id`), so runs never see each other's side effects and no server needs restarting.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from servers.common.scenario import Scenario, load_scenario

_DEFAULT_DB = Path(os.environ.get("MOCK_WORLD_DB", Path(__file__).resolve().parents[2] / "benchmark" / ".cache" / "world.sqlite"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    at TEXT NOT NULL,
    server TEXT NOT NULL,
    tool TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
"""


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class World:
    """Event-sourced view of one run's simulated enterprise."""

    _lock = threading.Lock()

    def __init__(self, db_path: str | Path | None = None, scenario: Scenario | None = None):
        self.db_path = Path(db_path or _DEFAULT_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.scenario = scenario or load_scenario()
        self._conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_SCHEMA)

    # -- events -----------------------------------------------------------------------------
    def events(self, run_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT seq, at, server, tool, kind, payload FROM events WHERE run_id = ?"
        args: list[Any] = [run_id]
        if kind:
            q += " AND kind = ?"
            args.append(kind)
        rows = self._conn.execute(q + " ORDER BY seq", args).fetchall()
        return [
            {"seq": s, "at": at, "server": sv, "tool": t, "kind": k, "payload": json.loads(p)}
            for s, at, sv, t, k, p in rows
        ]

    def record(self, run_id: str, server: str, tool: str, kind: str, payload: dict[str, Any], advance_minutes: int = 0) -> dict[str, Any]:
        with self._lock:
            now = self.now(run_id)
            seq = self._conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE run_id = ?", (run_id,)).fetchone()[0]
            body = dict(payload, advance_minutes=advance_minutes)
            self._conn.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, seq, iso(now), server, tool, kind, json.dumps(body, sort_keys=True)),
            )
        return {"seq": seq, "at": iso(now), **body}

    def reset(self, run_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM events WHERE run_id = ?", (run_id,))

    # -- simulated clock ------------------------------------------------------------------------
    def now(self, run_id: str) -> datetime:
        start = _parse(self.scenario.session_start)
        rows = self._conn.execute("SELECT payload FROM events WHERE run_id = ?", (run_id,)).fetchall()
        advance = sum(int(json.loads(p).get("advance_minutes", 0)) for (p,) in rows)
        return start + timedelta(minutes=advance)

    # -- derived state ------------------------------------------------------------------------
    def current_version(self, run_id: str, service: str, environment: str) -> str | None:
        version = None
        for d in self.scenario.deployments:
            if d["service"] == service and d["environment"] == environment:
                if version is None or _parse(d["finished_at"]) > _parse(version[1]):
                    version = (d["version"], d["finished_at"])
        current = version[0] if version else None
        for e in self.events(run_id, "rollback"):
            p = e["payload"]
            if p["service"] == service and p["environment"] == environment:
                current = p["to_version"]
        return current

    def recovered_at(self, run_id: str, service: str, environment: str) -> datetime | None:
        """When metrics return to baseline after a rollback to a known-good version, if any."""
        bad = {"checkout-api": "v4.17"}.get(service)
        for e in reversed(self.events(run_id, "rollback")):
            p = e["payload"]
            if p["service"] == service and p["environment"] == environment and p["to_version"] != bad:
                return _parse(e["at"]) + timedelta(minutes=self.scenario.rollback_recovery_minutes)
        return None
