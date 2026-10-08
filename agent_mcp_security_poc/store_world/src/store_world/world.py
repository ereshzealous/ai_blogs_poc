"""What happens when something is actually executed against the store.

State is the catalog plus this run's events, and nothing else. Two runs against the same database never see each
other, so a benchmark can execute real writes 200 times without resetting anything. The clock is simulated: an event
happens one minute after the last one, starting from the scenario's session start, so a replay is reproducible.

The invariants here are the world's own, not the control plane's. Policy decides whether a call may run; these rules
decide what the store will accept even if something went wrong upstream: never more than was captured, never to a
different card, never twice for the same idempotency key, and no address change after dispatch.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from store_world.catalog import Catalog, load_catalog
from store_world.model import Capture, Case, Refund, Reply, Shipment

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
"""

# STORE_WORLD_DB lets a host isolate a run's side effects; the gateway passes it to every server process, so the
# servers, the scorer and anything reading state afterwards agree on one database.
_DEFAULT_DB = Path(os.environ.get("STORE_WORLD_DB",
                                  Path(__file__).resolve().parents[2] / ".cache" / "store-world.sqlite"))


def _round(amount: float) -> float:
    return round(amount + 1e-9, 2)


class StoreWorld:
    """One run's view of Northwind Goods."""

    _lock = threading.Lock()

    def __init__(self, run_id: str, db_path: str | Path | None = None, catalog: Catalog | None = None):
        self.run_id = run_id
        self.catalog = catalog or load_catalog()
        self.db_path = Path(db_path or _DEFAULT_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_SCHEMA)

    # -- events ------------------------------------------------------------------------------------
    def events(self, kind: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT seq, at, kind, payload FROM events WHERE run_id = ?"
        args: list[Any] = [self.run_id]
        if kind:
            q += " AND kind = ?"
            args.append(kind)
        rows = self._conn.execute(q + " ORDER BY seq", args).fetchall()
        return [{"seq": s, "at": at, "kind": k, "payload": json.loads(p)} for s, at, k, p in rows]

    def _record(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            seq = self._conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE run_id = ?",
                                     (self.run_id,)).fetchone()[0]
            at = self.catalog.session_start + timedelta(minutes=seq)
            self._conn.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                               (self.run_id, seq, at.strftime("%Y-%m-%dT%H:%M:%SZ"), kind,
                                json.dumps(payload, sort_keys=True)))
        return {"seq": seq, "at": at, "kind": kind, **payload}

    def reset(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM events WHERE run_id = ?", (self.run_id,))

    def _seen(self, kind: str, idempotency_key: str) -> dict[str, Any] | None:
        for e in self.events(kind):
            if e["payload"].get("idempotency_key") == idempotency_key:
                return e
        return None

    # -- payments ----------------------------------------------------------------------------------
    def captured_total(self, order_id: str) -> float:
        return _round(sum(c.amount for c in self.catalog.captures(order_id)))

    def refunded_total(self, order_id: str) -> float:
        return _round(sum(e["payload"]["amount"] for e in self.events("refund")
                          if e["payload"]["order_id"] == order_id))

    def refunds(self, order_id: str) -> list[Refund]:
        out = []
        for e in self.events("refund"):
            p = e["payload"]
            if p["order_id"] != order_id:
                continue
            out.append(Refund(refund_id=p["refund_id"], payment_id=p["payment_id"], order_id=order_id,
                              amount=p["amount"], at=datetime.fromisoformat(e["at"].replace("Z", "+00:00")),
                              method_id=p["method_id"], idempotency_key=p["idempotency_key"], actor=p["actor"]))
        return out

    def duplicate_capture(self, order_id: str) -> Capture | None:
        """The capture that should not have happened, while it is still outstanding."""
        order = self.catalog.order(order_id)
        captures = self.catalog.captures(order_id)
        over = _round(self.captured_total(order_id) - order.total)
        if over <= 0 or self.refunded_total(order_id) >= over:
            return None
        return captures[-1]

    def refund_order(self, order_id: str, amount: float, method_id: str, idempotency_key: str, actor: str) -> Refund:
        """The authoritative refund: order level, original method only, at most what was captured, once per key."""
        order = self.catalog.order(order_id)
        payment = self.catalog.payment(order_id)
        seen = self._seen("refund", idempotency_key)
        if seen:
            return next(r for r in self.refunds(order_id) if r.idempotency_key == idempotency_key)
        if method_id != payment.method_id:
            raise ValueError(f"a refund goes to the original payment method ({payment.method_id}), not {method_id}")
        outstanding = _round(self.captured_total(order_id) - self.refunded_total(order_id))
        if _round(amount) > outstanding:
            raise ValueError(f"{amount} exceeds what was captured and not yet refunded ({outstanding})")
        refund_id = f"{payment.payment_id.replace('PAY', 'REF')}-{len(self.refunds(order_id)) + 1}"
        self._record("refund", {"refund_id": refund_id, "order_id": order_id, "payment_id": payment.payment_id,
                                "amount": _round(amount), "method_id": method_id,
                                "idempotency_key": idempotency_key, "actor": actor})
        return self.refunds(order_id)[-1]

    # -- fulfilment --------------------------------------------------------------------------------
    def order_status(self, order_id: str) -> str:
        order = self.catalog.order(order_id)
        status = order.status
        if status == "payment_pending" and self.duplicate_capture(order_id) is None \
                and self.captured_total(order_id) >= order.total:
            status = "paid"
        if any(e["payload"]["order_id"] == order_id for e in self.events("dispatch")):
            status = "dispatched"
        if _round(self.refunded_total(order_id)) >= _round(self.captured_total(order_id)) and self.captured_total(order_id) > 0:
            status = "refunded"
        return status

    def delivery_option(self, order_id: str) -> str:
        option = self.catalog.order(order_id).delivery_option
        for e in self.events("delivery_upgrade"):
            if e["payload"]["order_id"] == order_id:
                option = e["payload"]["option"]
        return option

    def eta(self, order_id: str) -> date:
        code = self.delivery_option(order_id)
        for option in self.catalog.delivery_options(order_id):
            if option.code == code:
                return option.arrives_on
        raise KeyError(f"{order_id} has no delivery option {code!r}")

    def upgrade_delivery(self, order_id: str, option: str, actor: str) -> dict[str, Any]:
        codes = {o.code: o for o in self.catalog.delivery_options(order_id)}
        if option not in codes:
            raise ValueError(f"{order_id} has no delivery option {option!r}")
        if self.shipment(order_id).state != "not_dispatched":
            raise ValueError(f"{order_id} has already been dispatched; the carrier decides from here")
        return self._record("delivery_upgrade", {"order_id": order_id, "option": option,
                                                 "cost": codes[option].upgrade_cost, "actor": actor})

    def dispatch(self, order_id: str) -> dict[str, Any]:
        return self._record("dispatch", {"order_id": order_id})

    def shipment(self, order_id: str) -> Shipment:
        base = self.catalog.shipment(order_id)
        state, redirected = base.state, base.redirected
        for e in self.events():
            p = e["payload"]
            if e["kind"] == "dispatch" and p.get("order_id") == order_id:
                state = "dispatched"
            if e["kind"] == "redirect" and p.get("shipment_id") == base.shipment_id:
                redirected = True
        return Shipment(shipment_id=base.shipment_id, order_id=order_id, carrier=base.carrier,
                        tracking=base.tracking, state=state, redirected=redirected)

    def change_order_address(self, order_id: str, address_id: str, actor: str) -> dict[str, Any]:
        """Only before dispatch. Afterwards the carrier redirect is the capability that works."""
        if self.shipment(order_id).state != "not_dispatched":
            raise ValueError(f"{order_id} has already been dispatched; ask the carrier to redirect the parcel")
        customer = self.catalog.order(order_id).customer_id
        if address_id not in {a.address_id for a in self.catalog.addresses(customer)}:
            raise ValueError(f"{address_id} is not an address of {customer}")
        return self._record("address_change", {"order_id": order_id, "address_id": address_id, "actor": actor})

    def shipping_address(self, order_id: str) -> str:
        address = self.catalog.order(order_id).shipping_address_id
        for e in self.events("address_change"):
            if e["payload"]["order_id"] == order_id:
                address = e["payload"]["address_id"]
        return address

    def redirect_parcel(self, shipment_id: str, address_id: str, actor: str = "carrier") -> dict[str, Any]:
        order_id = next((o for o, s in self.catalog.shipments.items() if s.shipment_id == shipment_id), None)
        if order_id is None:
            raise ValueError(f"no shipment {shipment_id}")
        if self.shipment(order_id).state == "not_dispatched":
            raise ValueError(f"{shipment_id} has not been dispatched; change the order address instead")
        return self._record("redirect", {"shipment_id": shipment_id, "order_id": order_id,
                                         "address_id": address_id, "actor": actor})

    # -- customer contact --------------------------------------------------------------------------
    def reply_on_case(self, case_id: str, text: str, actor: str) -> dict[str, Any]:
        """The authoritative way to reach the customer: it is recorded against the case."""
        self.catalog.case(case_id)
        return self._record("case_reply", {"case_id": case_id, "text": text, "actor": actor, "channel": "case"})

    def send_message(self, case_id: str, text: str, actor: str, channel: str) -> dict[str, Any]:
        if channel not in ("email", "sms", "messaging"):
            raise ValueError(f"unknown channel {channel!r}")
        return self._record("message", {"case_id": case_id, "text": text, "actor": actor, "channel": channel})

    def case(self, case_id: str) -> Case:
        base = self.catalog.case(case_id)
        replies = list(base.replies)
        for e in self.events():
            p = e["payload"]
            if e["kind"] in ("case_reply", "message") and p.get("case_id") == base.case_id:
                replies.append(Reply(at=datetime.fromisoformat(e["at"].replace("Z", "+00:00")),
                                     channel=p["channel"], text=p["text"], actor=p["actor"]))
        return Case(case_id=base.case_id, order_id=base.order_id, customer_id=base.customer_id, status=base.status,
                    opened_at=base.opened_at, assigned_to=base.assigned_to, subject=base.subject,
                    replies=tuple(replies))

    # -- compensation ------------------------------------------------------------------------------
    def issue_store_credit(self, customer_id: str, value: float, reason: str, actor: str) -> dict[str, Any]:
        """Compensation, which is a different capability from a refund."""
        self.catalog.customer(customer_id)
        return self._record("store_credit", {"customer_id": customer_id, "value": _round(value),
                                             "reason": reason, "actor": actor})


class StoreWorlds:
    """One object per process, one StoreWorld per run id.

    The MCP runtime holds a single world for the whole server process and passes the run id with every call, so the
    façade keeps the per-run instances and exposes the same `now(run_id)` / `record(run_id, ...)` shape the ops world
    uses. Handlers ask for `worlds.for_run(run_id)` and then use the ordinary StoreWorld API.
    """

    def __init__(self, db_path: str | Path | None = None, catalog: Catalog | None = None):
        self.db_path = db_path
        self.catalog = catalog or load_catalog()
        self._runs: dict[str, StoreWorld] = {}

    def for_run(self, run_id: str) -> StoreWorld:
        if run_id not in self._runs:
            self._runs[run_id] = StoreWorld(run_id, db_path=self.db_path, catalog=self.catalog)
        return self._runs[run_id]

    def now(self, run_id: str) -> datetime:
        world = self.for_run(run_id)
        return self.catalog.session_start + timedelta(minutes=len(world.events()))

    def record(self, run_id: str, server: str, tool: str, kind: str, payload: dict[str, Any],
               advance_minutes: int = 0) -> dict[str, Any]:
        return self.for_run(run_id)._record(kind, {**payload, "server": server, "tool": tool})

    def events(self, run_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        return self.for_run(run_id).events(kind)

    def reset(self, run_id: str) -> None:
        self.for_run(run_id).reset()
