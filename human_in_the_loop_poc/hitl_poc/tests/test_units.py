"""Implementation tests (not part of the canonical 30): digests, the transition table, the PDP, the safeguards."""
from hitl.approvals import TERMINAL, TRANSITIONS
from hitl.contracts import Action, Target
from hitl.policy import PolicyEngine
from hitl.suite import run_suite


def _a(**kw):
    base = dict(capability="rollbackDeployment", target=Target(service="payment-service", environment="production"),
                arguments={"from_version": "v4.18.0", "to_version": "v4.17.2"}, preconditions={"current_version": "v4.18.0"},
                policy={"policy_id": "prod-change-policy", "version": "7"}, risk="high_write")
    base.update(kw)
    return Action(**base)


def test_digest_is_canonical_and_sensitive():
    assert _a().digest() == _a(arguments={"to_version": "v4.17.2", "from_version": "v4.18.0"}).digest()      # key order is irrelevant
    for change in ({"arguments": {"from_version": "v4.18.0", "to_version": "v4.16.0"}}, {"risk": "low_write"},
                   {"policy": {"policy_id": "prod-change-policy", "version": "8"}}, {"preconditions": {"current_version": "v4.18.1"}},
                   {"target": Target(service="payment-service", environment="staging")}):
        assert _a(**change).digest() != _a().digest(), change


def test_terminal_states_have_no_exit():
    assert TERMINAL == {"SUCCEEDED", "REJECTED", "EXPIRED", "CANCELED", "DENIED", "REAPPROVAL_REQUIRED"}
    assert "APPROVED" not in TRANSITIONS["DENIED"] and "EXECUTING" not in TRANSITIONS["EXPIRED"]


def test_policy_fails_closed():
    p = PolicyEngine()
    assert p.evaluate("rollbackDeployment").decision == "REQUIRE_APPROVAL"
    assert p.evaluate("kubectl").decision == "DENY"
    p.available = False
    assert p.evaluate("getLogs").decision == "DENY" and p.evaluate("getLogs").rule == "P0-fail-closed"


def test_safeguards_are_load_bearing(tmp_path):
    (t07,) = run_suite(tmp_path / "a", {"bind_digest": False}, only=["HITL-T07"])
    (t18,) = run_suite(tmp_path / "b", {"authenticate_approver": False}, only=["HITL-T18"])
    assert t07.measured["side_effects"] == 1 and t18.measured["side_effects"] == 1


def test_http_roundtrip(tmp_path):
    from hitl.api import roundtrip
    r = roundtrip(tmp_path)
    assert r["calls_ok"] == r["calls"] and r["rollbacks"] == 1, r["log"]
