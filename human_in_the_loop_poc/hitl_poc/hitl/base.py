"""Shared plumbing: configuration, the deterministic clock and ids, canonical digests, identity, audit and spans.

Everything here is deterministic.  A run is reproducible byte for byte because time only moves when a test moves it and
every id is derived from stable inputs.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config"
T0 = 1790690520.0                 # 2026-09-29 14:02:00 UTC, the moment the payment-service alert fires
T_HITL = T0 + 7 * 60              # 14:09:00 UTC: the event reaches the HITL runtime in the protocol experiments (H1–H9)


def load(name: str) -> dict[str, Any]:
    return yaml.safe_load((CONFIG / name).read_text())


def canonical(obj: Any) -> str:
    """Canonical JSON: sorted keys, no whitespace, UTF-8.  Two equal actions always canonicalize to the same string."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def short_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}-" + sha256("|".join(map(str, parts)))[:10]


class Clock:
    def __init__(self, start: float = T0):
        self.t = start

    def now(self) -> float:
        return self.t

    def advance(self, seconds: float) -> float:
        self.t += seconds
        return self.t


def iso(t: float) -> str:
    import datetime as _dt
    return _dt.datetime.fromtimestamp(t, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- identity --------------------------------------------------------------------------------------------------------


class AuthError(Exception):
    pass


class Directory:
    """The simulated identity provider.  The only way to become an approver is to present that approver's credential."""

    def __init__(self) -> None:
        cfg = load("principals.yaml")
        self.principals: dict[str, dict[str, Any]] = cfg["principals"]
        self.credentials: dict[str, str] = cfg["credentials"]
        self.runtimes: dict[str, list[str]] = cfg.get("runtimes", {})
        self.delegations: dict[str, dict[str, Any]] = cfg.get("delegations", {})
        self.channel_links: dict[str, dict[str, str]] = cfg.get("channel_links", {})

    def authenticate(self, credential: str | None) -> str:
        if not credential or credential not in self.credentials:
            raise AuthError("unknown credential")
        return self.credentials[credential]

    def principal_for_channel(self, channel: str, user_id: str) -> str:
        """A chat click carries the channel's user id.  It is an enterprise principal only through an explicit link."""
        who = self.channel_links.get(channel, {}).get(user_id)
        if not who:
            raise AuthError(f"{channel} user {user_id} maps to no enterprise principal")
        return who

    def kind(self, principal: str) -> str:
        return self.principals.get(principal, {}).get("kind", "unknown")

    def roles(self, principal: str) -> list[str]:
        return list(self.principals.get(principal, {}).get("roles", []))

    def oncall(self, slot: str) -> str | None:
        return next((p for p, v in self.principals.items() if v.get("oncall") == slot), None)

    def grant(self, principal: str, role: str) -> None:            # used by tests that change the world
        self.principals[principal].setdefault("roles", []).append(role)

    def revoke(self, principal: str, role: str) -> None:
        self.principals[principal]["roles"] = [r for r in self.roles(principal) if r != role]

    # ---- the identity context the approval protocol consumes (built by Agent Identity, re-checked on resume) --------
    def agent_enabled(self, agent: str) -> bool:
        return self.principals.get(agent, {}).get("status") == "enabled"

    def disable_agent(self, agent: str) -> None:
        self.principals[agent]["status"] = "disabled"

    def runtime_registered(self, agent: str, runtime: str) -> bool:
        return runtime in self.runtimes.get(agent, [])

    def delegation_active(self, ref: str) -> bool:
        return self.delegations.get(ref, {}).get("status") == "active"

    def revoke_delegation(self, ref: str) -> None:
        self.delegations[ref]["status"] = "revoked"


# ---- audit -----------------------------------------------------------------------------------------------------------

GENESIS = "0" * 64


class AuditLog:
    """Append-only, hash-chained records of consequential facts (what, who, on whose authority, what changed)."""

    def __init__(self, db: sqlite3.Connection, clock: Clock):
        self.db, self.clock = db, clock
        db.execute("CREATE TABLE IF NOT EXISTS audit (n INTEGER PRIMARY KEY AUTOINCREMENT, t REAL, correlation_id TEXT, "
                   "proposal_id TEXT, kind TEXT, record TEXT, prev TEXT, hash TEXT)")

    def record(self, kind: str, correlation_id: str | None, proposal_id: str | None, /, **fields: Any) -> None:
        prev = self.db.execute("SELECT hash FROM audit ORDER BY n DESC LIMIT 1").fetchone()
        prev_h = prev[0] if prev else GENESIS
        body = canonical(fields)
        t = self.clock.now()
        h = sha256(f"{prev_h}|{t}|{correlation_id}|{proposal_id}|{kind}|{body}")
        self.db.execute("INSERT INTO audit (t, correlation_id, proposal_id, kind, record, prev, hash) VALUES (?,?,?,?,?,?,?)",
                        (t, correlation_id, proposal_id, kind, body, prev_h, h))
        self.db.commit()

    def records(self, correlation_id: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT n, t, correlation_id, proposal_id, kind, record, prev, hash FROM audit"
        rows = self.db.execute(q + (" WHERE correlation_id=? ORDER BY n" if correlation_id else " ORDER BY n"),
                               (correlation_id,) if correlation_id else ()).fetchall()
        return [{"n": r[0], "t": r[1], "time": iso(r[1]), "correlation_id": r[2], "proposal_id": r[3], "kind": r[4],
                 "record": json.loads(r[5]), "prev": r[6], "hash": r[7]} for r in rows]

    def verify(self) -> tuple[bool, int | None]:
        prev_h = GENESIS
        for n, t, c, p, k, body, prev, h in self.db.execute("SELECT n, t, correlation_id, proposal_id, kind, record, prev, hash FROM audit ORDER BY n"):
            if prev != prev_h or h != sha256(f"{prev_h}|{t}|{c}|{p}|{k}|{body}"):
                return False, n
            prev_h = h
        return True, None


# ---- spans -----------------------------------------------------------------------------------------------------------


class Telemetry:
    """Observability: one span per unit of work on the correlation id.  Explains behaviour; audit proves authority."""

    def __init__(self, clock: Clock):
        self.clock = clock
        self.spans: list[dict[str, Any]] = []
        self.stack: list[str] = []

    @contextmanager
    def span(self, kind: str, trace_id: str, name: str, **attrs: Any) -> Iterator[dict[str, Any]]:
        sid = short_id("sp", trace_id, kind, name, len(self.spans))
        s = {"trace_id": trace_id, "span_id": sid, "parent": self.stack[-1] if self.stack else None, "kind": kind, "name": name,
             "start": self.clock.now(), "attrs": attrs, "status": "ok"}
        self.stack.append(sid)
        try:
            yield s
        except Exception as e:  # noqa: BLE001 - recorded, then re-raised
            s["status"] = f"error: {type(e).__name__}"
            raise
        finally:
            self.stack.pop()
            s["end"] = self.clock.now()
            self.spans.append(s)


def connect(path: Path | str) -> sqlite3.Connection:
    db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    return db
