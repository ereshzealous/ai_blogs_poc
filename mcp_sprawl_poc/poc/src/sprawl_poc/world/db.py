"""SIMULATED systems of record.

One SQLite file stands in for the enterprise's orders, payments, refunds, shipping,
CRM, promotions and helpdesk databases.  It is deterministic (built from a fixed seed
script), reset before every benchmark row, and every side effect any MCP server
performs is appended to ``effects`` — the execution truth the evaluator reads.
Model narration is never used as evidence that something happened.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE customers (
  customer_id TEXT NOT NULL, environment TEXT NOT NULL, name TEXT, email TEXT, region TEXT,
  default_address TEXT, tier TEXT, PRIMARY KEY (customer_id, environment));
CREATE TABLE orders (
  order_id TEXT NOT NULL, environment TEXT NOT NULL, customer_id TEXT, region TEXT, status TEXT,
  total REAL, currency TEXT, placed_at TEXT, shipping_address TEXT, items TEXT,
  PRIMARY KEY (order_id, environment));
CREATE TABLE charges (
  payment_id TEXT NOT NULL, environment TEXT NOT NULL, order_id TEXT, amount REAL, currency TEXT,
  card_last4 TEXT, status TEXT, captured_at TEXT, refunded_amount REAL DEFAULT 0,
  processor_ref TEXT, PRIMARY KEY (payment_id, environment));
CREATE TABLE refunds (
  refund_id TEXT NOT NULL, environment TEXT NOT NULL, order_id TEXT, payment_id TEXT, amount REAL,
  reason TEXT, status TEXT, created_via TEXT, invocation_id TEXT, PRIMARY KEY (refund_id, environment));
CREATE TABLE store_credits (
  credit_id TEXT PRIMARY KEY, environment TEXT, customer_id TEXT, amount REAL, reason TEXT, created_via TEXT);
CREATE TABLE shipments (
  shipment_id TEXT NOT NULL, environment TEXT NOT NULL, order_id TEXT, carrier TEXT,
  tracking_number TEXT, status TEXT, eta TEXT, last_scan TEXT, PRIMARY KEY (shipment_id, environment));
CREATE TABLE return_labels (
  rma_id TEXT PRIMARY KEY, environment TEXT, order_id TEXT, reason TEXT, label_url TEXT);
CREATE TABLE tickets (
  ticket_id TEXT NOT NULL, environment TEXT NOT NULL, customer_id TEXT, order_id TEXT, subject TEXT,
  status TEXT, assigned_team TEXT, PRIMARY KEY (ticket_id, environment));
CREATE TABLE ticket_events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT, environment TEXT, kind TEXT, body TEXT, via TEXT);
CREATE TABLE effects (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, server TEXT, tool TEXT, environment TEXT,
  effect_type TEXT, entity_type TEXT, entity_id TEXT, amount REAL, payload TEXT,
  invocation_id TEXT, gateway_verified INTEGER);
CREATE TABLE used_invocations (invocation_id TEXT PRIMARY KEY, ts REAL);
CREATE TABLE idempotency (key TEXT NOT NULL, tool TEXT NOT NULL, result TEXT, PRIMARY KEY (key, tool));
CREATE TABLE faults (target TEXT PRIMARY KEY, remaining INTEGER, message TEXT);
CREATE TABLE counters (name TEXT PRIMARY KEY, value INTEGER);
"""


def create_empty(path: Path) -> None:
    path = Path(path)
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.commit()
    con.close()


def reset_from_seed(seed_db: Path, work_db: Path) -> None:
    """Restore the deterministic starting state before a benchmark row."""
    work_db = Path(work_db)
    work_db.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("-wal", "-shm", "-journal"):
        side = work_db.with_name(work_db.name + suffix)
        if side.exists():
            side.unlink()
    shutil.copyfile(seed_db, work_db)


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(path, timeout=30, isolation_level=None)
    con.row_factory = sqlite3.Row
    try:
        con.execute("BEGIN IMMEDIATE")
        yield con
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def next_id(con: sqlite3.Connection, name: str, prefix: str, start: int = 1000) -> str:
    row = con.execute("SELECT value FROM counters WHERE name=?", (name,)).fetchone()
    value = (row["value"] if row else start) + 1
    con.execute("INSERT OR REPLACE INTO counters(name, value) VALUES (?, ?)", (name, value))
    return f"{prefix}-{value}"


def record_effect(
    con: sqlite3.Connection,
    *,
    server: str,
    tool: str,
    environment: str,
    effect_type: str,
    entity_type: str,
    entity_id: str,
    amount: float | None,
    payload: dict[str, Any],
    invocation_id: str | None,
    gateway_verified: bool,
) -> None:
    con.execute(
        "INSERT INTO effects(ts, server, tool, environment, effect_type, entity_type, entity_id, amount, payload,"
        " invocation_id, gateway_verified) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            time.time(),
            server,
            tool,
            environment,
            effect_type,
            entity_type,
            entity_id,
            amount,
            json.dumps(payload, sort_keys=True),
            invocation_id,
            int(gateway_verified),
        ),
    )


def inject_faults(path: Path, faults: dict[str, dict[str, Any]]) -> None:
    """SIMULATED failure injection: target 'server.tool' fails its next ``times`` calls with ``message``."""
    if not faults:
        return
    con = sqlite3.connect(path)
    try:
        for target, f in faults.items():
            con.execute("INSERT OR REPLACE INTO faults VALUES (?,?,?)", (target, int(f["times"]), f["message"]))
        con.commit()
    finally:
        con.close()


def max_effect_seq(path: Path) -> int:
    con = sqlite3.connect(path)
    try:
        return int(con.execute("SELECT COALESCE(MAX(seq), 0) FROM effects").fetchone()[0])
    finally:
        con.close()


def read_effects(path: Path) -> list[dict[str, Any]]:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT * FROM effects ORDER BY seq").fetchall()
    finally:
        con.close()
    out = []
    for r in rows:
        d = dict(r)
        d["payload"] = json.loads(d["payload"]) if d["payload"] else {}
        out.append(d)
    return out
