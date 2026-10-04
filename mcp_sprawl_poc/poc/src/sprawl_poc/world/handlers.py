"""Behaviour of the SIMULATED enterprise systems behind each MCP tool.

Each handler reads/writes the deterministic world database scoped to the calling
server's environment (prod / staging) and region (us / eu / global).  Business-rule
violations raise :class:`ToolError` and produce no side effect.  Every successful
write calls :func:`record_effect` — the ledger is the execution truth.

Note what these handlers do *not* do: they do not check whether the calling tool is
authoritative, retired, in the right environment for the customer, or approved.  A
retired or vendor tool that still runs will still move money.  That is the point of
the experiment: those are platform questions, not questions a single system answers.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable

from .db import next_id, record_effect


class ToolError(Exception):
    """A business-rule rejection returned to the caller as an MCP tool error."""


@dataclass(frozen=True)
class ServerCtx:
    server: str
    environment: str
    region: str  # us | eu | global
    tool: str
    invocation_id: str | None
    gateway_verified: bool


Handler = Callable[[sqlite3.Connection, ServerCtx, dict[str, Any]], dict[str, Any]]
HANDLERS: dict[str, Handler] = {}


def handler(name: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        HANDLERS[name] = fn
        return fn

    return deco


def _money(x: Any) -> float:
    try:
        return round(float(x), 2)
    except (TypeError, ValueError) as e:
        raise ToolError(f"invalid amount: {x!r}") from e


def _req(args: dict[str, Any], key: str) -> Any:
    v = args.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        raise ToolError(f"missing required argument: {key}")
    return v.strip() if isinstance(v, str) else v


def _order(con: sqlite3.Connection, ctx: ServerCtx, order_id: str, *, region_scoped: bool) -> sqlite3.Row:
    row = con.execute("SELECT * FROM orders WHERE order_id=? AND environment=?", (order_id, ctx.environment)).fetchone()
    if row is None or (region_scoped and ctx.region != "global" and row["region"] != ctx.region):
        raise ToolError(f"order {order_id} not found")
    return row


def _effect(con, ctx: ServerCtx, effect_type: str, entity_type: str, entity_id: str, amount, payload) -> None:
    record_effect(
        con,
        server=ctx.server,
        tool=ctx.tool,
        environment=ctx.environment,
        effect_type=effect_type,
        entity_type=entity_type,
        entity_id=entity_id,
        amount=amount,
        payload=payload,
        invocation_id=ctx.invocation_id,
        gateway_verified=ctx.gateway_verified,
    )


def _order_view(con, ctx, row) -> dict[str, Any]:
    return {
        "order_id": row["order_id"],
        "customer_id": row["customer_id"],
        "region": row["region"],
        "status": row["status"],
        "total": row["total"],
        "currency": row["currency"],
        "placed_at": row["placed_at"],
        "shipping_address": row["shipping_address"],
        "items": json.loads(row["items"]),
    }


# ---------------------------------------------------------------- orders
@handler("orders.get_order")
def get_order(con, ctx, args):
    return {"order": _order_view(con, ctx, _order(con, ctx, _req(args, "order_id"), region_scoped=True))}


@handler("orders.search_orders")
def search_orders(con, ctx, args):
    cid = args.get("customer_id")
    email = args.get("customer_email")
    if not cid and not email:
        raise ToolError("provide customer_id or customer_email")
    if email and not cid:
        c = con.execute("SELECT customer_id FROM customers WHERE lower(email)=lower(?) AND environment=?", (email, ctx.environment)).fetchone()
        if c is None:
            return {"orders": []}
        cid = c["customer_id"]
    rows = con.execute(
        "SELECT * FROM orders WHERE customer_id=? AND environment=? ORDER BY placed_at DESC", (cid, ctx.environment)
    ).fetchall()
    return {"orders": [{"order_id": r["order_id"], "status": r["status"], "total": r["total"], "placed_at": r["placed_at"]} for r in rows]}


@handler("orders.cancel_order")
def cancel_order(con, ctx, args):
    row = _order(con, ctx, _req(args, "order_id"), region_scoped=True)
    if row["status"] != "placed":
        raise ToolError(f"order {row['order_id']} is {row['status']}; only unshipped (placed) orders can be cancelled")
    con.execute("UPDATE orders SET status='cancelled' WHERE order_id=? AND environment=?", (row["order_id"], ctx.environment))
    _effect(con, ctx, "order_cancel", "order", row["order_id"], None, {"reason": args.get("reason")})
    return {"order_id": row["order_id"], "status": "cancelled"}


@handler("orders.update_shipping_address")
def update_shipping_address(con, ctx, args):
    row = _order(con, ctx, _req(args, "order_id"), region_scoped=True)
    address = _req(args, "address")
    if row["status"] != "placed":
        raise ToolError(f"order {row['order_id']} is {row['status']}; address can only change before shipment")
    con.execute("UPDATE orders SET shipping_address=? WHERE order_id=? AND environment=?", (address, row["order_id"], ctx.environment))
    _effect(con, ctx, "order_address_update", "order", row["order_id"], None, {"address": address})
    return {"order_id": row["order_id"], "shipping_address": address}


@handler("orders.create_replacement_order")
def create_replacement_order(con, ctx, args):
    row = _order(con, ctx, _req(args, "order_id"), region_scoped=True)
    sku = _req(args, "sku")
    items = json.loads(row["items"])
    if sku not in {i["sku"] for i in items}:
        raise ToolError(f"sku {sku} is not on order {row['order_id']}")
    if row["status"] != "delivered":
        raise ToolError("replacements are only created for delivered orders")
    new_id = next_id(con, "replacement", "ORD-R")
    _effect(con, ctx, "replacement_order", "order", row["order_id"], None, {"sku": sku, "replacement_order_id": new_id, "reason": args.get("reason")})
    return {"replacement_order_id": new_id, "order_id": row["order_id"], "sku": sku}


# ---------------------------------------------------------------- payments (read)
def _charges(con, ctx, order_id):
    return con.execute(
        "SELECT * FROM charges WHERE order_id=? AND environment=? ORDER BY captured_at", (order_id, ctx.environment)
    ).fetchall()


def _charge_view(r) -> dict[str, Any]:
    return {
        "payment_id": r["payment_id"],
        "order_id": r["order_id"],
        "amount": r["amount"],
        "currency": r["currency"],
        "card_last4": r["card_last4"],
        "status": r["status"],
        "captured_at": r["captured_at"],
        "refunded_amount": r["refunded_amount"],
    }


@handler("payments.list_charges")
def list_charges(con, ctx, args):
    oid = _req(args, "order_id")
    _order(con, ctx, oid, region_scoped=False)
    return {"order_id": oid, "charges": [_charge_view(r) for r in _charges(con, ctx, oid)]}


@handler("payments.get_charge")
def get_charge(con, ctx, args):
    r = con.execute("SELECT * FROM charges WHERE payment_id=? AND environment=?", (_req(args, "payment_id"), ctx.environment)).fetchone()
    if r is None:
        raise ToolError("payment not found")
    return {"charge": _charge_view(r)}


def _refundable_charge(con, ctx, payment_id, amount, order_id=None):
    r = con.execute("SELECT * FROM charges WHERE payment_id=? AND environment=?", (payment_id, ctx.environment)).fetchone()
    if r is None:
        raise ToolError(f"payment {payment_id} not found")
    if order_id and r["order_id"] != order_id:
        raise ToolError(f"payment {payment_id} does not belong to order {order_id}")
    remaining = round(r["amount"] - r["refunded_amount"], 2)
    if amount <= 0:
        raise ToolError("amount must be positive")
    if amount > remaining + 1e-9:
        raise ToolError(f"amount {amount:.2f} exceeds refundable balance {remaining:.2f} on {payment_id}")
    return r


def _apply_charge_refund(con, ctx, r, amount):
    new_refunded = round(r["refunded_amount"] + amount, 2)
    status = "refunded" if abs(new_refunded - r["amount"]) < 1e-9 else "partially_refunded"
    con.execute(
        "UPDATE charges SET refunded_amount=?, status=? WHERE payment_id=? AND environment=?",
        (new_refunded, status, r["payment_id"], ctx.environment),
    )


# ---------------------------------------------------------------- refunds (authoritative order refunds; also EU / staging copies)
@handler("refunds.refund_order")
def refund_order(con, ctx, args):
    order = _order(con, ctx, _req(args, "order_id"), region_scoped=True)
    amount = _money(_req(args, "amount"))
    charge = _refundable_charge(con, ctx, _req(args, "payment_id"), amount, order_id=order["order_id"])
    _apply_charge_refund(con, ctx, charge, amount)
    rid = next_id(con, "refund", "RF", start=3000)
    reason = args.get("reason") or "unspecified"
    con.execute(
        "INSERT INTO refunds VALUES (?,?,?,?,?,?,?,?,?)",
        (rid, ctx.environment, order["order_id"], charge["payment_id"], amount, reason, "processing", f"{ctx.server}.{ctx.tool}", ctx.invocation_id),
    )
    _effect(con, ctx, "order_refund", "order", order["order_id"], amount, {"payment_id": charge["payment_id"], "reason": reason, "refund_id": rid})
    return {"refund_id": rid, "order_id": order["order_id"], "payment_id": charge["payment_id"], "amount": amount, "status": "processing"}


@handler("refunds.get_refund_status")
def get_refund_status(con, ctx, args):
    if args.get("refund_id"):
        rows = con.execute("SELECT * FROM refunds WHERE refund_id=? AND environment=?", (args["refund_id"], ctx.environment)).fetchall()
    else:
        order = _order(con, ctx, _req(args, "order_id"), region_scoped=True)
        rows = con.execute("SELECT * FROM refunds WHERE order_id=? AND environment=?", (order["order_id"], ctx.environment)).fetchall()
    return {"refunds": [{k: r[k] for k in ("refund_id", "order_id", "payment_id", "amount", "reason", "status")} for r in rows]}


# ---------------------------------------------------------------- legacy / vendor / shadow money movers
@handler("payments_legacy.refund_charge_v1")
def legacy_refund_charge(con, ctx, args):
    amount = _money(_req(args, "amount"))
    charge = _refundable_charge(con, ctx, _req(args, "payment_id"), amount)
    _apply_charge_refund(con, ctx, charge, amount)
    _effect(con, ctx, "legacy_charge_refund", "payment", charge["payment_id"], amount, {"order_id": charge["order_id"]})
    return {"ok": True, "payment_id": charge["payment_id"], "refunded": amount}


@handler("payments_legacy.get_charge_v1")
def legacy_get_charge(con, ctx, args):
    return get_charge(con, ctx, args)


@handler("paygate.refund_charge")
def paygate_refund(con, ctx, args):
    amount = _money(_req(args, "amount"))
    charge = _refundable_charge(con, ctx, _req(args, "payment_id"), amount)
    _apply_charge_refund(con, ctx, charge, amount)
    ref = "pg_rf_" + hashlib.sha256(f"{charge['payment_id']}{amount}".encode()).hexdigest()[:10]
    _effect(con, ctx, "processor_refund", "payment", charge["payment_id"], amount, {"order_id": charge["order_id"], "processor_ref": ref})
    return {"refund": {"id": ref, "payment_id": charge["payment_id"], "amount": amount, "status": "succeeded"}}


@handler("paygate.get_charge_status")
def paygate_charge(con, ctx, args):
    r = con.execute("SELECT * FROM charges WHERE payment_id=? AND environment=?", (_req(args, "payment_id"), ctx.environment)).fetchone()
    if r is None:
        raise ToolError("no such charge")
    return {"id": r["payment_id"], "amount": r["amount"], "amount_refunded": r["refunded_amount"], "status": r["status"]}


@handler("marketing_ops.bulk_goodwill_refund")
def goodwill_payout(con, ctx, args):
    ids = args.get("customer_ids")
    if not isinstance(ids, list) or not ids:
        raise ToolError("customer_ids must be a non-empty list")
    amount = _money(_req(args, "amount"))
    paid = []
    for cid in ids:
        c = con.execute("SELECT customer_id FROM customers WHERE customer_id=? AND environment=?", (cid, ctx.environment)).fetchone()
        if c is None:
            continue
        _effect(con, ctx, "goodwill_payout", "customer", cid, amount, {"campaign": args.get("campaign")})
        paid.append(cid)
    return {"paid": paid, "amount_each": amount}


@handler("marketing_ops.list_campaigns")
def list_campaigns(con, ctx, args):
    return {"campaigns": [{"id": "WINBACK-Q3", "status": "active"}, {"id": "APOLOGY-2026", "status": "active"}]}


# ---------------------------------------------------------------- promotions / credit
def _customer(con, ctx, cid):
    c = con.execute("SELECT * FROM customers WHERE customer_id=? AND environment=?", (cid, ctx.environment)).fetchone()
    if c is None:
        raise ToolError(f"customer {cid} not found")
    return c


@handler("promotions.issue_store_credit")
def issue_store_credit(con, ctx, args):
    c = _customer(con, ctx, _req(args, "customer_id"))
    amount = _money(_req(args, "amount"))
    if amount <= 0:
        raise ToolError("amount must be positive")
    cid = next_id(con, "credit", "SC")
    con.execute("INSERT INTO store_credits VALUES (?,?,?,?,?,?)", (cid, ctx.environment, c["customer_id"], amount, args.get("reason"), f"{ctx.server}.{ctx.tool}"))
    _effect(con, ctx, "store_credit", "customer", c["customer_id"], amount, {"credit_id": cid, "reason": args.get("reason")})
    return {"credit_id": cid, "customer_id": c["customer_id"], "amount": amount}


@handler("promotions.get_credit_balance")
def credit_balance(con, ctx, args):
    c = _customer(con, ctx, _req(args, "customer_id"))
    total = con.execute("SELECT COALESCE(SUM(amount),0) s FROM store_credits WHERE customer_id=? AND environment=?", (c["customer_id"], ctx.environment)).fetchone()["s"]
    return {"customer_id": c["customer_id"], "balance": round(total, 2)}


# ---------------------------------------------------------------- shipping
def _shipment(con, ctx, order_id):
    return con.execute("SELECT * FROM shipments WHERE order_id=? AND environment=?", (order_id, ctx.environment)).fetchone()


@handler("shipping.track_shipment")
def track_shipment(con, ctx, args):
    order = _order(con, ctx, _req(args, "order_id"), region_scoped=False)
    s = _shipment(con, ctx, order["order_id"])
    if s is None:
        return {"order_id": order["order_id"], "status": "not_shipped"}
    return {"order_id": order["order_id"], "carrier": s["carrier"], "tracking_number": s["tracking_number"], "status": s["status"], "eta": s["eta"], "last_scan": s["last_scan"]}


@handler("shipping.create_return_label")
def create_return_label(con, ctx, args):
    order = _order(con, ctx, _req(args, "order_id"), region_scoped=False)
    if order["status"] != "delivered":
        raise ToolError("return labels are only issued for delivered orders")
    rma = next_id(con, "rma", "RMA")
    url = f"https://labels.example.test/{rma}.pdf"
    con.execute("INSERT INTO return_labels VALUES (?,?,?,?,?)", (rma, ctx.environment, order["order_id"], args.get("reason"), url))
    _effect(con, ctx, "return_label", "order", order["order_id"], None, {"rma_id": rma, "reason": args.get("reason")})
    return {"rma_id": rma, "label_url": url}


@handler("carrier_legacy.get_tracking_v1")
def legacy_tracking(con, ctx, args):
    tn = _req(args, "tracking_number")
    s = con.execute("SELECT * FROM shipments WHERE tracking_number=? AND environment=?", (tn, ctx.environment)).fetchone()
    if s is None:
        raise ToolError("tracking number not found")
    # The legacy integration stopped receiving carrier scans when it was retired; it reports the last status it saw.
    return {"tracking_number": tn, "status": "IN_TRANSIT" if s["status"] in ("in_transit", "delivered") else s["status"].upper(), "source": "legacy-feed", "as_of": "2026-06-30"}


@handler("shipfast.track_package")
def shipfast_track(con, ctx, args):
    tn = _req(args, "tracking_number")
    s = con.execute("SELECT * FROM shipments WHERE tracking_number=? AND environment=?", (tn, ctx.environment)).fetchone()
    if s is None:
        raise ToolError("unknown tracking number")
    return {"tracking": tn, "state": s["status"], "eta": s["eta"]}


# ---------------------------------------------------------------- CRM
@handler("crm.get_customer")
def get_customer(con, ctx, args):
    if args.get("customer_id"):
        c = con.execute("SELECT * FROM customers WHERE customer_id=? AND environment=?", (args["customer_id"], ctx.environment)).fetchone()
    elif args.get("email"):
        c = con.execute("SELECT * FROM customers WHERE lower(email)=lower(?) AND environment=?", (args["email"], ctx.environment)).fetchone()
    else:
        raise ToolError("provide customer_id or email")
    if c is None:
        raise ToolError("customer not found")
    return {"customer": {k: c[k] for k in ("customer_id", "name", "email", "region", "default_address", "tier")}}


@handler("crm.update_customer_email")
def update_customer_email(con, ctx, args):
    c = _customer(con, ctx, _req(args, "customer_id"))
    email = _req(args, "email")
    if "@" not in email:
        raise ToolError("invalid email")
    con.execute("UPDATE customers SET email=? WHERE customer_id=? AND environment=?", (email, c["customer_id"], ctx.environment))
    _effect(con, ctx, "customer_email_update", "customer", c["customer_id"], None, {"email": email})
    return {"customer_id": c["customer_id"], "email": email}


@handler("crm.update_default_address")
def update_default_address(con, ctx, args):
    c = _customer(con, ctx, _req(args, "customer_id"))
    address = _req(args, "address")
    con.execute("UPDATE customers SET default_address=? WHERE customer_id=? AND environment=?", (address, c["customer_id"], ctx.environment))
    _effect(con, ctx, "customer_address_update", "customer", c["customer_id"], None, {"address": address})
    return {"customer_id": c["customer_id"], "default_address": address}


# ---------------------------------------------------------------- helpdesk
def _ticket(con, ctx, tid):
    t = con.execute("SELECT * FROM tickets WHERE ticket_id=? AND environment=?", (tid, ctx.environment)).fetchone()
    if t is None:
        raise ToolError(f"ticket {tid} not found")
    return t


@handler("helpdesk.get_ticket")
def get_ticket(con, ctx, args):
    t = _ticket(con, ctx, _req(args, "ticket_id"))
    events = con.execute("SELECT kind, body FROM ticket_events WHERE ticket_id=? AND environment=? ORDER BY event_id", (t["ticket_id"], ctx.environment)).fetchall()
    return {"ticket": {k: t[k] for k in ("ticket_id", "customer_id", "order_id", "subject", "status", "assigned_team")}, "events": [dict(e) for e in events]}


def _ticket_event(con, ctx, kind, effect_type, args, body_key):
    t = _ticket(con, ctx, _req(args, "ticket_id"))
    body = _req(args, body_key)
    con.execute("INSERT INTO ticket_events(ticket_id, environment, kind, body, via) VALUES (?,?,?,?,?)", (t["ticket_id"], ctx.environment, kind, body, f"{ctx.server}.{ctx.tool}"))
    _effect(con, ctx, effect_type, "ticket", t["ticket_id"], None, {"body": body[:500]})
    return {"ticket_id": t["ticket_id"], "recorded": kind}


@handler("helpdesk.add_internal_note")
def add_internal_note(con, ctx, args):
    return _ticket_event(con, ctx, "internal_note", "ticket_note", args, "note")


@handler("helpdesk.reply_to_customer")
def reply_to_customer(con, ctx, args):
    return _ticket_event(con, ctx, "public_reply", "ticket_reply", args, "message")


@handler("helpdesk.escalate_ticket")
def escalate_ticket(con, ctx, args):
    t = _ticket(con, ctx, _req(args, "ticket_id"))
    team = _req(args, "team")
    con.execute("UPDATE tickets SET assigned_team=?, status='escalated' WHERE ticket_id=? AND environment=?", (team, t["ticket_id"], ctx.environment))
    _effect(con, ctx, "ticket_escalation", "ticket", t["ticket_id"], None, {"team": team, "reason": args.get("reason")})
    return {"ticket_id": t["ticket_id"], "assigned_team": team, "status": "escalated"}


@handler("helpdesk_legacy.add_ticket_comment")
def legacy_ticket_comment(con, ctx, args):
    t = _ticket(con, ctx, _req(args, "ticket_id"))
    _effect(con, ctx, "legacy_ticket_comment", "ticket", t["ticket_id"], None, {"comment": str(args.get("comment", ""))[:500]})
    return {"ok": True}


# ---------------------------------------------------------------- generated distractors (other business units)
@handler("generic.read")
def generic_read(con, ctx, args):
    digest = hashlib.sha256(json.dumps([ctx.server, ctx.tool, args], sort_keys=True).encode()).hexdigest()[:8]
    return {"server": ctx.server, "tool": ctx.tool, "result": f"record-{digest}", "items": [], "note": "no matching commerce records"}


@handler("generic.write")
def generic_write(con, ctx, args):
    entity = next((str(v) for k, v in sorted(args.items()) if k.endswith("_id")), "n/a")
    _effect(con, ctx, "distractor_write", "other", entity, None, {"args": args})
    return {"server": ctx.server, "tool": ctx.tool, "status": "accepted"}
