"""What the control plane reads (inventory), what later notes switch on (faults), and the contract doc."""

from __future__ import annotations

from pathlib import Path

from store_world import load_catalog
from store_world.faults import Faults
from store_world.inventory import Inventory

CAT = load_catalog()
INV = Inventory.from_catalog(CAT)


def test_an_identifier_resolves_to_its_kind():
    assert INV.kind("ORD-4917") == "order"
    assert INV.kind("CASE-20871") == "case"
    assert INV.kind("SKU-NC-7781") == "sku"


def test_an_identifier_that_does_not_exist_is_not_invented():
    assert INV.exists("ORD-4917") is True
    assert INV.exists("ORD-9998") is False
    assert INV.kind("ORD-9998") == "order", "the shape is still recognised, so a refusal can say what it was"


def test_every_entity_has_a_region_so_policy_can_judge_a_write():
    assert INV.region("ORD-4917") == "eu"
    assert set(INV.regions()) == {"eu", "us"}


def test_the_binder_can_resolve_her_last_order_from_the_customer():
    customer = CAT.order("ORD-4917").customer_id
    assert INV.latest_order(customer) == "ORD-4917"


def test_the_binder_can_resolve_the_card_she_paid_with():
    assert INV.original_method("ORD-4917") == CAT.captures("ORD-4917")[0].method_id


def test_faults_exist_but_are_off_in_f1():
    faults = Faults.default()
    assert faults.enabled == ()
    assert set(faults.available) == {"payment_timeout", "payment_lost_response", "carrier_down", "duplicate_webhook"}


def test_a_fault_can_be_switched_on_by_a_later_note():
    faults = Faults.default().with_enabled("carrier_down")
    assert faults.is_on("carrier_down") is True
    assert faults.is_on("payment_timeout") is False


def test_the_data_contract_documents_every_entity_the_package_exposes():
    contract = (Path(__file__).resolve().parents[1] / "DATA-CONTRACT.md").read_text(encoding="utf-8")
    for entity in ("customer", "address", "order", "order line", "payment", "capture", "refund", "shipment",
                   "carrier", "delivery option", "stock", "return", "voucher", "store credit", "case", "staff",
                   "policy"):
        assert entity in contract.lower(), f"{entity} is exposed but not in the data contract"
    for fault in Faults.default().available:
        assert fault in contract, f"fault hook {fault} is not documented"
