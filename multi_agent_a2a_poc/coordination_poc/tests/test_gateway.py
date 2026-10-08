"""The capability gateway over real MCP stdio servers: evidence refs, approval bound to a digest, idempotent retry owned
by the workflow, denials that never reach a system.  Same code in every architecture and every process."""

from __future__ import annotations

import pytest

from coord.gateway import CallContext, Denied
from coord.util import digest

pytestmark = pytest.mark.mcp


def _wf(session, wf: str, idem: str = "workflow"):
    session.store.create_workflow(workflow_id=wf, arch="T", fixture_id="B1", status="RUNNING", started=0, idempotency=idem)
    root = session.tokens.issue_root(subject="alice", invoker="svc.incident-console", actor="agent.incident-solo", wf=wf)
    return session.tokens.exchange(root, target="gateway"), CallContext(wf, "test", "production")


async def test_read_returns_evidence_ref_and_is_audited(session):
    session.world.reset("B1")
    tok, ctx = _wf(session, "wf-r")
    out = await session.gateway.call(tok, "list_deployments", {"service": "checkout-api", "environment": "production"}, ctx)
    assert out["evidence_ref"].startswith("ev-") and out["result"]["running"] == "rel-2031"
    row = session.store.calls("wf-r")[0]
    assert (row["effect"], row["outcome"], row["evidence_ref"]) == ("ALLOW", "ok", out["evidence_ref"])
    assert row["actor_chain"] == "agent.incident-solo <- svc.incident-console <- alice"


async def test_write_is_approved_against_its_digest(session):
    session.world.reset("B1")
    tok, ctx = _wf(session, "wf-w")
    args = {"service": "checkout-api", "environment": "production", "to_release": "rel-2030"}
    await session.gateway.call(tok, "rollback_release", args, ctx)
    row = [c for c in session.store.calls("wf-w") if c["kind"] == "write"][0]
    apr = session.store.one("SELECT * FROM approvals WHERE approval_id=?", (row["approval_id"],))
    assert apr["digest"] == digest({"wf": "wf-w", "capability": "rollback_release", "args": args})
    assert session.world.healthy("checkout-api")


async def test_retry_of_the_same_write_executes_once(session):
    session.world.reset("B1")
    tok, ctx = _wf(session, "wf-i")
    args = {"service": "checkout-api", "environment": "production", "to_release": "rel-2030"}
    await session.gateway.call(tok, "rollback_release", args, ctx)
    second = await session.gateway.call(tok, "rollback_release", args, ctx)
    assert second["result"].get("idempotent_replay") is True
    assert len(session.world.executions()) == 1 and session.world.replays() == 1


async def test_without_workflow_idempotency_the_retry_executes_twice(session):
    """The negative control for E6."""
    session.world.reset("B1")
    tok, ctx = _wf(session, "wf-n", idem="off")
    args = {"service": "checkout-api", "environment": "production", "to_release": "rel-2030"}
    await session.gateway.call(tok, "rollback_release", args, ctx)
    await session.gateway.call(tok, "rollback_release", args, ctx)
    assert len(session.world.executions()) == 2


async def test_denied_write_never_reaches_the_world(session):
    session.world.reset("B7")
    tok, ctx = _wf(session, "wf-d")
    with pytest.raises(Denied):
        await session.gateway.call(tok, "flush_sessions", {"service": "session-cache", "environment": "production"}, ctx)
    assert session.world.executions() == []
    assert session.store.calls("wf-d")[0]["rule"] == "P4-no-session-flush"


async def test_token_for_another_workflow_is_refused(session):
    session.world.reset("B1")
    tok, _ = _wf(session, "wf-x")
    with pytest.raises(Denied):
        await session.gateway.call(tok, "get_incident", {"incident_id": "INC-4917"}, CallContext("wf-other", "t", "production"))
