"""Deterministic governance tests: policy rules, approval binding, audit chain. No model, no MCP."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sprawl_poc.catalog.build import build
from sprawl_poc.control_plane.approval import ApprovalService
from sprawl_poc.control_plane.audit import AuditLog
from sprawl_poc.control_plane.invocation import CallContext, Invocation
from sprawl_poc.control_plane.policy import ALLOW, DENY, REQUIRE_APPROVAL, Policy
from sprawl_poc.registry.model import load_registry
from sprawl_poc.util import DATA_DIR


@pytest.fixture(scope="module")
def registry():
    if not (DATA_DIR / "estates" / "estate-500" / "registry.yaml").exists():
        build()
    return load_registry(DATA_DIR / "estates" / "estate-500" / "registry.yaml")


def ctx(registry, role="support_t1", env="prod", request_id="REQ-1"):
    return CallContext(request_id, "rep:dana", role, registry.roles[role], "support-assistant", registry.agents["support-assistant"], env)


US = {"region": "us"}
EU = {"region": "eu"}
REFUND = {"order_id": "ORD-4917", "payment_id": "PAY-49172", "amount": 184.20, "reason": "duplicate_charge"}


@pytest.mark.parametrize(
    "impl,args,facts,decision,rule",
    [
        ("marketing_ops.bulk_goodwill_refund", {"customer_ids": ["CUS-2210"], "amount": 10}, {}, DENY, "P1_UNREGISTERED"),
        ("payments_legacy.refund_charge_v1", {"payment_id": "PAY-49172", "amount": 184.2}, {}, DENY, "P2_RETIRED"),
        ("refunds_staging.refund_order", REFUND, US, DENY, "P3_ENVIRONMENT"),
        ("refunds_eu.refund_order", REFUND, US, DENY, "P4_REGION"),
        ("refunds.refund_order", REFUND, EU, DENY, "P4_REGION"),
        ("paygate.refund_charge", {"payment_id": "PAY-49172", "amount": 184.2}, {}, DENY, "P5_NOT_AUTHORITATIVE"),
        ("refunds.refund_order", REFUND, US, ALLOW, "P8_ALLOW"),
        ("refunds_eu.refund_order", {**REFUND, "order_id": "ORD-6201"}, EU, ALLOW, "P8_ALLOW"),
        ("refunds.refund_order", {**REFUND, "amount": 640.0}, US, REQUIRE_APPROVAL, "P7_APPROVAL"),
        ("refunds.refund_order", {**REFUND, "amount": 250.0}, US, ALLOW, "P8_ALLOW"),  # threshold is strictly greater-than
        ("promotions.issue_store_credit", {"customer_id": "CUS-2219", "amount": 150}, US, REQUIRE_APPROVAL, "P7_APPROVAL"),
        ("crm.update_customer_email", {"customer_id": "CUS-2210", "email": "x@example.net"}, US, DENY, "P6_SCOPE"),
        ("subscriptions_legacy.cancel_subscription", {"subscription_id": "S1"}, {}, DENY, "P2_RETIRED"),
        ("gift_cards_staging.void_gift_card", {"gift_card_id": "G1"}, {}, DENY, "P3_ENVIRONMENT"),
        ("subscriptions.cancel_subscription", {"subscription_id": "S1"}, {}, DENY, "P6_SCOPE"),
    ],
)
def test_policy_rules(registry, impl, args, facts, decision, rule):
    d = Policy(registry).evaluate(Invocation(impl, args, ctx(registry)), facts)
    assert (d.decision, d.rule) == (decision, rule), d.reason


def test_scope_is_intersection_of_user_and_agent(registry):
    inv = Invocation("crm.update_customer_email", {"customer_id": "CUS-2210", "email": "x@example.net"}, ctx(registry, role="support_t2"))
    assert Policy(registry).evaluate(inv, US).decision == ALLOW


def test_wrong_session_environment_denies_prod_tool(registry):
    inv = Invocation("refunds.refund_order", REFUND, ctx(registry, env="staging"))
    assert Policy(registry).evaluate(inv, US).rule == "P3_ENVIRONMENT"


def test_approval_binds_to_exact_invocation(registry):
    pol = Policy(registry)
    svc = ApprovalService()
    big = {**REFUND, "amount": 640.0, "order_id": "ORD-5200", "payment_id": "PAY-52002"}
    inv = Invocation("refunds.refund_order", big, ctx(registry))
    rec = svc.request(inv, pol.version, "over threshold")
    assert svc.check(rec.approval_id, inv, pol.version) == (False, "approval is pending")
    with pytest.raises(Exception):
        svc.decide(rec.approval_id, "rep:dana", True)  # requester cannot self-approve
    svc.decide(rec.approval_id, "sup:alex", True)
    assert svc.check(rec.approval_id, inv, pol.version)[0]
    # any change to arguments, environment, requester or request voids it
    for changed in (
        Invocation("refunds.refund_order", {**big, "amount": 641.0}, ctx(registry)),
        Invocation("refunds.refund_order", {**big, "payment_id": "PAY-52001"}, ctx(registry)),
        Invocation("refunds_eu.refund_order", big, ctx(registry)),
        Invocation("refunds.refund_order", big, ctx(registry, request_id="REQ-2")),
        Invocation("refunds.refund_order", big, ctx(registry, env="staging")),
    ):
        ok, why = svc.check(rec.approval_id, changed, pol.version)
        assert not ok and "digest" in why
    # a policy change also voids it
    assert not svc.check(rec.approval_id, inv, pol.version + "-changed")[0]
    svc.consume(rec.approval_id)
    assert svc.check(rec.approval_id, inv, pol.version) == (False, "approval is consumed")


def test_audit_chain_detects_tampering(tmp_path: Path):
    p = tmp_path / "audit.jsonl"
    log = AuditLog(p)
    for i in range(5):
        log.append("event", {"i": i})
    assert AuditLog.verify(p) == (True, "ok")
    lines = p.read_text().splitlines()
    rec = json.loads(lines[2])
    rec["payload"]["i"] = 99
    lines[2] = json.dumps(rec)
    p.write_text("\n".join(lines) + "\n")
    ok, why = AuditLog.verify(p)
    assert not ok and "record 2" in why
    p.write_text("\n".join(lines[:2] + lines[3:]) + "\n")  # deletion
    assert not AuditLog.verify(p)[0]


def test_estate_manifests_are_nested_and_exact():
    sizes = {}
    for n in (50, 100, 500):
        m = json.loads((DATA_DIR / "estates" / f"estate-{n}" / "manifest.json").read_text())
        assert m["tool_count"] == n
        sizes[n] = {s["server"] for s in m["servers"]}
    assert sizes[50] < sizes[100] < sizes[500]


def test_registry_never_contains_shadow_tools(registry):
    assert not any(k.startswith("marketing_ops.") for k in registry.implementations)
