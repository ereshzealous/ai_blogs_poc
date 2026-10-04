import pytest

from layered_platform.policy.engine import PolicyEngine
from layered_platform.tools.registry import Registry

REG = Registry()
POL = PolicyEngine()


def decide(cap, args, env="production"):
    return POL.evaluate(cap, REG.get(cap), args, env)


@pytest.mark.parametrize("cap,args,effect,rule", [
    ("incident.get", {"incident_id": "INC-4917"}, "ALLOW", "P1-read"),
    ("deploy.rollback", {"service": "checkout-api", "environment": "production", "to_release": "rel-2030"}, "REQUIRE_APPROVAL", "P3-high-risk-production-write"),
    ("deploy.restart", {"service": "checkout-api", "environment": "production"}, "REQUIRE_APPROVAL", "P3-high-risk-production-write"),
    ("deploy.rollback", {"service": "checkout-api", "environment": "staging", "to_release": "rel-2032"}, "DENY", "P2-cross-environment-write"),
    ("deploy.flush_sessions", {"service": "checkout-api", "environment": "production"}, "DENY", "P0-unregistered"),
    ("incident.update", {"incident_id": "INC-4917", "status": "mitigated", "note": "x"}, "ALLOW", "P4-low-risk-write"),
])
def test_policy_table(cap, args, effect, rule):
    d = decide(cap, args)
    assert (d.effect, d.rule) == (effect, rule)


def test_policy_is_deterministic():
    args = {"service": "checkout-api", "environment": "production", "to_release": "rel-2030"}
    assert len({decide("deploy.rollback", args).model_dump_json() for _ in range(50)}) == 1


def test_default_is_deny():
    assert PolicyEngine(rules=[{"id": "P9", "when": {}, "effect": "DENY", "reason": "no"}]).evaluate("x", None, {}, "production").effect == "DENY"
