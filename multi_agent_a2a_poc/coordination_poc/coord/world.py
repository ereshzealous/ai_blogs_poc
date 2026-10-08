"""The simulated enterprise behind every fixture: ITSM, observability, deployments, changes and runbooks in one SQLite file.

Generalised from F2's INC-4917 world (f2_layer_architecture/.../simulated_enterprise/world.py).  `reset(fixture)` loads
one fixture into the file; every MCP server process (in the host and in each A2A agent process) opens the same file,
so a write made through one process is seen by all of them and by the evaluator.

Nothing reads the wall clock: time is a simulated minute counter that only moves when a write executes.  Every
physical side effect is appended to `executions`; that ledger, not any component's belief, is what is scored.  Writes
accept an idempotency key (a repeated key with the same arguments returns the stored result and counts a replay; with
different arguments it is refused), exactly as in F2.  This is a simulation, not a real backend.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from coord.util import FIXTURES, canon, hhmm

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deployments (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT, service TEXT, environment TEXT,
    version TEXT, minute INTEGER, author TEXT, summary TEXT, kind TEXT DEFAULT 'deploy');
CREATE TABLE IF NOT EXISTS running (service TEXT, environment TEXT, release TEXT, since INTEGER, PRIMARY KEY (service, environment));
CREATE TABLE IF NOT EXISTS changes (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT, service TEXT, environment TEXT, minute INTEGER,
    kind TEXT, key TEXT, from_v TEXT, to_v TEXT, author TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS flags (service TEXT, environment TEXT, flag TEXT, value TEXT, PRIMARY KEY (service, environment, flag));
CREATE TABLE IF NOT EXISTS replicas (service TEXT PRIMARY KEY, n INTEGER);
CREATE TABLE IF NOT EXISTS recovered (service TEXT PRIMARY KEY, minute INTEGER);
CREATE TABLE IF NOT EXISTS executions (seq INTEGER PRIMARY KEY AUTOINCREMENT, tool TEXT, args TEXT, idempotency_key TEXT,
    result TEXT, minute INTEGER, wall REAL, pid INTEGER);
CREATE TABLE IF NOT EXISTS idem (key TEXT PRIMARY KEY, tool TEXT, args_hash TEXT, result TEXT, replays INTEGER DEFAULT 0);
"""

WRITE_TOOLS = ("rollback_release", "restart_service", "scale_service", "flush_sessions", "revert_config", "set_feature_flag")
READ_TOOLS = ("get_incident", "get_runbook", "query_metrics", "search_logs", "get_dependencies", "list_deployments", "get_change_history")


class BusinessError(ValueError):
    """An expected refusal from a system of record (unknown id, conflicting key, invalid target)."""


def match_value(expected: Any, actual: Any) -> bool:
    """Shared by world physics and the evaluator: literal, {in: [...]} or {gte, lte}."""
    if isinstance(expected, dict):
        if "in" in expected:
            return str(actual).lower() in {str(v).lower() for v in expected["in"]}
        try:
            a = float(actual)
        except (TypeError, ValueError):
            return False
        return ("gte" not in expected or a >= float(expected["gte"])) and ("lte" not in expected or a <= float(expected["lte"]))
    return str(expected).lower() == str(actual).lower()


def match_call(matcher: dict[str, Any], tool: str, args: dict[str, Any]) -> bool:
    if matcher["tool"] != tool:
        return False
    return all(k in args and match_value(v, args[k]) for k, v in (matcher.get("args") or {}).items())


def load_fixture(fixture_id: str) -> dict[str, Any]:
    spec = yaml.safe_load((FIXTURES / f"{fixture_id}.yaml").read_text())
    spec["runbooks"] = yaml.safe_load((FIXTURES / "runbooks.yaml").read_text())
    return spec


class World:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    # ---- connection and spec -------------------------------------------------------------------------------------
    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.row_factory = sqlite3.Row
        return db

    def spec(self, db: sqlite3.Connection | None = None) -> dict[str, Any]:
        db = db or self._db()
        return json.loads(db.execute("SELECT v FROM meta WHERE k='spec'").fetchone()[0])

    def reset(self, fixture_id: str) -> None:
        for suffix in ("", "-wal", "-shm"):
            Path(str(self.path) + suffix).unlink(missing_ok=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        s = load_fixture(fixture_id)
        with self._db() as db:
            db.executescript(SCHEMA)
            db.execute("INSERT INTO meta VALUES ('spec', ?)", (canon(s),))
            db.execute("INSERT INTO meta VALUES ('now', ?)", (str(s["start_minute"]),))
            db.execute("INSERT INTO meta VALUES ('fixture', ?)", (fixture_id,))
            inc = dict(s["incident"])
            inc["timeline"] = [{"minute": inc["opened_minute"], "event": f"opened by {inc['reporter']}"}]
            db.execute("INSERT INTO incidents VALUES (?, ?)", (inc["id"], canon(inc)))
            for d in s["deployments"]:
                db.execute("INSERT INTO deployments (id, service, environment, version, minute, author, summary) VALUES (?,?,?,?,?,?,?)",
                           (d["id"], d["service"], d["environment"], str(d["version"]), d["minute"], d["author"], d["summary"]))
                if d.get("current"):
                    db.execute("INSERT OR REPLACE INTO running VALUES (?,?,?,?)", (d["service"], d["environment"], d["id"], d["minute"]))
            for c in s.get("changes") or []:
                db.execute("INSERT INTO changes (id, service, environment, minute, kind, key, from_v, to_v, author, summary) VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (c["id"], c["service"], c["environment"], c["minute"], c["kind"], c["key"], str(c["from"]), str(c["to"]), c["author"], c["summary"]))
                if c["kind"] == "flag":
                    db.execute("INSERT OR REPLACE INTO flags VALUES (?,?,?,?)", (c["service"], c["environment"], c["key"], str(c["to"])))
            for name, svc in s["services"].items():
                db.execute("INSERT INTO replicas VALUES (?, ?)", (name, int(svc.get("replicas", 1))))

    # ---- clock and helpers ---------------------------------------------------------------------------------------
    def now(self, db: sqlite3.Connection | None = None) -> int:
        db = db or self._db()
        return int(db.execute("SELECT v FROM meta WHERE k='now'").fetchone()[0])

    def version(self) -> int:
        """World version = number of executed writes.  Two identical reads at the same version are duplicates."""
        return int(self._db().execute("SELECT COUNT(*) FROM executions").fetchone()[0])

    def _service(self, s: dict[str, Any], service: str) -> dict[str, Any]:
        if service not in s["services"]:
            raise BusinessError(f"unknown service {service}; known: {', '.join(sorted(s['services']))}")
        return s["services"][service]

    def _degraded_at(self, db: sqlite3.Connection, s: dict[str, Any], service: str, minute: int) -> bool:
        shape = s["metrics"].get(service, {})
        start, end = shape.get("incident_start"), shape.get("incident_end")
        if start is None or minute < start or (end is not None and minute >= end):
            return False
        rec = db.execute("SELECT minute FROM recovered WHERE service=?", (service,)).fetchone()
        return not (rec and minute >= rec["minute"] + s["physics"]["recovery_minutes"])

    # ---- reads ---------------------------------------------------------------------------------------------------
    def get_incident(self, incident_id: str) -> dict[str, Any]:
        row = self._db().execute("SELECT doc FROM incidents WHERE id=?", (incident_id,)).fetchone()
        if not row:
            raise BusinessError(f"incident {incident_id} not found")
        doc = json.loads(row["doc"])
        doc["opened"] = hhmm(doc.pop("opened_minute"))
        doc["timeline"] = [{"time": hhmm(t["minute"]), "event": t["event"]} for t in doc["timeline"]]
        doc["notes"] = [{"time": hhmm(n["minute"]), "author": n["author"], "note": n["note"]} for n in doc.get("notes", [])]
        doc["now"] = hhmm(self.now())
        return doc

    def get_runbook(self, service: str) -> dict[str, Any]:
        s = self.spec()
        svc = self._service(s, service)
        rb = s["runbooks"]
        return {"service": service, "runbook_id": svc["runbook"], "general": rb["general"], "service_runbook": rb["services"][svc["runbook"]]}

    def get_dependencies(self, service: str) -> dict[str, Any]:
        s = self.spec()
        svc = self._service(s, service)
        deps = []
        for d in svc.get("depends_on") or []:
            deps.append({"name": d, "kind": "internal"} if isinstance(d, str) else dict(d))
        dependents = sorted(n for n, x in s["services"].items()
                            if any((d if isinstance(d, str) else d["name"]) == service for d in x.get("depends_on") or []))
        row = self._db().execute("SELECT n FROM replicas WHERE service=?", (service,)).fetchone()
        return {"service": service, "owner": svc["owner"], "tier": svc["tier"], "replicas": row["n"] if row else None,
                "depends_on": deps, "dependents": dependents}

    def list_deployments(self, service: str, environment: str, limit: int = 5) -> dict[str, Any]:
        self._service(self.spec(), service)
        db = self._db()
        rows = db.execute("SELECT * FROM deployments WHERE service=? AND environment=? ORDER BY minute DESC, seq DESC LIMIT ?",
                          (service, environment, int(limit))).fetchall()
        cur = db.execute("SELECT release FROM running WHERE service=? AND environment=?", (service, environment)).fetchone()
        return {"service": service, "environment": environment, "running": cur["release"] if cur else None,
                "deployments": [{"release": r["id"], "version": r["version"], "time": hhmm(r["minute"]), "author": r["author"],
                                 "kind": r["kind"], "summary": r["summary"]} for r in rows]}

    def get_change_history(self, service: str, environment: str, limit: int = 10) -> dict[str, Any]:
        self._service(self.spec(), service)
        rows = self._db().execute("SELECT * FROM changes WHERE service=? AND environment=? ORDER BY minute DESC, seq DESC LIMIT ?",
                                  (service, environment, int(limit))).fetchall()
        return {"service": service, "environment": environment,
                "changes": [{"change_id": r["id"], "time": hhmm(r["minute"]), "kind": r["kind"], "key": r["key"], "from": r["from_v"],
                             "to": r["to_v"], "author": r["author"], "summary": r["summary"]} for r in rows]}

    def query_metrics(self, service: str, environment: str, metric: str, minutes: int = 30) -> dict[str, Any]:
        s = self.spec()
        svc = self._service(s, service)
        shapes = {k: v for k, v in s["metrics"].get(service, {}).items() if isinstance(v, dict)}
        if metric not in shapes:
            raise BusinessError(f"metric {metric} not available for {service}; available: {', '.join(sorted(shapes))}")
        db = self._db()
        now = self.now(db)
        minutes = max(1, min(int(minutes), 120))
        shape = shapes[metric]
        series = []
        for m in range(now - minutes + 1, now + 1):
            bad = environment == "production" and self._degraded_at(db, s, service, m)
            series.append([hhmm(m), shape["incident"] if bad and "incident" in shape else shape["baseline"]])
        step = max(1, minutes // 10)
        return {"service": service, "environment": environment, "metric": metric, "now": hhmm(now), "latest": series[-1][1],
                "max": max(v for _, v in series), "min": min(v for _, v in series), "series": series[::-step][::-1],
                "slo_p95_ms": svc.get("slo_p95_ms") if metric == "latency_p95_ms" else None}

    def search_logs(self, service: str, environment: str, query: str = "", minutes: int = 30) -> dict[str, Any]:
        s = self.spec()
        self._service(s, service)
        db = self._db()
        now = self.now(db)
        src = s["logs"].get(service, {})
        bad = environment == "production" and self._degraded_at(db, s, service, now)
        lines = list(src.get("incident", [])) if bad else list(src.get("baseline", []))
        q = (query or "").lower().split()
        hits = [ln for ln in lines if not q or any(w in ln.lower() for w in q)] or lines
        return {"service": service, "environment": environment, "window": f"{hhmm(now - int(minutes))}-{hhmm(now)}",
                "matched": len(hits), "lines": hits[:8]}

    # ---- writes ------------------------------------------------------------------------------------------------------
    def _write(self, tool: str, args: dict[str, Any], key: str | None, do: Callable[[sqlite3.Connection, dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        ah = hashlib.sha256(canon(args).encode()).hexdigest()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if key:
                    prev = db.execute("SELECT * FROM idem WHERE key=?", (key,)).fetchone()
                    if prev:
                        if prev["tool"] != tool or prev["args_hash"] != ah:
                            raise BusinessError(f"idempotency key {key} was already used with different arguments")
                        db.execute("UPDATE idem SET replays=replays+1 WHERE key=?", (key,))
                        db.execute("COMMIT")
                        return dict(json.loads(prev["result"]), idempotent_replay=True)
                s = self.spec(db)
                result = do(db, s)
                now = self.now(db)
                db.execute("INSERT INTO executions (tool, args, idempotency_key, result, minute, wall, pid) VALUES (?,?,?,?,?,?,?)",
                           (tool, canon(args), key, canon(result), now, time.time(), os.getpid()))
                for fix in s["physics"].get("fixes") or []:
                    if match_call(fix, tool, args):
                        for svc in fix["recovers"]:
                            db.execute("INSERT OR REPLACE INTO recovered VALUES (?, ?)", (svc, now))
                db.execute("UPDATE meta SET v=? WHERE k='now'", (str(now + int(s["physics"]["durations"].get(tool, 1))),))
                if key:
                    db.execute("INSERT INTO idem VALUES (?,?,?,?,0)", (key, tool, ah, canon(result)))
                db.execute("COMMIT")
                return result
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def rollback_release(self, service: str, environment: str, to_release: str, key: str | None = None) -> dict[str, Any]:
        def do(db: sqlite3.Connection, s: dict[str, Any]) -> dict[str, Any]:
            self._service(s, service)
            target = db.execute("SELECT * FROM deployments WHERE id=? AND service=? AND environment=? AND kind='deploy'",
                                (to_release, service, environment)).fetchone()
            if not target:
                raise BusinessError(f"{to_release} is not a release of {service} in {environment}")
            cur = db.execute("SELECT release FROM running WHERE service=? AND environment=?", (service, environment)).fetchone()
            now = self.now(db)
            db.execute("INSERT INTO deployments (id, service, environment, version, minute, author, summary, kind) VALUES (?,?,?,?,?,?,?,?)",
                       (to_release, service, environment, target["version"], now, "incident-automation",
                        f"rollback from {cur['release'] if cur else '?'} to {to_release}", "rollback"))
            db.execute("INSERT OR REPLACE INTO running VALUES (?,?,?,?)", (service, environment, to_release, now))
            return {"status": "rolled_back", "service": service, "environment": environment,
                    "from_release": cur["release"] if cur else None, "to_release": to_release, "version": target["version"], "started": hhmm(now)}

        return self._write("rollback_release", {"service": service, "environment": environment, "to_release": to_release}, key, do)

    def restart_service(self, service: str, environment: str, key: str | None = None) -> dict[str, Any]:
        def do(db: sqlite3.Connection, s: dict[str, Any]) -> dict[str, Any]:
            self._service(s, service)
            return {"status": "restarted", "service": service, "environment": environment, "started": hhmm(self.now(db))}

        return self._write("restart_service", {"service": service, "environment": environment}, key, do)

    def scale_service(self, service: str, environment: str, replicas: int, key: str | None = None) -> dict[str, Any]:
        def do(db: sqlite3.Connection, s: dict[str, Any]) -> dict[str, Any]:
            self._service(s, service)
            prev = db.execute("SELECT n FROM replicas WHERE service=?", (service,)).fetchone()
            db.execute("INSERT OR REPLACE INTO replicas VALUES (?, ?)", (service, int(replicas)))
            return {"status": "scaled", "service": service, "environment": environment, "from_replicas": prev["n"] if prev else None,
                    "replicas": int(replicas)}

        return self._write("scale_service", {"service": service, "environment": environment, "replicas": int(replicas)}, key, do)

    def flush_sessions(self, service: str, environment: str, key: str | None = None) -> dict[str, Any]:
        def do(db: sqlite3.Connection, s: dict[str, Any]) -> dict[str, Any]:
            self._service(s, service)
            return {"status": "flushed", "service": service, "environment": environment, "sessions_dropped": 6104118}

        return self._write("flush_sessions", {"service": service, "environment": environment}, key, do)

    def revert_config(self, service: str, environment: str, change_id: str, key: str | None = None) -> dict[str, Any]:
        def do(db: sqlite3.Connection, s: dict[str, Any]) -> dict[str, Any]:
            self._service(s, service)
            c = db.execute("SELECT * FROM changes WHERE id=? AND service=? AND environment=?", (change_id, service, environment)).fetchone()
            if not c or c["kind"] not in ("config", "flag"):
                raise BusinessError(f"{change_id} is not a config or flag change of {service} in {environment}")
            now = self.now(db)
            db.execute("INSERT INTO changes (id, service, environment, minute, kind, key, from_v, to_v, author, summary) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (f"rev-{change_id}", service, environment, now, c["kind"], c["key"], c["to_v"], c["from_v"], "incident-automation", f"revert {change_id}"))
            if c["kind"] == "flag":
                db.execute("INSERT OR REPLACE INTO flags VALUES (?,?,?,?)", (service, environment, c["key"], c["from_v"]))
            return {"status": "reverted", "service": service, "environment": environment, "change_id": change_id, "key": c["key"],
                    "value": c["from_v"]}

        return self._write("revert_config", {"service": service, "environment": environment, "change_id": change_id}, key, do)

    def set_feature_flag(self, service: str, environment: str, flag: str, value: str, key: str | None = None) -> dict[str, Any]:
        value = str(value).lower()

        def do(db: sqlite3.Connection, s: dict[str, Any]) -> dict[str, Any]:
            self._service(s, service)
            prev = db.execute("SELECT value FROM flags WHERE service=? AND environment=? AND flag=?", (service, environment, flag)).fetchone()
            now = self.now(db)
            db.execute("INSERT OR REPLACE INTO flags VALUES (?,?,?,?)", (service, environment, flag, value))
            db.execute("INSERT INTO changes (id, service, environment, minute, kind, key, from_v, to_v, author, summary) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (f"flag-{flag}-{now}", service, environment, now, "flag", flag, prev["value"] if prev else "unset", value,
                        "incident-automation", "set by incident automation"))
            return {"status": "flag_set", "service": service, "environment": environment, "flag": flag,
                    "from": prev["value"] if prev else None, "to": value}

        return self._write("set_feature_flag", {"service": service, "environment": environment, "flag": flag, "value": value}, key, do)

    # ---- inspection (evaluator and tests only; never reachable through a tool) --------------------------------------
    def executions(self) -> list[dict[str, Any]]:
        return [dict(r, args=json.loads(r["args"]), result=json.loads(r["result"]))
                for r in self._db().execute("SELECT * FROM executions ORDER BY seq").fetchall()]

    def replays(self) -> int:
        return int(self._db().execute("SELECT COALESCE(SUM(replays),0) FROM idem").fetchone()[0])

    def healthy(self, service: str) -> bool:
        db = self._db()
        return not self._degraded_at(db, self.spec(db), service, self.now(db))

    def fixture_id(self) -> str:
        return self._db().execute("SELECT v FROM meta WHERE k='fixture'").fetchone()[0]
