"""The world is deterministic, seeded and big enough to hide ORD-4917 in."""

from __future__ import annotations

import re

from store_world import SEED, catalog_digest, load_catalog
from store_world.inventory import Inventory

CAT = load_catalog()


def test_the_seed_is_4917():
    assert SEED == 4917


def test_two_builds_are_identical():
    a, b = load_catalog(fresh=True), load_catalog(fresh=True)
    assert catalog_digest(a) == catalog_digest(b)


def test_the_digest_is_stable_across_processes():
    """A hash written into a frozen run config must not move when the process restarts."""
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-c", "from store_world import load_catalog, catalog_digest; print(catalog_digest(load_catalog()))"],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == catalog_digest(CAT)


def test_the_store_is_populated_enough_that_one_order_is_not_obvious():
    assert len(CAT.orders) >= 200
    assert len(CAT.customers) >= 80
    assert sum(1 for o in CAT.orders.values() if o.status == "payment_pending") >= 3, \
        "ORD-4917 must not be the only order in its state"


def test_every_identifier_follows_its_declared_shape():
    shapes = {
        "order": r"ORD-\d{4}", "customer": r"CUST-\d{4}", "address": r"ADDR-\d{4}",
        "payment": r"PAY-\d{5}", "capture": r"CAP-\d{5}-\d", "refund": r"REF-\d{5}-\d",
        "shipment": r"SHP-\d{5}", "tracking": r"TRK-[A-Z]{2}\d{8}", "case": r"CASE-\d{5}",
        "rma": r"RMA-\d{4}", "sku": r"SKU-[A-Z]{2}-\d{4}", "voucher": r"VCH-[A-Z0-9]{6}",
        "credit": r"CRD-\d{5}", "staff": r"STAFF-\d{4}",
    }
    assert set(shapes) <= set(Inventory.SHAPES), "every shape the world uses is declared for the binder"
    for kind, pattern in shapes.items():
        for ident in CAT.identifiers(kind):
            assert re.fullmatch(pattern, ident), f"{kind} id {ident} does not match {pattern}"


def test_no_real_brand_appears_anywhere():
    """Carriers, processors and vendors are invented; real retailers never appear in the data."""
    text = CAT.as_text().lower()
    for brand in ("amazon", "ebay", "shopify", "stripe", "paypal", "dhl", "fedex", "ups ", "royal mail",
                  "klarna", "adyen", "zalando", "walmart", "target", "asos", "etsy"):
        assert brand not in text, f"real brand {brand!r} leaked into the world"


def test_the_store_is_named_consistently():
    assert CAT.store_name == "Northwind Goods"
