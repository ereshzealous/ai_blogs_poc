"""Deterministic policy: ALLOW, REQUIRE_APPROVAL, DENY, scope delegation, environment and approvals."""

from __future__ import annotations

import pytest

from benchmark.evaluator.metrics import load_all_cases
from control_plane.policy.approvals import ApprovalRequest, ApprovalStatus, ApprovalStore
from control_plane.policy.engine import Decision, Identity, PolicyEngine, PolicyInput, invocation_digest
from control_plane.policy.environment import resolve_environment


def decide(policy, registry, inventory, identity, tool_id, args):
    rec = registry.get(tool_id)
    env = resolve_environment(args, rec, inventory).environment
    return policy.evaluate(PolicyInput(identity, tool_id, args, rec, env, "req-1"))


def test_read_is_allowed(policy, registry, inventory, oncall):
    r = decide(policy, registry, inventory, oncall, "observability.query_metrics",
               {"service": "checkout-api", "metric": "latency_p95_ms", "environment": "production"})
    assert (r.decision, r.rule_id) == (Decision.ALLOW, "read-only")


def test_production_rollback_requires_approval(policy, registry, inventory, oncall):
    r = decide(policy, registry, inventory, oncall, "source_control.rollback_release",
               {"service": "checkout-api", "environment": "production", "to_version": "v4.16"})
    assert r.decision is Decision.REQUIRE_APPROVAL


def test_same_rollback_in_staging_is_allowed(policy, registry, inventory, oncall):
    r = decide(policy, registry, inventory, oncall, "source_control.rollback_release",
               {"service": "checkout-api", "environment": "staging", "to_version": "v4.16"})
    assert r.decision is Decision.ALLOW


def test_destructive_production_action_is_denied_even_with_scope(policy, registry, inventory):
    # a hypothetical agent with every scope still cannot run a destructive action in production
    policy.config["agents"]["break-glass-agent"] = ["*"]
    policy.config["roles"]["admin"] = ["*"]
    r = decide(policy, registry, inventory, Identity("admin-1", ("admin",), "break-glass-agent"), "cloud.terminate_instance",
               {"instance_id": "i-0c41e7a9d2b3f5812"})
    assert (r.decision, r.rule_id, r.environment) == (Decision.DENY, "destructive-in-production", "production")


def test_terminate_denied_for_incident_agent(policy, registry, inventory, oncall):
    r = decide(policy, registry, inventory, oncall, "cloud.terminate_instance", {"instance_id": "i-0c41e7a9d2b3f5812"})
    assert r.decision is Decision.DENY


def test_deprecated_and_unregistered_tools_are_denied(policy, registry, inventory, oncall):
    assert decide(policy, registry, inventory, oncall, "legacy_monitoring.get_latency_report", {"service": "checkout-api"}).rule_id == "deprecated-tool"
    assert decide(policy, registry, inventory, oncall, "ops_debug.restart_service", {"service": "checkout-api"}).rule_id == "unregistered-tool"


def test_environment_restricted_server(policy, registry, inventory, oncall):
    # k8s_staging_eu only serves staging; the registry resolves its environment even without an argument
    r = decide(policy, registry, inventory, oncall, "k8s_staging_eu.restart_pod", {"pod": "checkout-api-6c7d8e9f0-a1b2c"})
    assert (r.decision, r.environment) == (Decision.ALLOW, "staging")


def test_agent_cannot_exceed_user_scopes(policy, registry, inventory, developer):
    r = decide(policy, registry, inventory, developer, "source_control.rollback_release",
               {"service": "checkout-api", "environment": "production", "to_version": "v4.16"})
    assert (r.decision, r.rule_id) == (Decision.DENY, "missing-scope")
    assert r.missing_scopes == ["deploy.rollback"]


def test_user_scopes_do_not_extend_agent(policy, registry, inventory, oncall):
    # the on-call human may close incidents; the incident agent may not
    r = decide(policy, registry, inventory, oncall, "itsm.close_incident", {"incident_id": "INC-4917", "resolution_code": "fixed"})
    assert (r.decision, r.missing_scopes) == (Decision.DENY, ["itsm.incident.close"])


def test_unknown_environment_defaults_to_production(registry, inventory):
    rec = registry.get("cloud.restart_instance")
    assert resolve_environment({"instance_id": "i-00000000deadbeef"}, rec, inventory).environment == "production"
    assert resolve_environment({"instance_id": "i-00000000deadbeef"}, rec, inventory).source == "default"


def test_policy_ignores_mcp_annotations(policy, registry, inventory, oncall):
    # cloud_ops.restart_service is published with readOnlyHint=true; the registry says HIGH_RISK_WRITE
    r = decide(policy, registry, inventory, oncall, "cloud_ops.restart_service", {"service": "checkout-api", "environment": "production"})
    assert r.decision is Decision.REQUIRE_APPROVAL


POLICIES = {version: PolicyEngine.load(version=version) for version in ("v1", "v2")}


@pytest.mark.parametrize("case", load_all_cases(), ids=lambda c: c.id)
def test_every_case_expected_policy(registry, inventory, case):
    """Each case file's expected decisions assume the policy version it declares (v1 unless stated)."""
    args = {k: (v[0] if isinstance(v, list) else ("x" if v == "*" else v)) for k, v in case.expected_args.items()}
    r = decide(POLICIES[case.policy_version], registry, inventory, Identity(case.user_id, case.roles), case.golden_tool, args)
    assert r.decision.value == case.expected_policy


def test_invocation_digest_binds_arguments():
    a = invocation_digest("source_control.rollback_release", {"service": "checkout-api", "to_version": "v4.16"}, "production", "r1")
    b = invocation_digest("source_control.rollback_release", {"service": "checkout-api", "to_version": "v4.15"}, "production", "r1")
    c = invocation_digest("source_control.rollback_release", {"to_version": "v4.16", "service": "checkout-api"}, "production", "r1")
    assert a != b and a == c


def test_approval_store_lifecycle():
    store = ApprovalStore()
    req = ApprovalRequest("d1", "r1", "source_control.rollback_release", "{}", "production", "high risk")
    assert store.request(req) is ApprovalStatus.PENDING
    assert store.request(req) is ApprovalStatus.PENDING  # idempotent
    assert store.decide("d1", True, "oncall-1") is ApprovalStatus.APPROVED
    assert store.status("d1") is ApprovalStatus.APPROVED
    with pytest.raises(KeyError):
        store.decide("d1", False, "oncall-1")  # already decided
    store.request(ApprovalRequest("d2", "r2", "kubernetes.rollback_deployment", "{}", "production", "high risk"))
    assert store.decide("d2", False, "oncall-1") is ApprovalStatus.REJECTED
