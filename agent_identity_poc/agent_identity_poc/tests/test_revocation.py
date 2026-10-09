"""One lever per layer, each with its own blast radius."""
from aid.agents import IncidentIntel
from aid.config import MIN

READ = IncidentIntel().investigate()[0]


def test_revoked_delegation_takes_effect_at_re_exchange(chain):
    ex = chain.start("web", "cred-web", "agent.incident-intel", sso="sso-maya")
    chain.revoke_delegation("sre.maya")
    assert chain.call(ex, READ).effect == "EXECUTED"            # the live token is self-contained
    chain.clock.advance(16 * MIN)
    d = chain.call(ex, READ)
    assert d.effect == "REJECTED" and "revoked" in d.reason


def test_event_execution_unaffected_by_human_revocation(chain):
    ex = chain.start("event", "cred-monitoring", "agent.incident-intel")
    chain.revoke_delegation("sre.maya")
    chain.clock.advance(16 * MIN)
    assert chain.call(ex, READ).effect == "EXECUTED"


def test_disabled_agent_stops_immediately_including_in_chains(chain):
    parent = chain.start("web", "cred-web", "agent.incident-intel", sso="sso-maya")
    child = chain.delegate(parent, "agent.remediation")
    chain.disable_agent("agent.incident-intel")
    assert chain.call(parent, READ).effect == "REJECTED"
    assert chain.call(child, READ).effect == "REJECTED"


def test_quarantined_runtime_fails_attestation(chain):
    a = chain.start("event", "cred-monitoring", "agent.incident-intel")
    b = chain.start("cicd", "cred-ci", "agent.release-guard")
    chain.quarantine_runtime("svc.hai-runtime")
    assert chain.call(a, READ).effect == "REJECTED"
    assert chain.call(b, READ).effect == "EXECUTED"


def test_revoked_invoker_credential_refuses_new_executions(chain):
    import pytest
    from aid.directory import AuthError
    chain.revoke_invoker_credential("cred-monitoring")
    with pytest.raises(AuthError):
        chain.start("event", "cred-monitoring", "agent.incident-intel")


def test_shared_account_rotation_stops_everyone(shared):
    a = shared.start("event", "cred-monitoring", "agent.incident-intel")
    b = shared.start("cicd", "cred-ci", "agent.release-guard")
    shared.rotate_shared_account()
    assert shared.call(a, READ).effect == "REJECTED" and shared.call(b, READ).effect == "REJECTED"
