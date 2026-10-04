"""Control plane v2: provenance, entity context, replacement binding, audit-bound finish."""

from __future__ import annotations

import secrets
from pathlib import Path

import anyio
import pytest

from sprawl_poc.agent.loop import ControlPlaneArm
from sprawl_poc.control_plane.approval import ApprovalService
from sprawl_poc.control_plane.audit import AuditLog
from sprawl_poc.control_plane.context import render_context, resolve_entities
from sprawl_poc.control_plane.gateway import Gateway
from sprawl_poc.control_plane.invocation import CallContext
from sprawl_poc.control_plane.provenance import grounded, ungrounded_fields
from sprawl_poc.control_plane.resolve import CapabilityResolver, entity_priors
from sprawl_poc.mcp_host import Estate
from sprawl_poc.registry.model import load_registry
from sprawl_poc.util import DATA_DIR
from sprawl_poc.world.db import read_effects, reset_from_seed
from sprawl_poc.world.seed import SEED_DB, build as build_seed

ESTATE = DATA_DIR / "estates" / "estate-50"


@pytest.mark.parametrize(
    "value,request_text,ok",
    [
        (30, "Refund $30 for the missing candle", True),
        (30.0, "Refund $30.00 for it", True),
        (18.5, "Refund 18.50 EUR for it", True),
        (9.9, "refund 9,90 EUR", True),
        (25, "Refund the order in full", False),
        (5250, "One of the candles on ORD-5250 was missing", False),  # an id is not an amount
        ("22 Harbor Ave, Seattle, WA 98101", "Send it to 22 Harbor Ave, Seattle, WA 98101 instead.", True),
        ("22 Harbor Ave., Seattle WA 98101", "Send it to 22 Harbor Ave, Seattle, WA 98101 instead.", True),
        ("123 New Street, Springfield, IL 62704", "The customer wants to change the delivery address.", False),
        ("maya.c@example.net", "Change the email to maya.c@example.net.", True),
        ("maya.new@example.net", "Change her email please.", False),
    ],
)
def test_grounding(value, request_text, ok):
    assert grounded(value, request_text) is ok


def test_ungrounded_skips_platform_bound_fields():
    assert ungrounded_fields(("amount",), {"amount": 184.2}, ["amount"], "refund the duplicate") == []
    assert ungrounded_fields(("amount",), {"amount": 25}, [], "refund the duplicate") == ["amount"]


def test_entity_priors_direct_beats_implied():
    p = entity_priors(["order"])
    assert p["order"] > p["customer"] > 0


@pytest.fixture()
def world(tmp_path: Path):
    if not SEED_DB.exists():
        build_seed()
    db = tmp_path / "world.db"
    reset_from_seed(SEED_DB, db)
    return db


def _ctx(reg, role="support_t1"):
    return CallContext("REQ-T", "rep:dana", role, reg.roles[role], "support-assistant", reg.agents["support-assistant"], "prod")


async def _session(db: Path, body):
    reg = load_registry(ESTATE / "registry.yaml")
    key = secrets.token_hex(16)
    async with Estate(ESTATE, db, enforce_gateway_token=True, gateway_key=key) as est:
        gw = Gateway(est, reg, AuditLog(db.with_suffix(".audit.jsonl")), ApprovalService(), key)
        resolver = CapabilityResolver(reg, est.tools, "prod")
        surfaced = {c.tool_name: c for c in (resolver.surface(cap, 0, ()) for cap in reg.capabilities) if c}
        return await body(est, gw, reg, surfaced)


def test_invented_address_is_not_executed(world):
    req = "The customer on ORD-5210 wants to change the delivery address."

    async def body(est, gw, reg, surfaced):
        return await gw.handle("order_update_shipping_address", {"order_id": "ORD-5210", "address": "123 New Street, Springfield, IL 62704"}, _ctx(reg), surfaced, req)

    result, trace = anyio.run(lambda: _session(world, body))
    assert result["status"] == "NOT_EXECUTED" and result["stage"] == "provenance"
    assert "needs_clarification" in result["next_step"]
    assert read_effects(world) == []


def test_requester_supplied_address_executes(world):
    req = "ORD-5244 hasn't shipped yet and the customer has moved. Send it to 22 Harbor Ave, Seattle, WA 98101 instead."

    async def body(est, gw, reg, surfaced):
        return await gw.handle("order_update_shipping_address", {"order_id": "ORD-5244", "address": "22 Harbor Ave, Seattle, WA 98101"}, _ctx(reg), surfaced, req)

    result, _ = anyio.run(lambda: _session(world, body))
    assert result["status"] == "EXECUTED"


def test_invented_partial_refund_amount_is_not_executed_but_amount_on_record_is(world):
    async def body(est, gw, reg, surfaced):
        a, _ = await gw.handle("order_refund", {"order_id": "ORD-5160", "reason": "item_not_received", "amount": 50}, _ctx(reg), surfaced, "Refund ORD-5160 in full, it was lost.")
        b, _ = await gw.handle("order_refund", {"order_id": "ORD-5160", "reason": "item_not_received", "amount": 89.99}, _ctx(reg), surfaced, "Refund ORD-5160 in full, it was lost.")
        return a, b

    a, b = anyio.run(lambda: _session(world, body))
    assert a["status"] == "NOT_EXECUTED" and a["stage"] == "provenance"
    assert b["status"] == "EXECUTED"  # equals the refundable amount on record: platform-owned


def test_single_item_replacement_binds_sku_multi_item_needs_it(world):
    async def body(est, gw, reg, surfaced):
        one, t1 = await gw.handle("order_replacement", {"order_id": "ORD-5154", "reason": "cracked"}, _ctx(reg), surfaced, "The mug set on ORD-5154 arrived cracked. Send a replacement.")
        two, _ = await gw.handle("order_replacement", {"order_id": "ORD-5216", "sku": "BELT-L"}, _ctx(reg), surfaced, "The customer on ORD-5216 received the wrong item. Please send the correct one.")
        return one, t1, two

    one, t1, two = anyio.run(lambda: _session(world, body))
    assert one["status"] == "EXECUTED" and "sku" in t1.binding["bound_fields"]
    assert two["status"] == "NOT_EXECUTED" and two["stage"] == "provenance"


def test_entity_context_marks_nonexistent_and_lists_charges(world):
    async def body(est, gw, reg, surfaced):
        return await resolve_entities("Refund ORD-9917 and check ORD-4917", gw.context_read)

    ctx = anyio.run(lambda: _session(world, body))
    text = render_context(ctx)
    assert "ORD-9917 (order): DOES NOT EXIST" in text
    assert text.count("charge: PAY-4917") == 2


def test_audit_bound_finish():
    arm = ControlPlaneArm.__new__(ControlPlaneArm)
    arm.results = [{"tool": "order_refund", "status": "APPROVAL_REQUIRED", "write": True}]
    assert "needs_approval" in arm.validate_finish("completed")
    assert arm.validate_finish("needs_approval") is None
    arm.results = [{"tool": "order_refund", "status": "NOT_EXECUTED", "write": True}]
    assert arm.validate_finish("completed") is not None
    arm.results = [{"tool": "order_refund", "status": "NOT_EXECUTED", "write": True}, {"tool": "order_refund", "status": "EXECUTED", "write": True}]
    assert arm.validate_finish("completed") is None
    arm.results = [{"tool": "shipment_track", "status": "EXECUTED", "write": False}]
    assert arm.validate_finish("completed") is None


def test_same_invocation_twice_executes_once(world):
    req = "Give Jordan Ellis (CUS-2211) a $15 goodwill credit for the delay on ORD-5190."

    async def body(est, gw, reg, surfaced):
        a, _ = await gw.handle("customer_store_credit", {"customer_id": "CUS-2211", "amount": 15, "reason": "late delivery"}, _ctx(reg), surfaced, req)
        b, t = await gw.handle("customer_store_credit", {"customer_id": "CUS-2211", "amount": 15, "reason": "late delivery"}, _ctx(reg), surfaced, req)
        return a, b, t

    a, b, t = anyio.run(lambda: _session(world, body))
    assert a["status"] == "EXECUTED" and b["status"] == "EXECUTED"
    assert b["result"].get("idempotent_replay") is True and t.execution["idempotency_key"]
    assert len(read_effects(world)) == 1


def test_hitl_approval_executes_exact_invocation_once(world):
    req = "ORD-5200 was charged twice, 640 dollars each time. Refund the duplicate."

    async def body(est, gw, reg, surfaced):
        ctx = _ctx(reg)
        held, _ = await gw.handle("order_refund", {"order_id": "ORD-5200", "reason": "duplicate_charge"}, ctx, surfaced, req)
        assert held["status"] == "APPROVAL_REQUIRED"
        for a in gw.approvals.pending():
            gw.approvals.decide(a.approval_id, "sup:alex.kim", True)
        other_request = CallContext("REQ-OTHER", ctx.requester_id, ctx.requester_role, ctx.user_scopes, ctx.agent_id, ctx.agent_scopes, ctx.environment)
        changed, _ = await gw.handle("order_refund", {"order_id": "ORD-5200", "reason": "duplicate_charge"}, other_request, surfaced, req)
        same, t = await gw.handle("order_refund", {"order_id": "ORD-5200", "reason": "duplicate_charge"}, ctx, surfaced, req)
        again, _ = await gw.handle("order_refund", {"order_id": "ORD-5200", "reason": "duplicate_charge"}, ctx, surfaced, req)
        return changed, same, t, again

    changed, same, t, again = anyio.run(lambda: _session(world, body))
    assert changed["status"] == "APPROVAL_REQUIRED"  # same values, different request -> different digest -> approval does not transfer
    assert same["status"] == "EXECUTED" and t.approval["status"] == "consumed"
    assert again["status"] != "EXECUTED"  # approval is single-use; the charge is also no longer a refundable duplicate
    assert [(e["effect_type"], e["amount"]) for e in read_effects(world)] == [("order_refund", 640.0)]


def test_fault_injection_transient_then_success_and_persistent_outage(world):
    from sprawl_poc.world.db import inject_faults

    inject_faults(world, {"refunds.refund_order": {"times": 1, "message": "503 temporarily unavailable"},
                          "refunds_eu.refund_order": {"times": 99, "message": "503 outage"}})
    req = "ORD-5260 was charged twice. Refund the duplicate charge."

    async def body(est, gw, reg, surfaced):
        ctx = _ctx(reg)
        first, _ = await gw.handle("order_refund", {"order_id": "ORD-5260", "reason": "duplicate_charge"}, ctx, surfaced, req)
        second, _ = await gw.handle("order_refund", {"order_id": "ORD-5260", "reason": "duplicate_charge"}, ctx, surfaced, req)
        return first, second

    async def body_eu(est, gw, reg, surfaced):  # a separate request
        ctx = _ctx(reg)
        eu1, _ = await gw.handle("order_refund", {"order_id": "ORD-6212", "reason": "duplicate_charge"}, ctx, surfaced, "ORD-6212 charged twice")
        eu2, _ = await gw.handle("order_refund", {"order_id": "ORD-6212", "reason": "duplicate_charge"}, ctx, surfaced, "ORD-6212 charged twice")
        vendor, _ = await gw.handle("paygate__refund_charge", {"payment_id": "PAY-62122", "amount": 55}, ctx, surfaced, "ORD-6212 charged twice, 55 EUR")
        vendor_policy, _ = await gw.govern_implementation("paygate__refund_charge", {"payment_id": "PAY-62122", "amount": 55}, ctx, "ORD-6212 charged twice, 55 EUR")
        return eu1, eu2, (vendor, vendor_policy)

    first, second = anyio.run(lambda: _session(world, body))
    eu1, eu2, vendor = anyio.run(lambda: _session(world, body_eu))
    assert first["status"] == "FAILED" and "503" in first["reason"]
    assert second["status"] == "EXECUTED"
    assert eu1["status"] == "FAILED" and eu2["status"] == "FAILED"
    vendor, vendor_policy = vendor  # the outage never opens a side door:
    assert vendor["status"] == "NOT_EXECUTED" and vendor["kind"] == "not_surfaced"  # the model cannot name the vendor tool
    assert vendor_policy["status"] == "DENIED" and vendor_policy["rule"] == "P5_NOT_AUTHORITATIVE"  # and policy denies it anyway
    assert [(e["server"], e["amount"]) for e in read_effects(world)] == [("refunds", 49.0)]


def test_needs_approval_requires_a_real_request_and_rejection_stands(world):
    arm = ControlPlaneArm.__new__(ControlPlaneArm)
    arm.results = []
    assert "no request" in arm.validate_finish("needs_approval")
    arm.results = [{"tool": "customer_store_credit", "status": "APPROVAL_REQUIRED", "write": True}]
    assert arm.validate_finish("needs_approval") is None
    req = "Give Ethan Wright (CUS-2219) $150 in store credit as a goodwill gesture for his lost drone order."

    async def body(est, gw, reg, surfaced):
        ctx = _ctx(reg)
        held, _ = await gw.handle("customer_store_credit", {"customer_id": "CUS-2219", "amount": 150, "reason": "goodwill"}, ctx, surfaced, req)
        for a in gw.approvals.pending():
            gw.approvals.decide(a.approval_id, "sup:alex.kim", False)
        again, _ = await gw.handle("customer_store_credit", {"customer_id": "CUS-2219", "amount": 150, "reason": "goodwill"}, ctx, surfaced, req)
        return held, again

    held, again = anyio.run(lambda: _session(world, body))
    assert held["status"] == "APPROVAL_REQUIRED"
    assert again["status"] == "DENIED" and again["rule"] == "P7_APPROVAL_REJECTED" and "refused" in again["next_step"]
    assert read_effects(world) == []


def test_duplicate_charge_invariant_blocks_refunding_the_original(world):
    req = "Refund ORD-7114, the customer was double charged."

    async def body(est, gw, reg, surfaced):
        ctx = _ctx(reg)
        orig, _ = await gw.handle("order_refund", {"order_id": "ORD-7114", "payment_id": "PAY-71141", "reason": "duplicate_charge"}, ctx, surfaced, req)
        dup, _ = await gw.handle("order_refund", {"order_id": "ORD-7114", "payment_id": "PAY-71142", "reason": "duplicate_charge"}, ctx, surfaced, req)
        again, _ = await gw.handle("order_refund", {"order_id": "ORD-7114", "reason": "duplicate_charge"}, ctx, surfaced, req)
        return orig, dup, again

    orig, dup, again = anyio.run(lambda: _session(world, body))
    assert orig["status"] == "NOT_EXECUTED" and "not a duplicate capture" in orig["reason"]
    assert dup["status"] == "EXECUTED"
    assert again["status"] == "NOT_EXECUTED"  # the duplicate is already refunded; nothing left to refund as a duplicate
    assert [(e["amount"], e["payload"]["payment_id"]) for e in read_effects(world)] == [(33.0, "PAY-71142")]


def test_second_financial_action_in_one_request_needs_approval(world):
    req = "Give Jordan Ellis (CUS-2211) a $15 goodwill credit for the delay on ORD-5190. Also refund $15."

    async def body(est, gw, reg, surfaced):
        ctx = _ctx(reg)
        first, _ = await gw.handle("customer_store_credit", {"customer_id": "CUS-2211", "amount": 15, "reason": "late delivery"}, ctx, surfaced, req)
        second, _ = await gw.handle("order_refund", {"order_id": "ORD-5190", "amount": 15, "reason": "customer_request"}, ctx, surfaced, req)
        return first, second

    first, second = anyio.run(lambda: _session(world, body))
    assert first["status"] == "EXECUTED"
    assert second["status"] == "APPROVAL_REQUIRED" and "second money-moving action" in second["reason"]
    assert len(read_effects(world)) == 1
