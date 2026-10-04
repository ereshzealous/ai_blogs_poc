"""Deterministic INC-4917 systems of record, shared by every MCP server process through one SQLite file.

The world is the "enterprise": deployments, metrics, logs, pods and incident records. Nothing is random.
It keeps the state that must survive process restarts (current versions, the simulated clock, executed writes,
idempotency records, injected faults), so a crashed platform can be restarted against the same reality.

Fault injection (per tool, stored in the database so tests can arm it from another process):
  timeout        the call sleeps past the client's timeout *before* doing anything (safe to retry)
  lose_response  the write executes and commits, then the response is delayed past the client's timeout
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

DATA = Path(__file__).parent / "data" / "inc4917.yaml"
DEFAULT_DB = Path(os.environ.get("LAP_ENTERPRISE_DB", "var/enterprise.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS executions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, tool TEXT NOT NULL, args TEXT NOT NULL,
  idempotency_key TEXT, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS idempotency (
  key TEXT PRIMARY KEY, tool TEXT NOT NULL, args_digest TEXT NOT NULL, result TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS replays (id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, tool TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS faults (tool TEXT PRIMARY KEY, mode TEXT NOT NULL, remaining INTEGER NOT NULL, delay_s REAL NOT NULL);
CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY AUTOINCREMENT, tool TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS incident_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deployments (id TEXT PRIMARY KEY, body TEXT NOT NULL, started_at TEXT NOT NULL);
"""


class IdempotencyConflict(ValueError):
    """The same idempotency key was reused with different arguments."""


def _digest(args: dict[str, Any]) -> str:
    clean = {k: v for k, v in args.items() if k != "idempotency_key"}
    return hashlib.sha256(json.dumps(clean, sort_keys=True).encode()).hexdigest()[:16]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class World:
    def __init__(self, db_path: str | Path | None = None):
        self.path = Path(db_path or DEFAULT_DB)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(DATA, encoding="utf-8") as fh:
            self.s = yaml.safe_load(fh)
        self._db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=30000")
        self._db.executescript(SCHEMA)

    # ------------------------------------------------------------------ admin (tests, experiments)
    def reset(self) -> None:
        for table in ("state", "executions", "idempotency", "replays", "faults", "calls", "incident_notes", "deployments"):
            self._db.execute(f"DELETE FROM {table}")

    def arm_fault(self, tool: str, mode: str, times: int = 1, delay_s: float = 4.0) -> None:
        assert mode in {"timeout", "lose_response"}, mode
        self._db.execute("INSERT OR REPLACE INTO faults VALUES (?,?,?,?)", (tool, mode, times, delay_s))

    def take_fault(self, tool: str) -> tuple[str, float] | None:
        row = self._db.execute("SELECT mode, remaining, delay_s FROM faults WHERE tool=?", (tool,)).fetchone()
        if not row or row[1] <= 0:
            return None
        self._db.execute("UPDATE faults SET remaining = remaining - 1 WHERE tool=?", (tool,))
        return row[0], row[2]

    def record_call(self, tool: str) -> None:
        self._db.execute("INSERT INTO calls (tool, at) VALUES (?,?)", (tool, _iso(self.now())))

    def executions(self, tool: str | None = None) -> list[dict[str, Any]]:
        q, p = "SELECT tool, args, idempotency_key, at FROM executions", ()
        if tool:
            q, p = q + " WHERE tool=?", (tool,)
        return [{"tool": t, "args": json.loads(a), "idempotency_key": k, "at": at} for t, a, k, at in self._db.execute(q + " ORDER BY id", p)]

    def replay_count(self, tool: str) -> int:
        return self._db.execute("SELECT COUNT(*) FROM replays WHERE tool=?", (tool,)).fetchone()[0]

    def call_count(self, tool: str) -> int:
        return self._db.execute("SELECT COUNT(*) FROM calls WHERE tool=?", (tool,)).fetchone()[0]

    def notes(self, incident_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute("SELECT status, note, at FROM incident_notes WHERE incident_id=? ORDER BY id", (incident_id,))
        return [{"status": s, "note": n, "at": at} for s, n, at in rows]

    # ------------------------------------------------------------------ state helpers
    def _get(self, key: str, default: Any = None) -> Any:
        row = self._db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _set(self, key: str, value: Any) -> None:
        self._db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, json.dumps(value)))

    def now(self) -> datetime:
        return _parse(self.s["session_start"]) + timedelta(minutes=self._get("clock_offset_min", 0))

    def version(self, service: str, environment: str) -> str | None:
        override = self._get(f"version:{service}:{environment}")
        if override:
            return override
        deps = [d for d in self.s["deployments"] if d["service"] == service and d["environment"] == environment]
        return max(deps, key=lambda d: d["started_at"])["version"] if deps else None

    def incident_active(self, service: str, environment: str) -> bool:
        m = self.s["metrics"].get(service, {}).get(environment)
        if not m or not m.get("incident_start"):
            return False
        if self.version(service, environment) != "v4.17":
            rolled = self._get(f"rolled_back_at:{service}:{environment}")
            if rolled and self.now() >= _parse(rolled) + timedelta(minutes=self.s["rollback_recovery_minutes"]):
                return False
        start = _parse(f"{self.s['date']}T{m['incident_start']}:00Z")
        return self.now() >= start

    # ------------------------------------------------------------------ idempotent writes
    def begin_write(self, tool: str, args: dict[str, Any]) -> dict[str, Any] | None:
        """Return the stored result if this key was already executed with the same arguments."""
        key = args.get("idempotency_key")
        if not key:
            return None
        row = self._db.execute("SELECT tool, args_digest, result FROM idempotency WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        if row[0] != tool or row[1] != _digest(args):
            raise IdempotencyConflict(f"idempotency key {key} was already used with different arguments")
        self._db.execute("INSERT INTO replays (key, tool, at) VALUES (?,?,?)", (key, tool, _iso(self.now())))
        return {**json.loads(row[2]), "replayed": True}

    def commit_write(self, tool: str, args: dict[str, Any], result: dict[str, Any]) -> None:
        key = args.get("idempotency_key")
        at = _iso(self.now())
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._db.execute("INSERT INTO executions (tool, args, idempotency_key, at) VALUES (?,?,?,?)",
                             (tool, json.dumps({k: v for k, v in args.items() if k != "idempotency_key"}, sort_keys=True), key, at))
            if key:
                self._db.execute("INSERT INTO idempotency VALUES (?,?,?,?,?)", (key, tool, _digest(args), json.dumps(result), at))
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    # ------------------------------------------------------------------ itsm
    def get_incident(self, incident_id: str) -> dict[str, Any]:
        inc = next((i for i in self.s["incidents"] if i["id"] == incident_id), None)
        if inc is None:
            raise LookupError(f"incident {incident_id} not found")
        notes = self.notes(incident_id)
        return {**inc, "status": notes[-1]["status"] if notes else inc["status"], "work_notes": notes}

    def update_incident(self, args: dict[str, Any]) -> dict[str, Any]:
        stored = self.begin_write("itsm.update_incident", args)
        if stored:
            return stored
        self.get_incident(args["incident_id"])
        at = _iso(self.now())
        self._db.execute("INSERT INTO incident_notes (incident_id, status, note, at) VALUES (?,?,?,?)",
                         (args["incident_id"], args["status"], args["note"], at))
        result = {"incident_id": args["incident_id"], "status": args["status"], "updated_at": at, "replayed": False}
        self.commit_write("itsm.update_incident", args, result)
        return result

    # ------------------------------------------------------------------ source control
    def _all_deployments(self) -> list[dict[str, Any]]:
        extra = [json.loads(b) for (b,) in self._db.execute("SELECT body FROM deployments ORDER BY started_at")]
        return self.s["deployments"] + extra

    def search_deployments(self, service: str | None, environment: str | None, since_hours: int) -> dict[str, Any]:
        since = self.now() - timedelta(hours=since_hours)
        rows = [d for d in self._all_deployments()
                if (not service or d["service"] == service) and (not environment or d["environment"] == environment)
                and _parse(d["started_at"]) >= since]
        rows.sort(key=lambda d: d["started_at"], reverse=True)
        return {"now": _iso(self.now()), "count": len(rows), "deployments": rows}

    def get_diff(self, commit: str) -> dict[str, Any]:
        c = self.s["commits"].get(commit)
        if c is None:
            raise LookupError(f"commit {commit} not found")
        return {"commit": commit, **c}

    def rollback_release(self, args: dict[str, Any]) -> dict[str, Any]:
        tool = "source_control.rollback_release"
        stored = self.begin_write(tool, args)
        if stored:
            return stored
        service, env, target = args["service"], args["environment"], args["target_version"]
        current = self.version(service, env)
        known = {r["version"] for r in self.s["releases"] if r["service"] == service}
        if target not in known:
            raise LookupError(f"{service} has no release {target}")
        # Like a real pipeline, a second rollback request starts another rollout (pods restart again), even when the
        # service already runs the target version. That is exactly the duplicate side effect idempotency prevents.
        now = self.now()
        n = self._db.execute("SELECT COUNT(*) FROM deployments").fetchone()[0]
        dep = {"id": f"DEP-9{n + 1:04d}", "service": service, "environment": env, "version": target,
               "previous_version": current, "strategy": "rollback", "status": "succeeded",
               "triggered_by": "release-pipeline (rollback)", "started_at": _iso(now),
               "finished_at": _iso(now + timedelta(minutes=2))}
        self._db.execute("INSERT INTO deployments VALUES (?,?,?)", (dep["id"], json.dumps(dep), dep["started_at"]))
        self._set(f"version:{service}:{env}", target)
        self._set(f"rolled_back_at:{service}:{env}", _iso(now))
        self._set("clock_offset_min", self._get("clock_offset_min", 0) + self.s["rollback_observe_minutes"])
        result = {"deployment_id": dep["id"], "service": service, "environment": env, "from_version": current,
                  "to_version": target, "status": "succeeded", "managed_by": "gitops-release-pipeline", "replayed": False,
                  "pods_restarted": 6}
        self.commit_write(tool, args, result)
        return result

    # ------------------------------------------------------------------ observability
    def _metric(self, service: str, env: str, name: str) -> float:
        m = self.s["metrics"].get(service, {}).get(env)
        if not m or name not in m:
            raise LookupError(f"no {name} for {service} in {env}")
        spec = m[name]
        return spec["incident"] if self.incident_active(service, env) and "incident" in spec else spec["baseline"]

    def query_latency(self, service: str, environment: str, window_minutes: int) -> dict[str, Any]:
        svc = self.s["services"].get(service)
        if svc is None:
            raise LookupError(f"unknown service {service}")
        p95 = self._metric(service, environment, "latency_p95_ms")
        p50 = self._metric(service, environment, "latency_p50_ms")
        base = self.s["metrics"][service][environment]["latency_p95_ms"]["baseline"]
        m = self.s["metrics"][service][environment]
        series = []
        for i in range(5, 0, -1):
            t = self.now() - timedelta(minutes=i * window_minutes / 5)
            start = m.get("incident_start")
            active = start and t >= _parse(f"{self.s['date']}T{start}:00Z") and self.incident_active(service, environment)
            series.append({"at": _iso(t), "p95_ms": m["latency_p95_ms"]["incident" if active else "baseline"]})
        return {"service": service, "environment": environment, "at": _iso(self.now()), "window_minutes": window_minutes,
                "p50_ms": p50, "p95_ms": p95, "baseline_p95_ms": base, "slo_p95_ms": svc["slo"]["p95_latency_ms"],
                "breaching_slo": p95 > svc["slo"]["p95_latency_ms"], "running_version": self.version(service, environment),
                "series": series}

    def search_logs(self, service: str, environment: str, level: str | None, limit: int) -> dict[str, Any]:
        logs = self.s["logs"].get(service, {}).get(environment)
        if logs is None:
            raise LookupError(f"no logs for {service} in {environment}")
        lines = list(logs.get("normal", []))
        if self.incident_active(service, environment):
            lines = logs.get("incident", []) + lines
        if level:
            lines = [ln for ln in lines if ln["level"] == level.upper()]
        counts = {"ERROR": 212, "WARN": 540, "INFO": 9000} if self.incident_active(service, environment) else {"ERROR": 0, "WARN": 3, "INFO": 9000}
        out = [{"level": ln["level"], "message": ln["message"].replace("{latency}", "190"),
                "count_last_15m": counts.get(ln["level"], 0)} for ln in lines[:limit]]
        return {"service": service, "environment": environment, "at": _iso(self.now()), "patterns": out}

    def get_slow_trace(self, service: str, environment: str) -> dict[str, Any]:
        key = "slow_example" if self.incident_active(service, environment) else "baseline_example"
        tr = self.s["traces"][key]
        if tr["service"] != service:
            raise LookupError(f"no traces for {service}")
        return {"environment": environment, **tr}

    # ------------------------------------------------------------------ database
    def get_connection_pool_stats(self, service: str, environment: str) -> dict[str, Any]:
        stats = self.s["database"]["pool_stats"].get(service, {}).get(environment)
        if stats is None:
            raise LookupError(f"no pool stats for {service} in {environment}")
        shape = "incident" if self.incident_active(service, environment) and "incident" in stats else "baseline"
        return {"service": service, "environment": environment, "at": _iso(self.now()), "database": "orders-db",
                **stats[shape], "baseline_max_connections": stats["baseline"]["max_connections"]}

    # ------------------------------------------------------------------ kubernetes
    def get_pods(self, service: str, environment: str) -> dict[str, Any]:
        k = self.s["kubernetes"].get(service, {}).get(environment)
        if k is None:
            raise LookupError(f"no workload {service} in {environment}")
        version = self.version(service, environment)
        pods = [{**p, "status": "Running", "ready": True, "image_version": version, "cpu_pct": 35, "memory_pct": 48} for p in k["pods"]]
        return {"service": service, "environment": environment, "cluster": k["cluster"], "managed_by": k["managed_by"],
                "revision": k["revision"], "ready": f"{len(pods)}/{len(pods)}", "pods": pods}

    def rollback_deployment(self, args: dict[str, Any]) -> dict[str, Any]:
        result = {"service": args["service"], "environment": args["environment"], "status": "rolled_back",
                  "warning": "workload is managed by gitops-release-pipeline; the controller will re-apply the desired revision",
                  "replayed": False}
        self.commit_write("kubernetes.rollback_deployment", args, result)
        return result
