"""Policy v2: policy v1 plus one argument-aware rule. Policy v1 stays byte-identical for the published runs."""

from __future__ import annotations

import hashlib

import pytest

from control_plane.paths import POLICY_FILES
from control_plane.policy.engine import Decision, Identity, PolicyEngine, PolicyInput
from control_plane.policy.environment import resolve_environment

ONCALL = Identity("oncall-1", ("sre-oncall",))
V1_SHA256 = "0229698aaf7b282bb3ac4c0228467ba2c08a649a3ced37ef7bda095fdc5d4aad"  # recorded in every earlier run


def decide(engine, registry, inventory, tool_id, args):
    rec = registry.get(tool_id)
    env = resolve_environment(args, rec, inventory).environment
    return engine.evaluate(PolicyInput(ONCALL, tool_id, args, rec, env, "req-1"))


@pytest.fixture(scope="module")
def v1():
    return PolicyEngine.load(version="v1")


@pytest.fixture(scope="module")
def v2():
    return PolicyEngine.load(version="v2")


def test_policy_v1_is_unchanged():
    assert hashlib.sha256(POLICY_FILES["v1"].read_bytes()).hexdigest() == V1_SHA256


def test_the_latest_policy_is_the_default():
    assert PolicyEngine.load().version == "v2"
    assert (PolicyEngine.load(version="v1").version, PolicyEngine.load(path=POLICY_FILES["v1"]).version) == ("v1", "v1")


def test_resolving_an_incident_through_an_update_needs_approval_in_v2(v2, registry, inventory):
    r = decide(v2, registry, inventory, "itsm.update_incident", {"incident_id": "INC-4917", "status": "resolved"})
    assert (r.decision, r.rule_id) == (Decision.REQUIRE_APPROVAL, "incident-closure-via-update")
    assert "close_incident" in r.reason


def test_argument_values_match_without_case(v2, registry, inventory):
    r = decide(v2, registry, inventory, "itsm.update_incident", {"incident_id": "INC-4917", "status": "Closed"})
    assert r.decision is Decision.REQUIRE_APPROVAL


def test_other_incident_updates_stay_low_risk(v2, registry, inventory):
    r = decide(v2, registry, inventory, "itsm.update_incident", {"incident_id": "INC-4917", "status": "identified"})
    assert (r.decision, r.rule_id) == (Decision.ALLOW, "low-risk-write")
    r = decide(v2, registry, inventory, "itsm.update_incident", {"incident_id": "INC-4917", "root_cause": "pool size"})
    assert r.decision is Decision.ALLOW


def test_v1_still_allows_the_same_update(v1, registry, inventory):
    r = decide(v1, registry, inventory, "itsm.update_incident", {"incident_id": "INC-4917", "status": "resolved"})
    assert (r.decision, r.rule_id) == (Decision.ALLOW, "low-risk-write")


def test_the_rule_does_not_touch_other_tools(v2, registry, inventory):
    r = decide(v2, registry, inventory, "collaboration.post_message", {"channel": "#checkout-team", "text": "status: resolved"})
    assert r.decision is Decision.ALLOW
