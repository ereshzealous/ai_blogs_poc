"""The simulated enterprise behind INC-4917: ITSM, deployments and observability in one SQLite file.

Every MCP server process opens the same file (path in F2_WORLD_DB), so a write made by one server is seen by the others
and by the experiment harness.  Nothing here reads the wall clock: time is a simulated minute counter that only moves
when a rollout runs.  Every physical side effect is appended to `executions`; that ledger, not any client's belief, is
what the scorers count.

Writes accept an optional idempotency key.  A key seen before with the same arguments returns the stored result without
executing again (and counts a replay); the same key with different arguments is refused.  A call without a key always
executes.  This mirrors how deployment and ticketing APIs commonly behave; it is simulated, not a real backend.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import yaml

DATA = Path(__file__).parent / "data" / "inc4917.yaml"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deployments (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT, service TEXT, environment TEXT,
    version TEXT, minute INTEGER, author TEXT, summary TEXT, kind TEXT DEFAULT 'deploy');
CREATE TABLE IF NOT EXISTS running (service TEXT, environment TEXT, release TEXT, since INTEGER, PRIMARY KEY (service, environment));
CREATE TABLE IF NOT EXISTS recovered (service TEXT PRIMARY KEY, minute INTEGER);
CREATE TABLE IF NOT EXISTS executions (seq INTEGER PRIMARY KEY AUTOINCREMENT, tool TEXT, args TEXT, idempotency_key TEXT,
    result TEXT, minute INTEGER, wall REAL, pid INTEGER);
CREATE TABLE IF NOT EXISTS idem (key TEXT PRIMARY KEY, tool TEXT, args_hash TEXT, result TEXT, replays INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS calls (seq INTEGER PRIMARY KEY AUTOINCREMENT, tool TEXT, args TEXT, minute INTEGER, wall REAL, pid INTEGER);
CREATE TABLE IF NOT EXISTS faults (tool TEXT PRIMARY KEY, kind TEXT, seconds REAL, remaining INTEGER);
"""


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def hhmm(minute: int) -> str:
    day, m = divmod(minute, 1440)
    return f"{'D' + str(day) + ' ' if day else ''}{m // 60:02d}:{m % 60:02d}"


class BusinessError(ValueError):
    """An expected refusal from a system of record (unknown id, conflicting key, invalid rollback target)."""


class World:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.environ.get("F2_WORLD_DB", "world.db"))
        self.spec = yaml.safe_load(DATA.read_text())

    # ---- connection ---------------------------------------------------------------------------------------------
    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.row_factory = sqlite3.Row
        return db

    def reset(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            Path(str(self.path) + suffix).unlink(missing_ok=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        s = self.spec
        with self._db() as db:
            db.executescript(SCHEMA)
            db.execute("INSERT INTO meta VALUES ('now', ?)", (str(s["start_minute"]),))
            inc = dict(s["incident"], notes=[], timeline=[{"minute": s["incident"]["opened_minute"], "event": "opened by latency alert"}])
            db.execute("INSERT INTO incidents VALUES (?, ?)", (inc["id"], _canon(inc)))
            for d in s["deployments"]:
                db.execute("INSERT INTO deployments (id, service, environment, version, minute, author, summary) VALUES (?,?,?,?,?,?,?)",
                           (d["id"], d["service"], d["environment"], d["version"], d["minute"], d["author"], d["summary"]))
                if d.get("current"):
                    db.execute("INSERT INTO running VALUES (?,?,?,?)", (d["service"], d["environment"], d["id"], d["minute"]))

    # ---- clock and bookkeeping -----------------------------------------------------------------------------------
    def now(self, db: sqlite3.Connection | None = None) -> int:
        db = db or self._db()
        return int(db.execute("SELECT v FROM meta WHERE k='now'").fetchone()[0])

    def record_call(self, tool: str, args: dict[str, Any]) -> None:
        with self._db() as db:
            db.execute("INSERT INTO calls (tool, args, minute, wall, pid) VALUES (?,?,?,?,?)",
                       (tool, _canon(args), self.now(db), time.time(), os.getpid()))

    def arm_fault(self, tool: str, kind: str, seconds: float = 0.0, times: int = 1) -> None:
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO faults VALUES (?,?,?,?)", (tool, kind, seconds, times))

    def take_fault(self, tool: str) -> tuple[str, float] | None:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT kind, seconds, remaining FROM faults WHERE tool=?", (tool,)).fetchone()
            if not row or row["remaining"] <= 0:
                db.execute("COMMIT")
                return None
            db.execute("UPDATE faults SET remaining=remaining-1 WHERE tool=?", (tool,))
            db.execute("COMMIT")
            return row["kind"], row["seconds"]

    # ---- reads ---------------------------------------------------------------------------------------------------
    def get_incident(self, incident_id: str) -> dict[str, Any]:
        row = self._db().execute("SELECT doc FROM incidents WHERE id=?", (incident_id,)).fetchone()
        if not row:
            raise BusinessError(f"incident {incident_id} not found")
        doc = json.loads(row["doc"])
        doc["opened"] = hhmm(doc.pop("opened_minute"))
        doc["timeline"] = [{"time": hhmm(t["minute"]), "event": t["event"]} for t in doc["timeline"]]
        doc["notes"] = [{"time": hhmm(n["minute"]), "status": n["status"], "note": n["note"]} for n in doc["notes"]]
        return doc

    def list_deployments(self, service: str, environment: str, limit: int = 5) -> dict[str, Any]:
        self._service(service)
        db = self._db()
        rows = db.execute("SELECT * FROM deployments WHERE service=? AND environment=? ORDER BY seq DESC LIMIT ?",
                          (service, environment, limit)).fetchall()
        cur = db.execute("SELECT release FROM running WHERE service=? AND environment=?", (service, environment)).fetchone()
        return {"service": service, "environment": environment, "running": cur["release"] if cur else None,
                "deployments": [{"release": r["id"], "version": r["version"], "time": hhmm(r["minute"]), "author": r["author"],
                                 "kind": r["kind"], "summary": r["summary"]} for r in rows]}

    def _service(self, service: str) -> dict[str, Any]:
        if service not in self.spec["services"]:
            raise BusinessError(f"unknown service {service}; known: {', '.join(self.spec['services'])}")
        return self.spec["services"][service]

    def _degraded_at(self, db: sqlite3.Connection, service: str, minute: int) -> bool:
        start = self.spec["metrics"][service].get("incident_start")
        if start is None or minute < start:
            return False
        rec = db.execute("SELECT minute FROM recovered WHERE service=?", (service,)).fetchone()
        return not (rec and minute >= rec["minute"] + self.spec["recovery_minutes"])

    def query_metrics(self, service: str, environment: str, metric: str, minutes: int = 30) -> dict[str, Any]:
        self._service(service)
        shapes = self.spec["metrics"][service]
        if metric not in shapes or metric == "incident_start":
            raise BusinessError(f"unknown metric {metric}; available: latency_p95_ms, error_rate_pct, db_pool_wait_ms, cpu_pct")
        db = self._db()
        now = self.now(db)
        minutes = max(1, min(int(minutes), 120))
        shape = shapes[metric]
        series = []
        for m in range(now - minutes + 1, now + 1):
            bad = environment == "production" and self._degraded_at(db, service, m)
            series.append([hhmm(m), shape["incident"] if bad and "incident" in shape else shape["baseline"]])
        step = max(1, minutes // 10)
        return {"service": service, "environment": environment, "metric": metric, "now": hhmm(now), "latest": series[-1][1],
                "max": max(v for _, v in series), "min": min(v for _, v in series), "series": series[::-step][::-1],
                "slo_p95_ms": self.spec["services"][service]["slo_p95_ms"] if metric == "latency_p95_ms" else None}

    def search_logs(self, service: str, environment: str, query: str = "", minutes: int = 30) -> dict[str, Any]:
        self._service(service)
        db = self._db()
        now = self.now(db)
        src = self.spec["logs"].get(service, {})
        bad = environment == "production" and self._degraded_at(db, service, now)
        lines = list(src.get("incident", [])) if bad else list(src.get("baseline", []))
        q = (query or "").lower().split()
        hits = [l for l in lines if not q or any(w in l.lower() for w in q)] or lines
        return {"service": service, "environment": environment, "window": f"{hhmm(now - minutes)}-{hhmm(now)}",
                "matched": len(hits), "lines": hits[:8]}

    # ---- writes (every physical execution is appended to `executions`) --------------------------------------------
    def _write(self, tool: str, args: dict[str, Any], key: str | None, do) -> dict[str, Any]:
        body = {k: v for k, v in args.items() if k != "idempotency_key"}
        ah = hashlib.sha256(_canon(body).encode()).hexdigest()
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
                result = do(db)
                db.execute("INSERT INTO executions (tool, args, idempotency_key, result, minute, wall, pid) VALUES (?,?,?,?,?,?,?)",
                           (tool, _canon(body), key, _canon(result), self.now(db), time.time(), os.getpid()))
                if key:
                    db.execute("INSERT INTO idem VALUES (?,?,?,?,0)", (key, tool, ah, _canon(result)))
                db.execute("COMMIT")
                return result
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def rollback_release(self, service: str, environment: str, to_release: str, key: str | None = None) -> dict[str, Any]:
        self._service(service)

        def do(db: sqlite3.Connection) -> dict[str, Any]:
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
            if environment == "production" and to_release in self.spec["healthy_releases"].get(service, []):
                db.execute("INSERT OR REPLACE INTO recovered VALUES (?, ?)", (service, now))
            db.execute("UPDATE meta SET v=? WHERE k='now'", (str(now + self.spec["rollback_minutes"]),))
            return {"status": "rolled_back", "service": service, "environment": environment, "from_release": cur["release"] if cur else None,
                    "to_release": to_release, "version": target["version"], "started": hhmm(now)}

        return self._write("rollback_release", {"service": service, "environment": environment, "to_release": to_release}, key, do)

    def restart_service(self, service: str, environment: str, key: str | None = None) -> dict[str, Any]:
        self._service(service)

        def do(db: sqlite3.Connection) -> dict[str, Any]:
            now = self.now(db)
            db.execute("UPDATE meta SET v=? WHERE k='now'", (str(now + 2),))
            return {"status": "restarted", "service": service, "environment": environment, "started": hhmm(now)}

        return self._write("restart_service", {"service": service, "environment": environment}, key, do)

    def scale_service(self, service: str, environment: str, replicas: int, key: str | None = None) -> dict[str, Any]:
        self._service(service)
        return self._write("scale_service", {"service": service, "environment": environment, "replicas": replicas}, key,
                           lambda db: {"status": "scaled", "service": service, "environment": environment, "replicas": replicas})

    def flush_sessions(self, service: str, environment: str, key: str | None = None) -> dict[str, Any]:
        self._service(service)
        return self._write("flush_sessions", {"service": service, "environment": environment}, key,
                           lambda db: {"status": "flushed", "service": service, "environment": environment, "sessions_dropped": 18422})

    def update_incident(self, incident_id: str, status: str, note: str, key: str | None = None) -> dict[str, Any]:
        if status not in ("investigating", "mitigated", "resolved"):
            raise BusinessError("status must be investigating, mitigated or resolved")

        def do(db: sqlite3.Connection) -> dict[str, Any]:
            row = db.execute("SELECT doc FROM incidents WHERE id=?", (incident_id,)).fetchone()
            if not row:
                raise BusinessError(f"incident {incident_id} not found")
            doc = json.loads(row["doc"])
            now = self.now(db)
            doc["status"] = status
            doc["notes"].append({"minute": now, "status": status, "note": note})
            db.execute("UPDATE incidents SET doc=? WHERE id=?", (_canon(doc), incident_id))
            return {"status": "updated", "incident_id": incident_id, "incident_status": status, "notes": len(doc["notes"])}

        return self._write("update_incident", {"incident_id": incident_id, "status": status, "note": note}, key, do)

    # ---- inspection (used by scorers and tests, never by either architecture) ------------------------------------
    def executions(self, tool: str | None = None) -> list[dict[str, Any]]:
        q, a = ("SELECT * FROM executions WHERE tool=? ORDER BY seq", (tool,)) if tool else ("SELECT * FROM executions ORDER BY seq", ())
        return [dict(r, args=json.loads(r["args"]), result=json.loads(r["result"])) for r in self._db().execute(q, a).fetchall()]

    def replays(self, tool: str) -> int:
        row = self._db().execute("SELECT COALESCE(SUM(replays),0) FROM idem WHERE tool=?", (tool,)).fetchone()
        return int(row[0])

    def calls(self) -> list[dict[str, Any]]:
        return [dict(r, args=json.loads(r["args"])) for r in self._db().execute("SELECT * FROM calls ORDER BY seq").fetchall()]

    def running(self, service: str, environment: str) -> str | None:
        r = self._db().execute("SELECT release FROM running WHERE service=? AND environment=?", (service, environment)).fetchone()
        return r["release"] if r else None

    def incident_doc(self, incident_id: str = "INC-4917") -> dict[str, Any]:
        return json.loads(self._db().execute("SELECT doc FROM incidents WHERE id=?", (incident_id,)).fetchone()["doc"])

    def healthy(self, service: str = "checkout-api") -> bool:
        db = self._db()
        return not self._degraded_at(db, service, self.now(db))
