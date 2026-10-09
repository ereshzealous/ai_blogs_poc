"""The simulated enterprise: ITSM, observability and a release pipeline for INC-4917, in one SQLite file (world.db).

Nothing here touches real infrastructure.  The release pipeline keeps its own ground truth (`deployments`, `rollbacks`,
`idempotency`, `capability_checks`, `capability_uses`): the proof asks the world, not the platform, how many times
production changed.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import yaml

SEED = Path(__file__).resolve().parents[2] / "scenarios" / "inc_4917" / "seed.yaml"

SCHEMA = """
CREATE TABLE IF NOT EXISTS deployments (service_env TEXT, seq INTEGER, id TEXT, version TEXT, commit_sha TEXT, finished_at TEXT, current INTEGER,
  PRIMARY KEY (service_env, seq));
CREATE TABLE IF NOT EXISTS rollbacks (id INTEGER PRIMARY KEY AUTOINCREMENT, service TEXT, environment TEXT, from_version TEXT, to_version TEXT,
  idempotency_key TEXT, capability_jti TEXT, via_server TEXT, executed_at REAL);
CREATE TABLE IF NOT EXISTS idempotency (key TEXT PRIMARY KEY, result_json TEXT, first_seen REAL, hits INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS capability_uses (jti TEXT PRIMARY KEY, used_at REAL, idempotency_key TEXT);
CREATE TABLE IF NOT EXISTS capability_checks (id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, server TEXT, tool TEXT, arguments_json TEXT,
  outcome TEXT, code TEXT, detail TEXT, jti TEXT, digest TEXT, traceparent TEXT);
CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, server TEXT, tool TEXT, arguments_json TEXT, traceparent TEXT);
CREATE TABLE IF NOT EXISTS log_lines (service_env TEXT, seq INTEGER, id TEXT, text TEXT, PRIMARY KEY (service_env, seq));
"""


class BusinessError(Exception):
    pass


class World:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.seed = yaml.safe_load(SEED.read_text())

    # ---- setup ---------------------------------------------------------------------------------------------------------
    @classmethod
    def reset(cls, path: str | Path, inject: bool = False) -> World:
        p = Path(path)
        for suffix in ("", "-wal", "-shm"):
            Path(str(p) + suffix).unlink(missing_ok=True)
        w = cls(p)
        with w.db:
            for se, rows in w.seed["deployments"].items():
                for i, r in enumerate(rows):
                    w.db.execute("INSERT INTO deployments VALUES (?,?,?,?,?,?,?)",
                                 (se, i, r["id"], r["version"], r["commit"], r["finished_at"], int(i == len(rows) - 1)))
            for se, rows in w.seed["logs"].items():
                if se == "injected":
                    continue
                lines = rows + (w.seed["logs"]["injected"] if inject and se == "checkout-api/production" else [])
                for i, r in enumerate(lines):
                    w.db.execute("INSERT INTO log_lines VALUES (?,?,?,?)", (se, i, r["id"], r["text"]))
        return w

    def record_call(self, server: str, tool: str, args: dict[str, Any], traceparent: str | None) -> None:
        self.db.execute("INSERT INTO calls (at, server, tool, arguments_json, traceparent) VALUES (?,?,?,?,?)",
                        (time.time(), server, tool, json.dumps(args, sort_keys=True), traceparent))

    def record_check(self, server: str, tool: str, args: dict, outcome: str, code: str, detail: str, jti: str | None, digest: str | None,
                     traceparent: str | None) -> None:
        self.db.execute("INSERT INTO capability_checks (at, server, tool, arguments_json, outcome, code, detail, jti, digest, traceparent) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)", (time.time(), server, tool, json.dumps(args, sort_keys=True), outcome, code, detail, jti, digest, traceparent))

    # ---- reads ---------------------------------------------------------------------------------------------------------
    def current(self, service: str, env: str) -> str:
        row = self.db.execute("SELECT version FROM deployments WHERE service_env=? AND current=1", (f"{service}/{env}",)).fetchone()
        if not row:
            raise BusinessError(f"no deployment for {service} in {env}")
        return row[0]

    def get_incident(self, incident_id: str) -> dict[str, Any]:
        inc = self.seed["incident"]
        if incident_id != inc["id"]:
            raise BusinessError(f"unknown incident {incident_id}")
        return {**inc, "running_version": self.current(inc["service"], inc["environment"])}

    def get_deployment(self, service: str, env: str) -> dict[str, Any]:
        rows = self.db.execute("SELECT id, version, commit_sha, finished_at, current FROM deployments WHERE service_env=? ORDER BY seq",
                               (f"{service}/{env}",)).fetchall()
        if not rows:
            raise BusinessError(f"no deployment for {service} in {env}")
        hist = [{"id": r[0], "version": r[1], "commit": r[2], "finished_at": r[3], "current": bool(r[4])} for r in rows]
        cur = next(h for h in hist if h["current"])
        prev = [h for h in hist if not h["current"] and h["version"] != cur["version"]]
        return {"service": service, "environment": env, "running_version": cur["version"], "deployment_id": cur["id"],
                "previous_version": prev[-1]["version"] if prev else None, "history": hist}

    def get_metrics(self, service: str, env: str) -> dict[str, Any]:
        m = self.seed["metrics"].get(f"{service}/{env}")
        if not m:
            raise BusinessError(f"no metrics for {service} in {env}")
        running = self.current(service, env)
        active = m.get("incident_version") == running
        out = {k: (v["incident"] if active and "incident" in v else v["baseline"]) for k, v in m.items() if isinstance(v, dict)}
        slo = self.seed["services"][service]["slo_p95_ms"]
        return {"service": service, "environment": env, "running_version": running, **out, "slo_p95_ms": slo,
                "breaching_slo": out["latency_p95_ms"] > slo}

    def get_logs(self, service: str, env: str) -> dict[str, Any]:
        rows = self.db.execute("SELECT id, text FROM log_lines WHERE service_env=? ORDER BY seq", (f"{service}/{env}",)).fetchall()
        return {"service": service, "environment": env, "lines": [{"id": r[0], "text": r[1]} for r in rows]}

    def inspect_release(self, service: str, version: str) -> dict[str, Any]:
        rel = self.seed["releases"].get(f"{service}/{version}")
        if not rel:
            raise BusinessError(f"unknown release {service} {version}")
        return {"service": service, "version": version, **rel}

    # ---- the one consequential write ------------------------------------------------------------------------------------
    def execute_rollback(self, service: str, env: str, target_version: str, idempotency_key: str, jti: str | None, via: str) -> dict[str, Any]:
        """Idempotent: a key seen before returns the first result and changes nothing."""
        hit = self.db.execute("SELECT result_json FROM idempotency WHERE key=?", (idempotency_key,)).fetchone()
        if hit:
            self.db.execute("UPDATE idempotency SET hits = hits + 1 WHERE key=?", (idempotency_key,))
            return {**json.loads(hit[0]), "idempotent_replay": True}
        se = f"{service}/{env}"
        rows = self.db.execute("SELECT seq, version, current FROM deployments WHERE service_env=? ORDER BY seq", (se,)).fetchall()
        if not rows:
            raise BusinessError(f"no deployment for {service} in {env}")
        cur = next(r for r in rows if r[2])
        target = [r for r in rows if r[1] == target_version]
        if not target:
            raise BusinessError(f"{target_version} was never deployed to {service} {env}")
        with self.db:
            self.db.execute("UPDATE deployments SET current=0 WHERE service_env=?", (se,))
            self.db.execute("UPDATE deployments SET current=1 WHERE service_env=? AND seq=?", (se, target[0][0]))
            cur_id = self.db.execute("INSERT INTO rollbacks (service, environment, from_version, to_version, idempotency_key, capability_jti, via_server, executed_at) "
                                     "VALUES (?,?,?,?,?,?,?,?)", (service, env, cur[1], target_version, idempotency_key, jti, via, time.time())).lastrowid
            result = {"status": "SUCCEEDED", "rollback_id": f"RB-{cur_id:05d}", "service": service, "environment": env,
                      "from_version": cur[1], "to_version": target_version, "idempotent_replay": False}
            self.db.execute("INSERT INTO idempotency (key, result_json, first_seen) VALUES (?,?,?)", (idempotency_key, json.dumps(result), time.time()))
        return result

    def use_jti(self, jti: str, idempotency_key: str) -> None:
        self.db.execute("INSERT INTO capability_uses VALUES (?,?,?)", (jti, time.time(), idempotency_key))

    def seen_jti(self) -> set[str]:
        return {r[0] for r in self.db.execute("SELECT jti FROM capability_uses")}

    # ---- ground truth for the proof --------------------------------------------------------------------------------------
    def rollback_count(self, service: str | None = None) -> int:
        if service:
            return self.db.execute("SELECT COUNT(*) FROM rollbacks WHERE service=?", (service,)).fetchone()[0]
        return self.db.execute("SELECT COUNT(*) FROM rollbacks").fetchone()[0]

    def rollbacks(self) -> list[dict[str, Any]]:
        cols = ["id", "service", "environment", "from_version", "to_version", "idempotency_key", "capability_jti", "via_server", "executed_at"]
        return [dict(zip(cols, r)) for r in self.db.execute("SELECT * FROM rollbacks ORDER BY id")]

    def checks(self) -> list[dict[str, Any]]:
        cols = ["id", "at", "server", "tool", "arguments_json", "outcome", "code", "detail", "jti", "digest", "traceparent"]
        return [dict(zip(cols, r)) for r in self.db.execute("SELECT * FROM capability_checks ORDER BY id")]

    def calls(self) -> list[dict[str, Any]]:
        cols = ["id", "at", "server", "tool", "arguments_json", "traceparent"]
        return [dict(zip(cols, r)) for r in self.db.execute("SELECT * FROM calls ORDER BY id")]

    def idempotency_hits(self, key: str) -> int:
        r = self.db.execute("SELECT hits FROM idempotency WHERE key=?", (key,)).fetchone()
        return r[0] if r else 0
