"""Entity resolution and authoritative argument binding.

The model proposes intent ("refund ORD-4917, duplicate charge").  The platform reads the
systems of record (through the gateway, over MCP) and binds the values it already owns:
which charge is the duplicate, how much is refundable, which customer an order belongs
to, which region the entity lives in (and therefore which implementation is
authoritative).  Values that genuinely belong to the requester (a new address, a
partial amount, a goodwill amount) are never invented here.

Binding facts come from current systems of record in this POC — not from agent memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..registry.model import Registry

Reader = Callable[[str, dict[str, Any]], Awaitable[tuple[bool, dict[str, Any] | None, str]]]


@dataclass
class BindResult:
    ok: bool
    implementation: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)
    bound_fields: list[str] = field(default_factory=list)
    dropped_fields: list[str] = field(default_factory=list)
    error: str | None = None
    error_kind: str | None = None  # entity_not_found | no_matching_charge | ambiguous | invalid_value

    def as_record(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "implementation": self.implementation,
            "arguments": self.arguments,
            "facts": self.facts,
            "bound_fields": self.bound_fields,
            "dropped_fields": self.dropped_fields,
            "error": self.error,
            "error_kind": self.error_kind,
        }


def _fail(kind: str, msg: str, facts: dict[str, Any] | None = None) -> BindResult:
    return BindResult(False, error=msg, error_kind=kind, facts=facts or {})


class Binder:
    def __init__(self, registry: Registry, read: Reader, impl_schemas: dict[str, dict[str, Any]]):
        self.registry = registry
        self.read = read
        self.impl_schemas = impl_schemas

    async def _order(self, order_id: str) -> dict[str, Any] | None:
        ok, data, _ = await self.read("orders.get_order", {"order_id": order_id})
        return data["order"] if ok and data else None

    async def _customer(self, **kw: str) -> dict[str, Any] | None:
        ok, data, _ = await self.read("crm.get_customer", kw)
        return data["customer"] if ok and data else None

    async def entity_facts(self, args: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        """Facts about the entity an invocation acts on; returns (facts, missing-entity message)."""
        if args.get("order_id"):
            order = await self._order(str(args["order_id"]))
            if order is None:
                return {"order_id": args["order_id"], "exists": False}, f"order {args['order_id']} does not exist in the orders system of record"
            return {"entity": "order", "order_id": order["order_id"], "region": order["region"], "customer_id": order["customer_id"], "status": order["status"]}, None
        if args.get("customer_id"):
            c = await self._customer(customer_id=str(args["customer_id"]))
            if c is None:
                return {"customer_id": args["customer_id"], "exists": False}, f"customer {args['customer_id']} does not exist in the CRM system of record"
            return {"entity": "customer", "customer_id": c["customer_id"], "region": c["region"]}, None
        return {}, None

    def _filter(self, implementation: str, args: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        props = (self.impl_schemas.get(implementation) or {}).get("properties") or {}
        kept = {k: v for k, v in args.items() if k in props and v is not None}
        return kept, sorted(k for k in args if k not in props)

    async def bind_capability(self, capability: str, model_args: dict[str, Any]) -> BindResult:
        cap = self.registry.capabilities.get(capability)
        if cap is None:
            return _fail("invalid_value", f"unknown capability {capability}")
        ref = cap.authoritative.get("us") or cap.authoritative.get("global") or next(iter(cap.authoritative.values()))
        profile = self.registry.get(ref).binding_profile if self.registry.get(ref) else None
        if profile == "order_refund":
            return await self._bind_order_refund(capability, model_args)
        if profile == "customer_credit":
            return await self._bind_customer_credit(capability, model_args)
        if profile == "customer_entity":
            return await self._bind_customer_entity(capability, model_args)
        if profile == "order_replacement":
            return await self._bind_order_replacement(capability, model_args)
        # order_entity and profile-less capabilities: verify the entity, pick the authoritative implementation.
        facts, missing = await self.entity_facts(model_args)
        if missing:
            return _fail("entity_not_found", missing, facts)
        impl = self.registry.authoritative_for(capability, facts.get("region"))
        if impl is None:
            return _fail("invalid_value", f"no authoritative implementation for {capability} in region {facts.get('region')}", facts)
        args, dropped = self._filter(impl, model_args)
        return BindResult(True, impl, args, facts, [], dropped)

    async def bind_implementation(self, implementation: str, model_args: dict[str, Any]) -> BindResult:
        """Model named a concrete implementation: no value binding, only entity facts for policy."""
        facts, _missing = await self.entity_facts(model_args)
        return BindResult(True, implementation, dict(model_args), facts, [], [])

    # ------------------------------------------------------------------ profiles
    async def _bind_order_refund(self, capability: str, a: dict[str, Any]) -> BindResult:
        if not a.get("order_id"):
            return _fail("invalid_value", "order_id is required to refund an order")
        facts, missing = await self.entity_facts({"order_id": a["order_id"]})
        if missing:
            return _fail("entity_not_found", missing, facts)
        ok, data, err = await self.read("payments.list_charges", {"order_id": facts["order_id"]})
        if not ok or data is None:
            return _fail("invalid_value", f"could not read charges: {err}", facts)
        charges = sorted(data["charges"], key=lambda c: c["captured_at"])
        for c in charges:
            c["refundable"] = round(c["amount"] - c["refunded_amount"], 2)
        facts["charges"] = [{k: c[k] for k in ("payment_id", "amount", "refundable", "captured_at")} for c in charges]
        reason = a.get("reason") or "other"
        bound: list[str] = []
        # Business invariant: a duplicate is a later capture repeating an earlier capture of the same amount.
        dupes = [c for i, c in enumerate(charges) if c["refundable"] > 0 and any(abs(p["amount"] - c["amount"]) < 1e-9 for p in charges[:i])]
        if a.get("payment_id"):
            charge = next((c for c in charges if c["payment_id"] == a["payment_id"]), None)
            if charge is None:
                return _fail("no_matching_charge", f"payment {a['payment_id']} is not a charge on {facts['order_id']}", facts)
            if reason == "duplicate_charge" and charge not in dupes:
                others = ", ".join(c["payment_id"] for c in dupes) or "none refundable"
                return _fail("invalid_value", f"{charge['payment_id']} is not a duplicate capture on {facts['order_id']} "
                                              f"(duplicate captures: {others}); refunding it as duplicate_charge is not allowed", facts)
        elif reason == "duplicate_charge":
            if not dupes:
                return _fail(
                    "no_matching_charge",
                    f"no duplicate charge exists on {facts['order_id']}: it has {len(charges)} capture(s) "
                    + ", ".join(f"{c['payment_id']} {c['amount']:.2f}" for c in charges),
                    facts,
                )
            charge = dupes[-1]
            bound.append("payment_id")
        else:
            refundable = [c for c in charges if c["refundable"] > 0]
            if not refundable:
                return _fail("no_matching_charge", f"nothing left to refund on {facts['order_id']}", facts)
            if len(refundable) > 1:
                return _fail("ambiguous", f"{facts['order_id']} has {len(refundable)} refundable charges; specify which", facts)
            charge = refundable[0]
            bound.append("payment_id")
        if a.get("amount") is not None:
            try:
                amount = round(float(a["amount"]), 2)
            except (TypeError, ValueError):
                return _fail("invalid_value", f"amount {a['amount']!r} is not a number", facts)
            if amount > charge["refundable"] + 1e-9:
                return _fail("invalid_value", f"amount {amount:.2f} exceeds refundable {charge['refundable']:.2f} on {charge['payment_id']}", facts)
            if abs(amount - charge["refundable"]) < 0.005:
                bound.append("amount")  # equals the value on record: platform-owned, not a requester-chosen amount
        else:
            amount = charge["refundable"]
            bound.append("amount")
        impl = self.registry.authoritative_for(capability, facts["region"])
        args = {"order_id": facts["order_id"], "payment_id": charge["payment_id"], "amount": amount, "reason": reason}
        return BindResult(True, impl, args, facts, bound, [])

    async def _bind_order_replacement(self, capability: str, a: dict[str, Any]) -> BindResult:
        if not a.get("order_id"):
            return _fail("invalid_value", "order_id is required")
        order = await self._order(str(a["order_id"]))
        if order is None:
            return _fail("entity_not_found", f"order {a['order_id']} does not exist in the orders system of record", {"order_id": a["order_id"], "exists": False})
        facts = {"entity": "order", "order_id": order["order_id"], "region": order["region"], "customer_id": order["customer_id"], "status": order["status"],
                 "skus": [i["sku"] for i in order["items"]]}
        bound: list[str] = []
        sku = a.get("sku")
        if not sku and len(order["items"]) == 1:
            sku = order["items"][0]["sku"]
            bound.append("sku")  # only one item on the order: the platform knows which one
        elif sku and len(order["items"]) == 1 and sku == order["items"][0]["sku"]:
            bound.append("sku")
        impl = self.registry.authoritative_for(capability, facts["region"])
        args = {"order_id": order["order_id"], **({"sku": sku} if sku else {}), **({"reason": a["reason"]} if a.get("reason") else {})}
        return BindResult(True, impl, args, facts, bound, [])

    async def _bind_customer_credit(self, capability: str, a: dict[str, Any]) -> BindResult:
        bound: list[str] = []
        cid = a.get("customer_id")
        facts: dict[str, Any] = {}
        if not cid and a.get("order_id"):
            facts, missing = await self.entity_facts({"order_id": a["order_id"]})
            if missing:
                return _fail("entity_not_found", missing, facts)
            cid = facts["customer_id"]
            bound.append("customer_id")
        if not cid:
            return _fail("invalid_value", "customer_id or order_id is required")
        cfacts, missing = await self.entity_facts({"customer_id": cid})
        if missing:
            return _fail("entity_not_found", missing, cfacts)
        facts = {**cfacts, **({"via_order": facts.get("order_id")} if facts.get("order_id") else {})}
        impl = self.registry.authoritative_for(capability, facts.get("region"))
        args = {"customer_id": cid}
        for k in ("amount", "reason"):
            if a.get(k) is not None:
                args[k] = a[k]
        return BindResult(True, impl, args, facts, bound, [])

    async def _bind_customer_entity(self, capability: str, a: dict[str, Any]) -> BindResult:
        bound: list[str] = []
        cid = a.get("customer_id")
        if not cid and a.get("lookup_email"):
            c = await self._customer(email=str(a["lookup_email"]))
            if c is None:
                return _fail("entity_not_found", f"no customer with email {a['lookup_email']} in the CRM system of record")
            cid = c["customer_id"]
            bound.append("customer_id")
        if not cid:
            return _fail("invalid_value", "customer_id or lookup_email is required")
        facts, missing = await self.entity_facts({"customer_id": cid})
        if missing:
            return _fail("entity_not_found", missing, facts)
        impl = self.registry.authoritative_for(capability, facts.get("region"))
        rest = {k: v for k, v in a.items() if k not in ("customer_id", "lookup_email")}
        args, dropped = self._filter(impl, {"customer_id": cid, **rest})
        return BindResult(True, impl, args, facts, bound, dropped)
