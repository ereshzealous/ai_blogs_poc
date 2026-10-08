"""Builds the store as it stands before anyone acts: seed 4917, no randomness that is not seeded, no network.

The anchor case is stated once, in data/ord-4917/seed.yaml. Everything else is generated around it, so ORD-4917 is
one order among hundreds rather than the only thing in the world.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml

from store_world.model import (Address, Capture, Carrier, Case, Customer, DeliveryOption, IncidentNote, Order,
                               OrderLine, Payment, Policy, Product, Return, Shipment, Staff, Stock, StoreCredit,
                               Voucher)

SEED = 4917
SEED_FILE = Path(__file__).resolve().parents[2] / "data" / "ord-4917" / "seed.yaml"

_STATUSES = ("paid", "paid", "paid", "dispatched", "dispatched", "delivered", "delivered", "delivered",
             "cancelled", "payment_pending")
_CITIES = (("Utrecht", "NL"), ("Ghent", "BE"), ("Lyon", "FR"), ("Porto", "PT"), ("Aarhus", "DK"),
           ("Leipzig", "DE"), ("Cork", "IE"), ("Tampere", "FI"), ("Austin", "US"), ("Portland", "US"),
           ("Madison", "US"), ("Asheville", "US"))
_STREETS = ("Kanaalstraat", "Lange Nieuwstraat", "Rue Bellecour", "Rua do Almada", "Vestergade", "Karl-Heine-Strasse",
            "Barrack Street", "Hämeenkatu", "Burnet Road", "Alberta Street", "Willy Street", "Haywood Road")
_REASONS = ("does not fit", "arrived damaged", "changed mind", "wrong item sent", "duplicate order")


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _d(value: str) -> date:
    return date.fromisoformat(value)


class Catalog:
    """The static store. Nothing here changes; a run's changes live in StoreWorld's event log."""

    def __init__(self, raw: dict[str, Any]):
        self.raw = raw
        store = raw["store"]
        self.store_name: str = store["name"]
        self.currency: str = store["currency"]
        self.regions: tuple[str, ...] = tuple(store["regions"])
        self.processor: str = store["processor"]
        self.warehouses: dict[str, str] = dict(store["warehouses"])
        self.calendar = {k: v for k, v in raw["calendar"].items()}
        self.session_start = _dt(raw["calendar"]["session_start"])

        self.products: dict[str, Product] = {p["sku"]: Product(**p) for p in raw["products"]}
        self.carriers: dict[str, Carrier] = {
            c["code"]: Carrier(code=c["code"], name=c["name"], regions=tuple(c["regions"]),
                               cutoff_hour=c["cutoff_hour"], working_days=tuple(c["working_days"]))
            for c in raw["carriers"]}
        self.staff_rows: dict[str, Staff] = {
            s["staff_id"]: Staff(staff_id=s["staff_id"], role=s["role"], region=s["region"],
                                 refund_limit=s["refund_limit"], compensation_limit=s["compensation_limit"],
                                 supervisor_id=s["supervisor_id"], scopes=tuple(s["scopes"]))
            for s in raw["staff"]}
        self.policies: dict[str, Policy] = {
            name: Policy(name=name, version=p["version"], rules=dict(p["rules"]), values=dict(p["values"]))
            for name, p in raw["policies"].items()}

        self.customers: dict[str, Customer] = {}
        self.addresses_by_customer: dict[str, list[Address]] = {}
        self.orders: dict[str, Order] = {}
        self.lines_by_order: dict[str, list[OrderLine]] = {}
        self.payments: dict[str, Payment] = {}          # by order id
        self.captures_by_order: dict[str, list[Capture]] = {}
        self.shipments: dict[str, Shipment] = {}        # by order id
        self.delivery_by_order: dict[str, list[DeliveryOption]] = {}
        self.cases: dict[str, Case] = {}                # by case id
        self.case_by_order: dict[str, str] = {}
        self.stock_rows: dict[tuple[str, str], Stock] = {}
        self.returns: dict[str, Return] = {}
        self.vouchers: dict[str, Voucher] = {}
        self.credits: dict[str, StoreCredit] = {}

        self._build_anchor(raw["anchor"])
        self._build_rest()

    # -- the anchor case -------------------------------------------------------------------------
    def _build_anchor(self, a: dict[str, Any]) -> None:
        c = a["customer"]
        self.customers[c["customer_id"]] = Customer(customer_id=c["customer_id"], email=c["email"],
                                                    email_verified=c["email_verified"],
                                                    messaging_number=c["messaging_number"], region=c["region"],
                                                    since=_d(c["since"]))
        self.addresses_by_customer[c["customer_id"]] = [
            Address(address_id=x["address_id"], customer_id=c["customer_id"], line1=x["line1"], city=x["city"],
                    postcode=x["postcode"], country=x["country"], current=x["current"],
                    valid_from=_d(x["valid_from"]), valid_to=_d(x["valid_to"]) if x["valid_to"] else None)
            for x in a["addresses"]]

        o = a["order"]
        order_id = o["order_id"]
        self.orders[order_id] = Order(order_id=order_id, customer_id=c["customer_id"], placed_at=_dt(o["placed_at"]),
                                      status=o["status"], region=o["region"], total=o["total"],
                                      currency=self.currency, shipping_address_id=o["shipping_address_id"],
                                      delivery_option=o["delivery_option"])
        ln = a["line"]
        self.lines_by_order[order_id] = [OrderLine(line_id=ln["line_id"], order_id=order_id, sku=ln["sku"],
                                                   title=ln["title"], quantity=ln["quantity"],
                                                   unit_price=ln["unit_price"], gift=ln["gift"],
                                                   promised_date=_d(ln["promised_date"]))]
        p = a["payment"]
        self.payments[order_id] = Payment(payment_id=p["payment_id"], order_id=order_id, method_id=p["method_id"],
                                          method_label=p["method_label"], authorized=p["authorized"],
                                          currency=self.currency)
        self.captures_by_order[order_id] = [
            Capture(capture_id=x["capture_id"], payment_id=p["payment_id"], order_id=order_id, amount=x["amount"],
                    at=_dt(x["at"]), method_id=p["method_id"], idempotency_key=x["idempotency_key"])
            for x in a["captures"]]

        s = a["shipment"]
        self.shipments[order_id] = Shipment(shipment_id=s["shipment_id"], order_id=order_id, carrier=s["carrier"],
                                            tracking=s["tracking"])
        self.delivery_by_order[order_id] = [
            DeliveryOption(code=x["code"], price=x["price"], upgrade_cost=x["upgrade_cost"],
                           arrives_on=_d(x["arrives_on"]), cutoff_at=_dt(x["cutoff_at"]))
            for x in a["delivery_options"]]

        k = a["case"]
        self.cases[k["case_id"]] = Case(case_id=k["case_id"], order_id=order_id, customer_id=c["customer_id"],
                                        status=k["status"], opened_at=_dt(k["opened_at"]),
                                        assigned_to=k["assigned_to"], subject=k["subject"])
        self.case_by_order[order_id] = k["case_id"]

        st = a["stock"]
        self.stock_rows[(st["sku"], st["region"])] = Stock(**st)

        self.anchor_order_id = order_id
        self.anchor_customer_id = c["customer_id"]
        n = a["incident_note"]
        self._incident_note = IncidentNote(at=_dt(n["at"]), reference=n["reference"], summary=n["summary"])

    # -- the rest of the store -------------------------------------------------------------------
    def _build_rest(self) -> None:
        rnd = random.Random(SEED)
        skus = sorted(self.products)
        carrier_codes = sorted(self.carriers)
        reserved_addresses = {a.address_id for rows in self.addresses_by_customer.values() for a in rows}

        # customers CUST-1000..CUST-1089, the anchor keeping its own id
        addr_seq = 1000
        for i in range(90):
            cid = f"CUST-{1000 + i}"
            if cid in self.customers:
                continue
            region = "eu" if i % 3 else "us"
            self.customers[cid] = Customer(customer_id=cid, email=f"customer{1000 + i}@example.invalid",
                                           email_verified=bool(i % 4), messaging_number=f"+31 6 {10 + i % 80:02d} 00 00 00",
                                           region=region, since=date(2021, 1, 1) + timedelta(days=rnd.randrange(1500)))
            city, country = _CITIES[i % len(_CITIES)]
            while f"ADDR-{addr_seq}" in reserved_addresses:
                addr_seq += 1
            self.addresses_by_customer[cid] = [Address(address_id=f"ADDR-{addr_seq}", customer_id=cid,
                                                       line1=f"{_STREETS[i % len(_STREETS)]} {1 + i % 140}", city=city,
                                                       postcode=f"{1000 + i * 7 % 8999} AB", country=country,
                                                       current=True, valid_from=date(2022, 1, 1))]
            addr_seq += 1

        # orders: 240 in total, the anchor among them
        numbers = sorted({4917, *rnd.sample(range(1000, 10000), 260)})[:240]
        if 4917 not in numbers:                                   # pragma: no cover - sample always leaves room
            numbers = sorted({4917, *numbers[:-1]})
        customers = sorted(self.customers)
        idx = 0
        for n in numbers:
            order_id = f"ORD-{n}"
            if order_id in self.orders:
                continue
            cid = customers[idx % len(customers)]
            customer = self.customers[cid]
            placed = datetime(2026, 11, 1, tzinfo=timezone.utc) + timedelta(hours=rnd.randrange(24 * 29),
                                                                            minutes=rnd.randrange(60))
            if cid == self.anchor_customer_id:
                # she has earlier orders, which is what makes "which of your recent orders" a real question,
                # but ORD-4917 is always her last: the platform can answer that without asking her.
                placed = self.orders[self.anchor_order_id].placed_at - timedelta(days=3 + idx % 40,
                                                                                 hours=rnd.randrange(10))
            status = _STATUSES[idx % len(_STATUSES)]
            sku = skus[idx % len(skus)]
            product = self.products[sku]
            quantity = 1 + idx % 3
            total = round(product.price * quantity, 2)
            address = self.addresses_by_customer[cid][0]
            option = ("standard", "express", "nominated")[idx % 3]
            self.orders[order_id] = Order(order_id=order_id, customer_id=cid, placed_at=placed, status=status,
                                          region=customer.region, total=total, currency=self.currency,
                                          shipping_address_id=address.address_id, delivery_option=option)
            self.lines_by_order[order_id] = [OrderLine(line_id=f"LINE-{n}-1", order_id=order_id, sku=sku,
                                                       title=product.title, quantity=quantity,
                                                       unit_price=product.price, gift=bool(idx % 7 == 0),
                                                       promised_date=(placed + timedelta(days=7)).date())]
            payment_id = f"PAY-{80000 + idx}"
            method = f"PM-{''.join(rnd.choices('ABCDEFGHJKLMNPQRSTUVWXYZ0123456789', k=6))}"
            self.payments[order_id] = Payment(payment_id=payment_id, order_id=order_id, method_id=method,
                                              method_label=f"card ending {1000 + idx % 8999}", authorized=total,
                                              currency=self.currency)
            captured = [] if status == "payment_pending" and idx % 2 else [
                Capture(capture_id=f"{payment_id.replace('PAY', 'CAP')}-1", payment_id=payment_id, order_id=order_id,
                        amount=total, at=placed, method_id=method, idempotency_key=f"chk-{n}-a1")]
            self.captures_by_order[order_id] = captured
            carrier = carrier_codes[idx % len(carrier_codes)]
            self.shipments[order_id] = Shipment(
                shipment_id=f"SHP-{30000 + idx}", order_id=order_id, carrier=carrier,
                tracking=f"TRK-{carrier}{20000000 + idx * 137:08d}",
                state="dispatched" if status in ("dispatched", "delivered") else "not_dispatched")
            self.delivery_by_order[order_id] = self._options_for(placed)
            if idx % 5 == 0:
                case_id = f"CASE-{20000 + idx}"
                if case_id not in self.cases:
                    self.cases[case_id] = Case(case_id=case_id, order_id=order_id, customer_id=cid,
                                               status="closed" if idx % 10 else "open",
                                               opened_at=placed + timedelta(days=2), assigned_to="STAFF-2210",
                                               subject="Where is my order?")
                    self.case_by_order[order_id] = case_id
            if idx % 11 == 0:
                rma = f"RMA-{2000 + idx}"
                self.returns[rma] = Return(rma_id=rma, order_id=order_id, line_id=f"LINE-{n}-1",
                                           reason=_REASONS[idx % len(_REASONS)],
                                           state="requested" if idx % 2 else "received")
            idx += 1

        for i, sku in enumerate(skus):
            for region in self.regions:
                key = (sku, region)
                if key not in self.stock_rows:
                    self.stock_rows[key] = Stock(sku=sku, region=region, available=5 + (i * 13 + len(region)) % 90,
                                                 reserved=i % 5, warehouse=self.warehouses[region])

        for i in range(24):
            code = "".join(rnd.choices("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789", k=6))
            self.vouchers[f"VCH-{code}"] = Voucher(voucher_id=f"VCH-{code}", value=float(5 * (1 + i % 6)),
                                                   expires_on=date(2027, 1, 31), constraints="one per order")
        for i in range(18):
            cid = customers[(i * 5) % len(customers)]
            self.credits[f"CRD-{40000 + i}"] = StoreCredit(credit_id=f"CRD-{40000 + i}", customer_id=cid,
                                                           value=float(10 * (1 + i % 4)),
                                                           issued_at=datetime(2026, 10, 1, tzinfo=timezone.utc)
                                                           + timedelta(days=i), reason="goodwill")

    def _options_for(self, placed: datetime) -> list[DeliveryOption]:
        base = placed.date()
        return [DeliveryOption(code="standard", price=0.0, upgrade_cost=0.0, arrives_on=base + timedelta(days=10),
                               cutoff_at=placed + timedelta(days=5)),
                DeliveryOption(code="express", price=34.0, upgrade_cost=34.0, arrives_on=base + timedelta(days=6),
                               cutoff_at=placed + timedelta(days=4)),
                DeliveryOption(code="nominated", price=12.0, upgrade_cost=12.0, arrives_on=base + timedelta(days=12),
                               cutoff_at=placed + timedelta(days=7))]

    # -- lookups ---------------------------------------------------------------------------------
    def order(self, order_id: str) -> Order:
        return self.orders[order_id]

    def lines(self, order_id: str) -> list[OrderLine]:
        return list(self.lines_by_order.get(order_id, ()))

    def payment(self, order_id: str) -> Payment:
        return self.payments[order_id]

    def captures(self, order_id: str) -> list[Capture]:
        return list(self.captures_by_order.get(order_id, ()))

    def customer(self, customer_id: str) -> Customer:
        return self.customers[customer_id]

    def addresses(self, customer_id: str) -> list[Address]:
        return list(self.addresses_by_customer.get(customer_id, ()))

    def stock(self, sku: str, region: str = "eu") -> Stock:
        return self.stock_rows[(sku, region)]

    def delivery_options(self, order_id: str) -> list[DeliveryOption]:
        return list(self.delivery_by_order.get(order_id, ()))

    def shipment(self, order_id: str) -> Shipment:
        return self.shipments[order_id]

    def case(self, ref: str) -> Case:
        """By case id, or by the order it belongs to."""
        if ref in self.cases:
            return self.cases[ref]
        return self.cases[self.case_by_order[ref]]

    def staff(self, staff_id: str) -> Staff:
        return self.staff_rows[staff_id]

    def policy(self, name: str) -> Policy:
        return self.policies[name]

    def incident_note(self) -> IncidentNote:
        return self._incident_note

    def orders_of(self, customer_id: str) -> list[Order]:
        return sorted((o for o in self.orders.values() if o.customer_id == customer_id), key=lambda o: o.placed_at)

    # -- introspection ---------------------------------------------------------------------------
    def identifiers(self, kind: str) -> Iterable[str]:
        source = {
            "order": self.orders, "customer": self.customers, "payment": {p.payment_id: p for p in self.payments.values()},
            "shipment": {s.shipment_id: s for s in self.shipments.values()}, "case": self.cases,
            "rma": self.returns, "sku": self.products, "voucher": self.vouchers, "credit": self.credits,
            "staff": self.staff_rows, "refund": {},
            "address": {a.address_id: a for rows in self.addresses_by_customer.values() for a in rows},
            "capture": {c.capture_id: c for rows in self.captures_by_order.values() for c in rows},
            "tracking": {s.tracking: s for s in self.shipments.values()},
            "line": {ln.line_id: ln for rows in self.lines_by_order.values() for ln in rows},
        }[kind]
        return sorted(source)

    def as_json(self) -> dict[str, Any]:
        def enc(value: Any) -> Any:
            if isinstance(value, (datetime, date)):
                return value.isoformat()
            if isinstance(value, dict):
                return {str(k): enc(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
            if isinstance(value, (list, tuple)):
                return [enc(v) for v in value]
            if hasattr(value, "__dataclass_fields__"):
                return enc(asdict(value))
            return value

        return enc({
            "store": {"name": self.store_name, "currency": self.currency, "regions": list(self.regions),
                      "processor": self.processor, "warehouses": self.warehouses},
            "customers": self.customers, "addresses": self.addresses_by_customer, "orders": self.orders,
            "lines": self.lines_by_order, "payments": self.payments, "captures": self.captures_by_order,
            "shipments": self.shipments, "delivery": self.delivery_by_order, "cases": self.cases,
            "stock": {f"{sku}|{region}": row for (sku, region), row in self.stock_rows.items()},
            "returns": self.returns, "vouchers": self.vouchers, "credits": self.credits,
            "products": self.products, "carriers": self.carriers, "staff": self.staff_rows,
            "policies": {n: p.as_dict() for n, p in self.policies.items()},
            "incident_note": self._incident_note, "calendar": self.calendar,
        })

    def as_text(self) -> str:
        return json.dumps(self.as_json(), sort_keys=True)


@lru_cache(maxsize=1)
def _cached_catalog() -> Catalog:
    return Catalog(yaml.safe_load(SEED_FILE.read_text(encoding="utf-8")))


def load_catalog(fresh: bool = False) -> Catalog:
    """The store. Cached, because building it is pure; pass fresh=True to prove two builds agree."""
    if fresh:
        return Catalog(yaml.safe_load(SEED_FILE.read_text(encoding="utf-8")))
    return _cached_catalog()


def catalog_digest(catalog: Catalog) -> str:
    """SHA-256 of the whole store, so a run config can pin exactly which world it measured."""
    return hashlib.sha256(catalog.as_text().encode("utf-8")).hexdigest()
