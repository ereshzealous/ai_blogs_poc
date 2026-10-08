"""Authority only narrows across a hop; delegation edges, depth, audience, expiry and signatures are enforced."""

from __future__ import annotations

import pytest

from coord.identity import AuthError, TokenService

T = TokenService()


def coord_root():
    return T.issue_root(subject="alice", invoker="svc.incident-console", actor="agent.coordinator", wf="wf-1")


def test_root_scopes_are_an_intersection():
    root = T.issue_root(subject="alice", invoker="svc.incident-console", actor="agent.incident-solo", wf="wf-1")
    assert "write:rollback" in root.scope and root.chain() == "agent.incident-solo <- svc.incident-console <- alice"


def test_delegation_narrows_to_target_and_request():
    t = T.exchange(coord_root(), target="agent.remediation", requested=["read:deploy", "write:rollback"], dlg="d1")
    assert t.scope == ["read:deploy", "write:rollback"]          # remediation may hold every write; this delegation gets one
    e = T.exchange(coord_root(), target="agent.evidence", requested=["read:deploy", "write:rollback"], dlg="d2")
    assert e.scope == ["read:deploy"]                             # write is never the evidence agent's to have
    assert t.chain() == "agent.remediation <- agent.coordinator <- svc.incident-console <- alice"
    assert t.depth == 1 and t.dlg == "d1"


def test_review_never_gets_write_authority_even_if_requested():
    t = T.exchange(coord_root(), target="agent.review", requested=["write:rollback", "read:deploy"])
    assert t.scope == ["read:deploy"]


def test_coordinator_has_no_tool_authority():
    assert T.exchange(coord_root(), target="gateway").scope == []


def test_gateway_token_cannot_widen():
    t = T.exchange(coord_root(), target="agent.remediation", requested=["read:deploy"], dlg="d1")
    assert T.exchange(t, target="gateway").scope == ["read:deploy"]


def test_delegation_edges_enforced():
    t = T.exchange(coord_root(), target="agent.diagnosis")
    with pytest.raises(AuthError):
        T.exchange(t, target="agent.remediation")                 # diagnosis may not delegate onward


def test_audience_signature_and_expiry():
    t = T.exchange(coord_root(), target="agent.diagnosis")
    raw = T.encode(t)
    assert T.decode(raw, audience="agent.diagnosis").scope == t.scope
    with pytest.raises(AuthError):
        T.decode(raw, audience="agent.remediation")
    body, sig = raw.split(".")
    with pytest.raises(AuthError):
        T.decode(body + "." + sig[:-2] + "AA", audience="agent.diagnosis")
    with pytest.raises(AuthError):
        T.decode(raw, audience="agent.diagnosis", now=t.exp + 1)
