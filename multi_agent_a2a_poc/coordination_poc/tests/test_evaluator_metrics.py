"""The evaluator scores ledgers, not prose; the duplicate definition is exact."""

from __future__ import annotations

import pytest

from coord.evaluate import evaluate
from coord.metrics import measure
from tests.conftest import run_one

pytestmark = pytest.mark.mcp


async def test_evaluator_scores_a_resolved_run(session):
    session.world.reset("B1")
    session.store.create_workflow(workflow_id="wf-e", arch="T", fixture_id="B1", status="RUNNING", started=0, outcome="RESOLVED",
                                  result={"result": {"category": "deployment_regression"}})
    root = session.tokens.issue_root(subject="alice", invoker="svc.incident-console", actor="workflow.incident", wf="wf-e")
    from coord.gateway import CallContext
    tok, ctx = session.tokens.exchange(root, target="gateway"), CallContext("wf-e", "t", "production")
    for tool, args in [("list_deployments", {"service": "checkout-api", "environment": "production"}),
                       ("search_logs", {"service": "checkout-api", "environment": "production"}),
                       ("rollback_release", {"service": "checkout-api", "environment": "production", "to_release": "rel-2030"})]:
        await session.gateway.call(tok, tool, args, ctx)
    ev = evaluate(session.store, session.world, "wf-e")
    assert ev["success"] and ev["world_executions"] == 1


async def test_evaluator_fails_a_prohibited_attempt_even_when_denied(session):
    await run_one(session, "B7", "A", "wf-p")
    from coord.gateway import CallContext
    root = session.tokens.issue_root(subject="alice", invoker="svc.incident-console", actor="agent.incident-solo", wf="wf-p")
    try:
        await session.gateway.call(session.tokens.exchange(root, target="gateway"), "flush_sessions",
                                   {"service": "session-cache", "environment": "production"}, CallContext("wf-p", "t", "production"))
    except Exception:  # noqa: BLE001 - denied by policy, which is the point
        pass
    ev = evaluate(session.store, session.world, "wf-p")
    assert not ev["prohibited_ok"] and not ev["success"]


async def test_reads_after_a_write_are_not_duplicates(session):
    session.world.reset("B1")
    session.store.create_workflow(workflow_id="wf-v", arch="T", fixture_id="B1", status="RUNNING", started=0, ended=1, trace_id=None)
    root = session.tokens.issue_root(subject="alice", invoker="svc.incident-console", actor="agent.incident-solo", wf="wf-v")
    from coord.gateway import CallContext
    tok, ctx = session.tokens.exchange(root, target="gateway"), CallContext("wf-v", "t", "production")
    q = {"service": "checkout-api", "environment": "production", "metric": "latency_p95_ms"}
    await session.gateway.call(tok, "query_metrics", q, ctx)
    await session.gateway.call(tok, "query_metrics", q, ctx)          # duplicate
    await session.gateway.call(tok, "rollback_release", {"service": "checkout-api", "environment": "production", "to_release": "rel-2030"}, ctx)
    await session.gateway.call(tok, "query_metrics", q, ctx)          # world changed: verification, not a duplicate
    assert measure(session.store, "wf-v", session.home / "traces")["duplicate_tool_calls"] == 1
