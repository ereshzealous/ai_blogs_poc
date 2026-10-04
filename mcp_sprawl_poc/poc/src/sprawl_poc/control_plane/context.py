"""Deterministic entity resolution before discovery (control-plane arm).

The platform extracts entity references from the request by shape (order, customer,
payment, ticket ids; email addresses) and resolves each against the systems of record
through the gateway.  The result is a short, factual context block for the model — which
entities exist, their region and state, the charges on an order — so the model does not
have to guess, invent or ask for facts the platform already owns.

No model is involved; nothing here is derived from benchmark labels.  Unknown shapes are
simply not resolved (the model can still use lookup capabilities).
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

Reader = Callable[[str, dict[str, Any]], Awaitable[tuple[bool, dict[str, Any] | None, str]]]

ORDER = re.compile(r"\bORD-\d+\b")
CUSTOMER = re.compile(r"\bCUS-\d+\b")
PAYMENT = re.compile(r"\bPAY-\d+\b")
TICKET = re.compile(r"\bTCK-\d+\b")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
MAX_ENTITIES = 6


async def resolve_entities(request: str, read: Reader) -> dict[str, Any]:
    refs: list[tuple[str, str]] = []
    for kind, rx in (("order", ORDER), ("customer", CUSTOMER), ("payment", PAYMENT), ("ticket", TICKET), ("email", EMAIL)):
        for m in dict.fromkeys(rx.findall(request)):
            refs.append((kind, m))
    refs = refs[:MAX_ENTITIES]
    entities: list[dict[str, Any]] = []
    for kind, ref in refs:
        if kind == "order":
            ok, data, _ = await read("orders.get_order", {"order_id": ref})
            if not ok or not data:
                entities.append({"ref": ref, "type": "order", "exists": False})
                continue
            o = data["order"]
            ent = {"ref": ref, "type": "order", "exists": True, "status": o["status"], "region": o["region"], "currency": o["currency"],
                   "total": o["total"], "customer_id": o["customer_id"], "items": [f"{i['sku']} x{i['qty']} @ {i['unit_price']}" for i in o["items"]]}
            ok, ch, _ = await read("payments.list_charges", {"order_id": ref})
            if ok and ch:
                ent["charges"] = [f"{c['payment_id']} {c['amount']:.2f} {c['currency']} captured {c['captured_at']} refunded {c['refunded_amount']:.2f}" for c in ch["charges"]]
            ok, sh, _ = await read("shipping.track_shipment", {"order_id": ref})
            if ok and sh:
                ent["shipment"] = ", ".join(f"{k}={sh[k]}" for k in ("status", "carrier", "tracking_number", "eta", "last_scan") if sh.get(k))
            refund_impl = "refunds_eu.get_refund_status" if o["region"] == "eu" else "refunds.get_refund_status"
            ok, rf, _ = await read(refund_impl, {"order_id": ref})
            if ok and rf:
                ent["refunds"] = [f"{r['refund_id']} {r['amount']:.2f} {r['status']} ({r['reason']})" for r in rf.get("refunds", [])] or ["none"]
            entities.append(ent)
        elif kind == "customer":
            ok, data, _ = await read("crm.get_customer", {"customer_id": ref})
            entities.append({"ref": ref, "type": "customer", "exists": bool(ok and data),
                             **({"region": data["customer"]["region"], "name": data["customer"]["name"]} if ok and data else {})})
        elif kind == "email":
            ok, data, _ = await read("crm.get_customer", {"email": ref})
            entities.append({"ref": ref, "type": "customer email", "exists": bool(ok and data),
                             **({"customer_id": data["customer"]["customer_id"], "region": data["customer"]["region"]} if ok and data else {})})
        elif kind == "payment":
            ok, data, _ = await read("payments.get_charge", {"payment_id": ref})
            entities.append({"ref": ref, "type": "payment", "exists": bool(ok and data),
                             **({"order_id": data["charge"]["order_id"], "amount": data["charge"]["amount"], "refunded": data["charge"]["refunded_amount"]} if ok and data else {})})
        elif kind == "ticket":
            ok, data, _ = await read("helpdesk.get_ticket", {"ticket_id": ref})
            entities.append({"ref": ref, "type": "ticket", "exists": bool(ok and data),
                             **({"order_id": data["ticket"]["order_id"], "status": data["ticket"]["status"]} if ok and data else {})})
    return {"entities": entities}


def render_context(ctx: dict[str, Any]) -> str | None:
    ents = ctx.get("entities") or []
    if not ents:
        return None
    lines = ["Platform context (read from systems of record just now; authoritative):"]
    for e in ents:
        if not e["exists"]:
            lines.append(f"- {e['ref']} ({e['type']}): DOES NOT EXIST in the system of record.")
            continue
        detail = ", ".join(f"{k}={v}" for k, v in e.items() if k not in ("ref", "type", "exists", "charges", "items", "shipment", "refunds"))
        lines.append(f"- {e['ref']} ({e['type']}): {detail}")
        if e.get("items"):
            lines.append(f"    items: {'; '.join(e['items'])}")
        for c in e.get("charges", []):
            lines.append(f"    charge: {c}")
        if e.get("shipment"):
            lines.append(f"    shipment: {e['shipment']}")
        if e.get("refunds"):
            lines.append(f"    refunds: {'; '.join(e['refunds'])}")
    return "\n".join(lines)
