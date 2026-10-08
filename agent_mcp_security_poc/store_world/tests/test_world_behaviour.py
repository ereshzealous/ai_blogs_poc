"""What the world does when something is executed against it: refunds, upgrades, replies, state.

The control plane decides whether a call may run; this package decides what happens when it does, and
each run's side effects are isolated by run id.
"""

from __future__ import annotations

from datetime import date

import pytest

from store_world import StoreWorld, load_catalog

CAT = load_catalog()
ORDER = "ORD-4917"


@pytest.fixture()
def world(tmp_path):
    return StoreWorld(run_id="t-1", db_path=tmp_path / "w.sqlite")


def test_the_order_starts_payment_pending_with_a_duplicate_capture(world):
    assert world.order_status(ORDER) == "payment_pending"
    assert world.duplicate_capture(ORDER) is not None


def test_refunding_the_duplicate_clears_it_and_settles_the_order(world):
    duplicate = world.duplicate_capture(ORDER)
    world.refund_order(ORDER, amount=duplicate.amount, method_id=duplicate.method_id,
                       idempotency_key="k1", actor="STAFF-2210")
    assert world.refunded_total(ORDER) == duplicate.amount
    assert world.duplicate_capture(ORDER) is None
    assert world.order_status(ORDER) == "paid"


def test_the_same_idempotency_key_never_refunds_twice(world):
    duplicate = world.duplicate_capture(ORDER)
    for _ in range(3):
        world.refund_order(ORDER, amount=duplicate.amount, method_id=duplicate.method_id,
                           idempotency_key="k1", actor="STAFF-2210")
    assert world.refunded_total(ORDER) == duplicate.amount
    assert len(world.refunds(ORDER)) == 1


def test_a_refund_to_a_different_method_is_rejected_by_the_world_too(world):
    """Policy denies it first; the world refuses as well, so a bug cannot move money elsewhere."""
    duplicate = world.duplicate_capture(ORDER)
    with pytest.raises(ValueError, match="original payment method"):
        world.refund_order(ORDER, amount=duplicate.amount, method_id="PM-OTHER",
                           idempotency_key="k2", actor="STAFF-2210")


def test_refunding_more_than_was_captured_is_refused(world):
    duplicate = world.duplicate_capture(ORDER)
    with pytest.raises(ValueError, match="captured"):
        world.refund_order(ORDER, amount=duplicate.amount * 10, method_id=duplicate.method_id,
                           idempotency_key="k3", actor="STAFF-2210")


def test_upgrading_to_express_makes_the_promise(world):
    assert world.eta(ORDER) > date(2026, 12, 4)
    world.upgrade_delivery(ORDER, option="express", actor="STAFF-1004")
    assert world.eta(ORDER) <= date(2026, 12, 4)


def test_the_address_can_be_changed_before_dispatch_and_not_after(world):
    new_address = CAT.addresses(CAT.order(ORDER).customer_id)[0].address_id
    world.change_order_address(ORDER, address_id=new_address, actor="STAFF-2210")
    world.dispatch(ORDER)
    with pytest.raises(ValueError, match="dispatched"):
        world.change_order_address(ORDER, address_id=new_address, actor="STAFF-2210")


def test_after_dispatch_the_carrier_redirect_is_the_one_that_works(world):
    world.dispatch(ORDER)
    shipment = world.shipment(ORDER)
    world.redirect_parcel(shipment.shipment_id, address_id=CAT.addresses(CAT.order(ORDER).customer_id)[0].address_id)
    assert world.shipment(ORDER).redirected is True


def test_a_reply_on_the_case_is_recorded_against_the_case(world):
    world.reply_on_case(CAT.case(ORDER).case_id, text="Your duplicate charge has been refunded.", actor="STAFF-2210")
    case = world.case(CAT.case(ORDER).case_id)
    assert len(case.replies) == 1
    assert case.replies[0].channel == "case"


def test_runs_do_not_see_each_others_side_effects(tmp_path):
    a = StoreWorld(run_id="a", db_path=tmp_path / "w.sqlite")
    b = StoreWorld(run_id="b", db_path=tmp_path / "w.sqlite")
    duplicate = a.duplicate_capture(ORDER)
    a.refund_order(ORDER, amount=duplicate.amount, method_id=duplicate.method_id, idempotency_key="k", actor="STAFF-2210")
    assert a.refunded_total(ORDER) == duplicate.amount
    assert b.refunded_total(ORDER) == 0
    assert b.order_status(ORDER) == "payment_pending"


def test_every_execution_is_an_event_with_an_actor(world):
    duplicate = world.duplicate_capture(ORDER)
    world.refund_order(ORDER, amount=duplicate.amount, method_id=duplicate.method_id,
                       idempotency_key="k1", actor="STAFF-2210")
    events = world.events()
    assert [e["kind"] for e in events] == ["refund"]
    assert events[0]["payload"]["actor"] == "STAFF-2210"
