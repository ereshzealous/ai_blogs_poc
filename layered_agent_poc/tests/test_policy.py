from agent_platform.actions.policy import PolicyEngine
from agent_platform.actions.registry import CapabilityRegistry
from agent_platform.actions.types import ActionContext, Decision, Invocation

CTX = ActionContext("alice", "agent:incident-remediation", "wf-test", "propose_remediation", "production")
ENGINE = PolicyEngine(CapabilityRegistry())


def decide(tool, **args):
    return ENGINE.evaluate(Invocation(tool, args), CTX)


def test_read_only_is_allowed():
    r = decide("observability.query_latency", service="checkout-api", environment="production")
    assert (r.decision, r.rule_id) == (Decision.ALLOW, "P1-read-only")


def test_direct_kubernetes_rollback_of_a_gitops_service_is_denied():
    r = decide("kubernetes.rollback_deployment", service="checkout-api", environment="production", revision=41)
    assert (r.decision, r.rule_id) == (Decision.DENY, "P2-gitops-authoritative")


def test_write_to_another_environment_than_the_incident_is_denied():
    r = decide("source_control.rollback_release", service="checkout-api", environment="staging", target_version="v4.16")
    assert (r.decision, r.rule_id) == (Decision.DENY, "P3-env-must-match-incident")


def test_production_release_rollback_needs_an_incident_commander():
    r = decide("source_control.rollback_release", service="checkout-api", environment="production", target_version="v4.16")
    assert (r.decision, r.rule_id, r.approver_role) == (Decision.REQUIRE_APPROVAL, "P4-prod-high-risk-approval", "incident-commander")


def test_approval_digest_is_bound_to_arguments_and_workflow():
    a = decide("source_control.rollback_release", service="checkout-api", environment="production", target_version="v4.16")
    b = decide("source_control.rollback_release", service="checkout-api", environment="production", target_version="v4.15")
    other = ENGINE.evaluate(Invocation("source_control.rollback_release", {"service": "checkout-api", "environment": "production",
                                                                          "target_version": "v4.16"}),
                            ActionContext("alice", "agent", "wf-other", "x", "production"))
    assert len({a.digest, b.digest, other.digest}) == 3


def test_unregistered_tool_is_denied():
    r = decide("database.drop_table", table="orders")
    assert (r.decision, r.rule_id) == (Decision.DENY, "P0-default-deny")


def test_low_risk_write_is_allowed():
    r = decide("itsm.update_incident", incident_id="INC-4917", status="resolved", note="x")
    assert r.decision is Decision.ALLOW
