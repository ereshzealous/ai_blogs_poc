"""What an argument binder asks the platform before a call is allowed to name something.

Two questions matter more than the rest: *is this a real thing* (an order number the model invented is never sent),
and *what does the request mean by "her last order" or "the card she paid with"* (the platform knows; asking the
customer would be asking a question the platform can already answer).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar, Iterator

from store_world.catalog import Catalog, load_catalog


@dataclass(frozen=True)
class Inventory:
    catalog: Catalog

    #: every identifier shape in the store; the shape alone says what kind of thing a name is
    SHAPES: ClassVar[dict[str, re.Pattern[str]]]

    @classmethod
    def from_catalog(cls, catalog: Catalog | None = None) -> Inventory:
        return cls(catalog or load_catalog())

    # -- identity ----------------------------------------------------------------------------------
    def kind(self, identifier: str) -> str | None:
        """What kind of thing this name is, whether or not the store holds it."""
        for kind, shape in self.SHAPES.items():
            if shape.fullmatch(identifier):
                return kind
        return None

    def exists(self, identifier: str) -> bool:
        kind = self.kind(identifier)
        if kind is None:
            return False
        try:
            return identifier in set(self.catalog.identifiers(kind))
        except KeyError:
            return False

    def region(self, identifier: str) -> str | None:
        kind = self.kind(identifier)
        cat = self.catalog
        if kind == "order" and identifier in cat.orders:
            return cat.orders[identifier].region
        if kind == "customer" and identifier in cat.customers:
            return cat.customers[identifier].region
        if kind == "case" and identifier in cat.cases:
            return cat.orders[cat.cases[identifier].order_id].region
        if kind == "shipment":
            for order_id, shipment in cat.shipments.items():
                if shipment.shipment_id == identifier:
                    return cat.orders[order_id].region
        if kind == "staff" and identifier in cat.staff:
            return cat.staff[identifier].region
        return None

    def regions(self) -> tuple[str, ...]:
        return self.catalog.regions

    # -- what the platform knows and the customer should not be asked -------------------------------
    def latest_order(self, customer_id: str) -> str | None:
        orders = self.catalog.orders_of(customer_id)
        return orders[-1].order_id if orders else None

    def original_method(self, order_id: str) -> str | None:
        captures = self.catalog.captures(order_id)
        return captures[0].method_id if captures else None

    def case_of(self, order_id: str) -> str | None:
        return self.catalog.case_by_order.get(order_id)

    def customer_of(self, order_id: str) -> str | None:
        order = self.catalog.orders.get(order_id)
        return order.customer_id if order else None

    def all_identifiers(self) -> Iterator[tuple[str, str]]:
        for kind in self.SHAPES:
            for ident in self.catalog.identifiers(kind):
                yield kind, ident


Inventory.SHAPES = {
    "order": re.compile(r"ORD-\d{4}"),
    "customer": re.compile(r"CUST-\d{4}"),
    "address": re.compile(r"ADDR-\d{4}"),
    "line": re.compile(r"LINE-\d{4}-\d"),
    "payment": re.compile(r"PAY-\d{5}"),
    "capture": re.compile(r"CAP-\d{5}-\d"),
    "refund": re.compile(r"REF-\d{5}-\d"),
    "method": re.compile(r"PM-[A-Z0-9]{6}"),
    "shipment": re.compile(r"SHP-\d{5}"),
    "tracking": re.compile(r"TRK-[A-Z]{2}\d{8}"),
    "rma": re.compile(r"RMA-\d{4}"),
    "sku": re.compile(r"SKU-[A-Z]{2}-\d{4}"),
    "voucher": re.compile(r"VCH-[A-Z0-9]{6}"),
    "credit": re.compile(r"CRD-\d{5}"),
    "case": re.compile(r"CASE-\d{5}"),
    "staff": re.compile(r"STAFF-\d{4}"),
}
