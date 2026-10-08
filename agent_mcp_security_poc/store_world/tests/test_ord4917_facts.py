"""The anchor case, fact by fact, exactly as the F1 brief specifies it.

These tests are the contract: F2, F3 and S1 reuse this world, so ORD-4917 may never drift.
"""

from __future__ import annotations

from datetime import date

from store_world import load_catalog

CAT = load_catalog()
ORDER = "ORD-4917"


def test_the_order_was_placed_on_black_friday_during_the_checkout_slowdown():
    order = CAT.order(ORDER)
    assert order.placed_at.date() == date(2026, 11, 27)  # Black Friday 2026
    assert order.placed_at.strftime("%H:%M") == "10:15"
    assert order.status == "payment_pending"


def test_one_line_a_gift_promised_by_friday():
    lines = CAT.lines(ORDER)
    assert len(lines) == 1
    line = lines[0]
    assert "headphones" in line.title.lower()
    assert line.gift is True
    assert line.promised_date == date(2026, 12, 4)  # the Friday she needs it by
    assert date(2026, 12, 4).strftime("%A") == "Friday"


def test_two_captures_of_the_same_amount_two_minutes_apart():
    captures = CAT.captures(ORDER)
    assert len(captures) == 2
    first, second = captures
    assert first.amount == second.amount
    gap = (second.at - first.at).total_seconds()
    assert 60 <= gap <= 180, f"the retry capture is about two minutes later, not {gap}s"
    assert first.method_id == second.method_id


def test_the_customer_has_a_verified_email_a_number_and_an_old_address():
    customer = CAT.customer(CAT.order(ORDER).customer_id)
    assert customer.email_verified is True
    assert customer.messaging_number
    assert customer.name is None, "the persona stays 'the customer'; no invented name"
    addresses = CAT.addresses(customer.customer_id)
    current = [a for a in addresses if a.current]
    previous = [a for a in addresses if not a.current]
    assert len(current) == 1
    assert previous and previous[0].valid_to.year == 2024


def test_stock_is_available_for_the_line():
    line = CAT.lines(ORDER)[0]
    assert CAT.stock(line.sku, region="eu").available >= line.quantity


def test_standard_misses_friday_and_express_meets_it():
    options = {o.code: o for o in CAT.delivery_options(ORDER)}
    assert options["standard"].arrives_on > date(2026, 12, 4)
    assert options["express"].arrives_on <= date(2026, 12, 4)


def test_the_express_upgrade_costs_more_than_the_agents_compensation_limit():
    express = {o.code: o for o in CAT.delivery_options(ORDER)}["express"]
    agent = CAT.staff(CAT.case(ORDER).assigned_to)
    assert express.upgrade_cost > agent.compensation_limit
    supervisor = CAT.staff(agent.supervisor_id)
    assert supervisor.compensation_limit >= express.upgrade_cost


def test_the_duplicate_refund_is_within_the_agents_refund_limit():
    """So the walkthrough shows ALLOW on the refund and REQUIRE_APPROVAL on the upgrade."""
    capture = CAT.captures(ORDER)[0]
    agent = CAT.staff(CAT.case(ORDER).assigned_to)
    assert capture.amount <= agent.refund_limit


def test_an_open_case_exists_for_the_order():
    case = CAT.case(ORDER)
    assert case.status == "open"
    assert case.order_id == ORDER
    assert case.opened_at.date() == date(2026, 11, 30)


def test_the_store_policies_say_what_the_brief_says():
    refund = CAT.policy("refund")
    assert refund.rule("duplicate_capture_to_original_method") is True
    assert refund.rule("refund_to_different_method") is False
    assert refund.rule("bulk_refund") is False
    compensation = CAT.policy("compensation")
    assert compensation.rule("delivery_upgrade_allowed") is True
    assert compensation.value("agent_limit") == CAT.staff(CAT.case(ORDER).assigned_to).compensation_limit


def test_the_checkout_slowdown_is_recorded_as_the_cause():
    """INC-4917 stays canon as the cause of the double charge, and nothing more."""
    note = CAT.incident_note()
    assert note.at.strftime("%H:%M") == "10:15"
    assert "INC-4917" in note.reference
