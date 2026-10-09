"""Delegation, narrowing, non-delegable scopes, sender constraint and audience."""
import pytest

from aid.agents import IncidentIntel, ReleaseGuard, Remediation
from aid.trust import TrustError


def test_event_execution_has_no_human_and_no_rollback_scope(chain):
    ex = chain.start("event", "cred-monitoring", "agent.incident-intel")
    assert ex.token.on_behalf_of is None and ex.token.sub == "svc.monitoring-webhook"
    assert "deploy:rollback" not in ex.token.scopes and "incident:investigate" not in ex.token.scopes


def test_scopes_are_an_intersection(chain):
    ex = chain.start("web", "cred-web", "agent.incident-intel", sso="sso-maya")
    d = chain.d
    assert set(ex.token.scopes) == d.delegable("sre.maya") & d.delegable("svc.web-portal") & d.ceiling("agent.incident-intel")


def test_even_the_incident_commander_cannot_delegate_rollback(chain):
    ex = chain.start("web", "cred-web", "agent.incident-intel", sso="sso-dev")
    assert chain.d.holds("ic.dev", "deploy:rollback") and "deploy:rollback" not in ex.token.scopes


def test_delegation_keeps_the_actor_and_narrows(chain):
    parent = chain.start("web", "cred-web", "agent.incident-intel", sso="sso-maya")
    child = chain.delegate(parent, "agent.remediation")
    assert child.token.act.chain() == ["agent.remediation@1.0.0", "agent.incident-intel@1.3.0"]
    assert child.token.sub == "sre.maya" and set(child.token.scopes) <= set(parent.token.scopes)
    assert child.token.exp == parent.token.exp


def test_undeclared_edge_refused(chain):
    parent = chain.start("web", "cred-web", "agent.incident-intel", sso="sso-maya")
    with pytest.raises(TrustError):
        chain.delegate(parent, "agent.release-guard")


def test_depth_limit(chain):
    chain.d.agents["agent.remediation"]["may_delegate_to"] = ["agent.incident-intel"]
    chain.d.agents["agent.incident-intel"]["may_delegate_to"] = ["agent.remediation"]
    chain.d.max_depth = 1
    e = chain.delegate(chain.start("web", "cred-web", "agent.incident-intel", sso="sso-maya"), "agent.remediation")
    with pytest.raises(TrustError, match="depth"):
        chain.delegate(e, "agent.incident-intel")


def test_confused_deputy_denied(chain):
    callee = chain.delegate(chain.start("cicd", "cred-ci", "agent.release-guard"), "agent.incident-intel")
    d = chain.call(callee, ReleaseGuard().ask_incident_intel_to_roll_back())
    assert d.effect == "DENY" and d.rule == "P1-missing-scope"


def test_rollback_needs_an_approval_from_a_human_commander(chain):
    ex = chain.start("event", "cred-monitoring", "agent.incident-intel")
    d = chain.call(ex, IncidentIntel().remediate())
    assert d.effect == "REQUIRE_APPROVAL"
    assert not chain.approve(d.approval_id, "agent.incident-intel")[0]
    assert not chain.approve(d.approval_id, "sre.maya")[0]
    assert not chain.approve(d.approval_id, "ic.dev", "0" * 64)[0]
    assert chain.approve(d.approval_id, "ic.dev")[0]
    assert chain.call(ex, IncidentIntel().remediate(), approval_id=d.approval_id).effect == "EXECUTED"
    assert chain.call(ex, IncidentIntel().remediate(), approval_id=d.approval_id).effect == "REJECTED"   # consumed once


def test_token_bound_to_its_workload(chain):
    ex = chain.start("event", "cred-monitoring", "agent.incident-intel")
    other = chain.att.current("spiffe://prod.company.internal/batch-runner")
    assert chain.call(ex, IncidentIntel().investigate()[0], presenter_svid=other).effect == "REJECTED"


def test_tool_credentials_are_audience_bound_and_short(chain):
    ex = chain.delegate(chain.start("web", "cred-web", "agent.incident-intel", sso="sso-maya"), "agent.remediation")
    assert chain.call(ex, Remediation().plan()[0]).effect == "EXECUTED"
    cred = chain.broker.minted[-1]
    assert cred.aud == "kubernetes" and cred.exp - cred.iat == 600
    assert chain.tools["jira"].call(cred, "issue:comment", {})[0] == 401


def test_the_tool_sees_a_capability_identity_not_the_platform(chain):
    ex = chain.start("event", "cred-monitoring", "agent.incident-intel")
    chain.call(ex, IncidentIntel().investigate()[1])
    assert chain.tools["kubernetes"].log[-1]["user.username"] == "system:serviceaccount:payments:release-reader"
