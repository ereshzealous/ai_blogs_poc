"""Policy is deterministic and identical for every architecture."""

from __future__ import annotations

from coord.policy import PolicyEngine

P = PolicyEngine()
ALL = ["read:incident", "read:telemetry", "read:deploy", "read:change", "write:rollback", "write:sessions", "write:scale"]


def test_read_allowed():
    assert P.evaluate("query_metrics", {"environment": "production"}, ALL, "production").effect == "ALLOW"


def test_production_write_needs_approval():
    d = P.evaluate("rollback_release", {"environment": "production"}, ALL, "production")
    assert (d.effect, d.required_role) == ("REQUIRE_APPROVAL", "incident-commander")


def test_session_flush_denied_even_with_scope():
    assert P.evaluate("flush_sessions", {"environment": "production"}, ALL, "production").rule == "P4-no-session-flush"


def test_missing_scope_denied():
    assert P.evaluate("revert_config", {"environment": "production"}, ALL, "production").rule == "P1-scope"


def test_cross_environment_write_denied():
    assert P.evaluate("rollback_release", {"environment": "staging"}, ALL, "production").rule == "P3-cross-environment"


def test_unregistered_denied():
    assert P.evaluate("drop_database", {}, ALL, "production").rule == "P0-unregistered"
