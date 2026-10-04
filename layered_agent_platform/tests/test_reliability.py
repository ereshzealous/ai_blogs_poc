"""Timeouts, bounded retries and idempotent writes through real MCP servers (no model needed)."""

from __future__ import annotations

import json

import anyio
import pytest

from agent_platform.actions.audit import AuditLog
from agent_platform.actions.gateway import ActionGateway
from agent_platform.actions.idempotency import IdempotencyStore
from agent_platform.actions.mcp_pool import McpPool
from agent_platform.actions.policy import PolicyEngine
from agent_platform.actions.registry import CapabilityRegistry
from agent_platform.actions.types import ActionContext, ApprovalGrant, Invocation

pytestmark = pytest.mark.mcp

ROLLBACK = Invocation("source_control.rollback_release",
                      {"service": "checkout-api", "environment": "production", "target_version": "v4.16", "reason": "test"})
CTX = ActionContext("alice", "agent:incident-remediation", "wf-rel", "remediate", "production")


async def with_gateway(env, fn):
    tmp = env["tmp"]
    pool = McpPool(tmp / "enterprise.db")
    registry = CapabilityRegistry()
    gw = ActionGateway(registry, PolicyEngine(registry), pool, IdempotencyStore(tmp / "platform.db"), AuditLog(tmp / "platform.db"))
    await pool.start()
    try:
        return await fn(gw)
    finally:
        await pool.close()


def grant_for(gw: ActionGateway) -> ApprovalGrant:
    d = gw.evaluate(ROLLBACK, CTX)
    return ApprovalGrant(d.digest, "alice", "incident-commander", "2026-09-08T10:41:00Z")


def test_read_timeout_is_retried_with_a_bound(platform_env):
    world = platform_env["world"]
    world.arm_fault("observability.query_latency", "timeout", times=2, delay_s=3)

    async def run(gw):
        return await gw.execute(Invocation("observability.query_latency", {"service": "checkout-api", "environment": "production"}), CTX)

    res = anyio.run(with_gateway, platform_env, run)
    assert res.ok and res.attempts == 3
    assert res.result["p95_ms"] == 2150
    assert world.executions() == []  # a read never mutates the world


def test_read_gives_up_after_its_retry_budget(platform_env):
    platform_env["world"].arm_fault("observability.query_latency", "timeout", times=5, delay_s=3)

    async def run(gw):
        return await gw.execute(Invocation("observability.query_latency", {"service": "checkout-api", "environment": "production"}), CTX)

    res = anyio.run(with_gateway, platform_env, run)
    assert res.status == "failed" and res.attempts == 3


def test_lost_response_on_a_write_does_not_execute_twice(platform_env):
    """The rollback commits, its response is lost, the gateway retries with the same key, the backend replays."""
    world = platform_env["world"]
    world.arm_fault("source_control.rollback_release", "lose_response", times=1, delay_s=4)

    async def run(gw):
        return await gw.execute(ROLLBACK, CTX, operation_id="op-lost-1", grant=grant_for(gw))

    res = anyio.run(with_gateway, platform_env, run)
    assert res.ok and res.attempts == 2 and res.replayed
    assert len(world.executions("source_control.rollback_release")) == 1
    assert world.replay_count("source_control.rollback_release") == 1
    assert world.version("checkout-api", "production") == "v4.16"


def test_monolith_retry_executes_the_same_write_twice(platform_env):
    """Baseline: the monolith retries on timeout without an idempotency key."""
    import os

    from monolith.incident_agent import IncidentAgent

    world = platform_env["world"]
    world.arm_fault("source_control.rollback_release", "lose_response", times=1, delay_s=4)
    os.environ["LAP_ENTERPRISE_DB"] = str(platform_env["tmp"] / "enterprise.db")

    async def run():
        agent = IncidentAgent()
        await agent.connect()
        try:
            return await agent.call_tool("source_control__rollback_release", dict(ROLLBACK.arguments, target_version="v4.16"))
        finally:
            await agent.close()

    out = anyio.run(run)
    assert json.loads(out)["status"] == "succeeded"
    assert world.call_count("source_control.rollback_release") == 2
    assert len(world.executions("source_control.rollback_release")) == 2  # two rollouts, two rounds of pod restarts


def test_same_operation_is_replayed_from_the_platform_record(platform_env):
    world = platform_env["world"]

    async def run(gw):
        g = grant_for(gw)
        first = await gw.execute(ROLLBACK, CTX, operation_id="op-2", grant=g)
        second = await gw.execute(ROLLBACK, CTX, operation_id="op-2", grant=g)  # e.g. a resumed workflow
        return first, second

    first, second = anyio.run(with_gateway, platform_env, run)
    assert first.ok and not first.replayed
    assert second.ok and second.replayed and second.attempts == 0
    assert world.call_count("source_control.rollback_release") == 1


def test_key_reuse_with_different_arguments_is_rejected_by_the_backend(platform_env):
    world = platform_env["world"]
    world.commit_write("source_control.rollback_release", {"service": "checkout-api", "environment": "production",
                                                           "target_version": "v4.15", "reason": "x", "idempotency_key": "op-3"},
                       {"status": "succeeded"})

    async def run(gw):
        return await gw.execute(ROLLBACK, CTX, operation_id="op-3", grant=grant_for(gw))

    res = anyio.run(with_gateway, platform_env, run)
    assert res.status == "failed" and "different arguments" in res.error


def test_high_risk_write_needs_a_grant_for_this_exact_invocation(platform_env):
    world = platform_env["world"]

    async def run(gw):
        none = await gw.execute(ROLLBACK, CTX, operation_id="op-4")
        wrong = await gw.execute(ROLLBACK, CTX, operation_id="op-4",
                                 grant=ApprovalGrant("0" * 20, "alice", "incident-commander", "now"))
        return none, wrong

    none, wrong = anyio.run(with_gateway, platform_env, run)
    assert none.status == wrong.status == "approval_required"
    assert world.call_count("source_control.rollback_release") == 0


def test_denied_action_never_reaches_the_backend(platform_env):
    world = platform_env["world"]

    async def run(gw):
        return await gw.execute(Invocation("kubernetes.rollback_deployment",
                                           {"service": "checkout-api", "environment": "production", "revision": 41}), CTX,
                                operation_id="op-5")

    res = anyio.run(with_gateway, platform_env, run)
    assert res.status == "denied" and res.policy.rule_id == "P2-gitops-authoritative"
    assert world.call_count("kubernetes.rollback_deployment") == 0


def test_agent_toolbox_hides_keys_and_blocks_unoffered_tools(platform_env):
    world = platform_env["world"]

    async def run(gw):
        box = gw.toolbox(ActionContext("alice", "agent", "wf-box", "investigate", "production"),
                         ["observability.query_latency"])
        defs = box.definitions()
        obs = await box.call("source_control__rollback_release", ROLLBACK.arguments)
        ok = await box.call("observability__query_latency", {"service": "checkout-api", "environment": "production"})
        return defs, obs, ok

    defs, obs, ok = anyio.run(with_gateway, platform_env, run)
    assert "idempotency_key" not in json.dumps(defs)
    assert obs.startswith("DENIED") and world.call_count("source_control.rollback_release") == 0
    assert json.loads(ok)["p95_ms"] == 2150
