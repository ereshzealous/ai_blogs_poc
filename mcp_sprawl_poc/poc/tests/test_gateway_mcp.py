"""Gateway + binding over REAL MCP servers (stdio subprocesses). No model.

These tests *break* the execution path on purpose: direct calls that skip the gateway,
forged and replayed tokens, arguments changed after approval, retired/shadow/staging
implementations named directly (rejected at the proposal stage when the model names them;
denied by policy on the internal path), nonexistent entities.
"""

from __future__ import annotations

import secrets
from pathlib import Path

import anyio
import pytest

from sprawl_poc.control_plane.approval import ApprovalService
from sprawl_poc.control_plane.audit import AuditLog
from sprawl_poc.control_plane.gateway import Gateway
from sprawl_poc.control_plane.invocation import CallContext, Invocation
from sprawl_poc.control_plane.resolve import CapabilityResolver
from sprawl_poc.mcp_host import Estate
from sprawl_poc.registry.model import load_registry
from sprawl_poc.servers.serve import GATEWAY_META_KEY, gateway_mac
from sprawl_poc.util import DATA_DIR
from sprawl_poc.world.db import read_effects, reset_from_seed
from sprawl_poc.world.seed import SEED_DB, build as build_seed

pytestmark = pytest.mark.mcp
ESTATE = DATA_DIR / "estates" / "estate-50"


def run(coro_fn):
    return anyio.run(coro_fn)


@pytest.fixture()
def world(tmp_path: Path):
    if not SEED_DB.exists():
        build_seed()
    db = tmp_path / "world.db"
    reset_from_seed(SEED_DB, db)
    return db


def _ctx(reg, role="support_t1"):
    return CallContext("REQ-T", "rep:dana", role, reg.roles[role], "support-assistant", reg.agents["support-assistant"], "prod")


async def _gateway_session(db: Path, body):
    reg = load_registry(ESTATE / "registry.yaml")
    key = secrets.token_hex(16)
    async with Estate(ESTATE, db, enforce_gateway_token=True, gateway_key=key) as est:
        gw = Gateway(est, reg, AuditLog(db.with_suffix(".audit.jsonl")), ApprovalService(), key)
        resolver = CapabilityResolver(reg, est.tools, "prod")
        surfaced = {c.tool_name: c for c in (resolver.surface(cap, 0, ()) for cap in reg.capabilities) if c}
        return await body(est, gw, reg, surfaced, key)


def test_protocol_version_is_measured(world):
    async def body(est, gw, reg, surfaced, key):
        return est.protocol_record()

    rec = run(lambda: _gateway_session(world, body))
    assert rec["negotiated_protocol_versions"] == ["2026-07-28"]
    assert rec["sdk_version"] == "2.2.0"


def test_bypass_forgery_and_replay_are_rejected_by_servers(world):
    async def body(est, gw, reg, surfaced, key):
        args = {"order_id": "ORD-4917", "payment_id": "PAY-49172", "amount": 184.2, "reason": "duplicate_charge"}
        no_token = await est.call("refunds.refund_order", args)
        forged = await est.call("refunds.refund_order", args, meta={GATEWAY_META_KEY: {"invocation_id": "INV-x", "mac": "0" * 64}})
        wrong_key = await est.call("refunds.refund_order", args, meta={GATEWAY_META_KEY: {"invocation_id": "INV-y", "mac": gateway_mac(b"not-the-key", "refunds.refund_order", args, "INV-y")}})
        good_mac = gateway_mac(key.encode(), "refunds.refund_order", args, "INV-z")
        altered = await est.call("refunds.refund_order", {**args, "amount": 184.0}, meta={GATEWAY_META_KEY: {"invocation_id": "INV-z", "mac": good_mac}})
        first = await est.call("paygate.get_charge_status", {"payment_id": "PAY-49172"}, meta={GATEWAY_META_KEY: {"invocation_id": "INV-r", "mac": gateway_mac(key.encode(), "paygate.get_charge_status", {"payment_id": "PAY-49172"}, "INV-r")}})
        replay = await est.call("paygate.get_charge_status", {"payment_id": "PAY-49172"}, meta={GATEWAY_META_KEY: {"invocation_id": "INV-r", "mac": gateway_mac(key.encode(), "paygate.get_charge_status", {"payment_id": "PAY-49172"}, "INV-r")}})
        return no_token, forged, wrong_key, altered, first, replay

    no_token, forged, wrong_key, altered, first, replay = run(lambda: _gateway_session(world, body))
    for r in (no_token, forged, wrong_key, altered):
        assert r.is_error and "REJECTED_BY_SERVER" in r.text
    assert not first.is_error
    assert replay.is_error and "replay" in replay.text
    assert read_effects(world) == []


def test_ord4917_binds_duplicate_charge_and_executes(world):
    async def body(est, gw, reg, surfaced, key):
        return await gw.handle("order_refund", {"order_id": "ORD-4917", "reason": "duplicate_charge"}, _ctx(reg), surfaced)

    result, trace = run(lambda: _gateway_session(world, body))
    assert result["status"] == "EXECUTED", result
    assert trace.canonical_invocation["arguments"] == {"order_id": "ORD-4917", "payment_id": "PAY-49172", "amount": 184.2, "reason": "duplicate_charge"}
    assert set(trace.binding["bound_fields"]) == {"payment_id", "amount"}
    eff = read_effects(world)
    assert [(e["server"], e["effect_type"], e["amount"], bool(e["gateway_verified"])) for e in eff] == [("refunds", "order_refund", 184.2, True)]


@pytest.mark.parametrize(
    "tool,args,status,rule_or_kind",
    [
        ("payments_legacy__refund_charge_v1", {"payment_id": "PAY-49172", "amount": 184.2}, "DENIED", "P2_RETIRED"),
        ("paygate__refund_charge", {"payment_id": "PAY-49172", "amount": 184.2}, "DENIED", "P5_NOT_AUTHORITATIVE"),
        ("refunds_staging__refund_order", {"order_id": "ORD-4917", "payment_id": "PAY-49172", "amount": 184.2, "reason": "duplicate_charge"}, "DENIED", "P3_ENVIRONMENT"),
        ("marketing_ops__bulk_goodwill_refund", {"customer_ids": ["CUS-2210"], "amount": 184.2}, "DENIED", "P1_UNREGISTERED"),
        ("refunds_eu__refund_order", {"order_id": "ORD-4917", "payment_id": "PAY-49172", "amount": 184.2, "reason": "duplicate_charge"}, "DENIED", "P4_REGION"),
        ("order_refund", {"order_id": "ORD-9917", "reason": "duplicate_charge"}, "NOT_EXECUTED", "entity_not_found"),
        ("order_refund", {"order_id": "ORD-5230", "reason": "duplicate_charge"}, "NOT_EXECUTED", "no_matching_charge"),
        ("order_refund", {"order_id": "ORD-5200", "reason": "duplicate_charge"}, "APPROVAL_REQUIRED", "P7_APPROVAL"),
        ("customer_update_email", {"customer_id": "CUS-2210", "email": "maya.c@example.net"}, "DENIED", "P6_SCOPE"),
        ("order_refund", {"order_id": "ORD-4917", "reason": "Duplicate charge"}, "NOT_EXECUTED", "proposal_schema"),
        ("customer_store_credit", {"customer_id": "CUS-2210", "amount": -5, "reason": "x"}, "NOT_EXECUTED", "proposal_schema"),
        ("refunds__refund_order", {"order_id": "ORD-4917", "payment_id": "PAY-49172", "amount": -5, "reason": "duplicate_charge"}, "NOT_EXECUTED", "schema"),
        ("order_refund", {"order_id": "ORD-4917", "reason": "duplicate_charge", "amount": 500}, "NOT_EXECUTED", "invalid_value"),
    ],
)
def test_control_plane_blocks_unsafe_invocations(world, tool, args, status, rule_or_kind):
    async def body(est, gw, reg, surfaced, key):
        if tool in est.by_model_name:  # an implementation: the policy rules, through the internal (not model-facing) path
            return await gw.govern_implementation(tool, args, _ctx(reg))
        return await gw.handle(tool, args, _ctx(reg), surfaced)

    result, trace = run(lambda: _gateway_session(world, body))
    assert result["status"] == status, result
    assert rule_or_kind in (result.get("rule"), result.get("kind"), result.get("stage")), result
    assert read_effects(world) == []


def test_servers_validate_their_declared_schema(world):
    async def body(est, gw, reg, surfaced, key):
        return await gw._signed_call("refunds.refund_order", {"order_id": "ORD-4917", "payment_id": "PAY-49172", "amount": 10, "reason": "Duplicate charge"})

    _inv, out = run(lambda: _gateway_session(world, body))
    assert out.is_error and "invalid arguments" in out.text
    assert read_effects(world) == []


def test_eu_order_resolves_eu_implementation(world):
    async def body(est, gw, reg, surfaced, key):
        return await gw.handle("order_refund", {"order_id": "ORD-6201", "reason": "duplicate_charge"}, _ctx(reg), surfaced)

    result, trace = run(lambda: _gateway_session(world, body))
    assert result["status"] == "EXECUTED" and trace.implementation == "refunds_eu.refund_order"


def test_approved_invocation_executes_once_and_changed_args_do_not(world):
    async def body(est, gw, reg, surfaced, key):
        ctx = _ctx(reg)
        held, trace = await gw.handle("order_refund", {"order_id": "ORD-5200", "reason": "duplicate_charge"}, ctx, surfaced)
        apr = held["approval_id"]
        gw.approvals.decide(apr, "sup:alex", True)
        inv = Invocation(trace.implementation, trace.canonical_invocation["arguments"], ctx)
        facts = trace.binding["facts"]
        changed = Invocation(inv.implementation, {**inv.arguments, "amount": 639.0}, ctx)
        r_changed, _ = await gw.execute_approved(apr, changed, facts)
        r_ok, _ = await gw.execute_approved(apr, inv, facts)
        r_again, _ = await gw.execute_approved(apr, inv, facts)
        return r_changed, r_ok, r_again

    r_changed, r_ok, r_again = run(lambda: _gateway_session(world, body))
    assert r_changed["status"] != "EXECUTED" and "digest" in r_changed["reason"]
    assert r_ok["status"] == "EXECUTED"
    assert r_again["status"] != "EXECUTED"
    eff = read_effects(world)
    assert len(eff) == 1 and eff[0]["amount"] == 640.0
