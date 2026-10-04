import asyncio
from contextlib import AsyncExitStack

import pytest

from monolith.incident_agent import IncidentAgent

pytestmark = pytest.mark.mcp


def test_monolith_gates_production_writes_in_code(world, tmp_path):
    asked = []

    async def refuse(tool, args):
        asked.append(tool)
        return False

    async def go():
        agent = IncidentAgent(session_id="t", approver=refuse, workdir=tmp_path, world_db=world.path)
        async with AsyncExitStack() as stack:
            await agent._connect(stack)
            out = await agent._execute_tool("rollback_release", {"service": "checkout-api", "environment": "production", "to_release": "rel-2030"})
            read = await agent._execute_tool("get_incident", {"incident_id": "INC-4917"})
        await agent.aclose()
        return out, read

    out, read = asyncio.run(go())
    assert asked == ["rollback_release"] and "not approved" in out and world.executions() == []
    assert "INC-4917" in read


def test_monolith_does_not_retry_a_timed_out_write(world, tmp_path):
    world.arm_fault("rollback_release", "lose_response", 3, 1)

    async def ok(tool, args):
        return True

    async def go():
        agent = IncidentAgent(session_id="t", approver=ok, workdir=tmp_path, world_db=world.path)
        import monolith.incident_agent as m
        m.TOOL_TIMEOUT_S = 1.0
        async with AsyncExitStack() as stack:
            await agent._connect(stack)
            out = await agent._execute_tool("rollback_release", {"service": "checkout-api", "environment": "production", "to_release": "rel-2030"})
        await agent.aclose()
        m.TOOL_TIMEOUT_S = 5.0
        return out

    out = asyncio.run(go())
    assert out.startswith("Error") and len(world.executions("rollback_release")) == 1   # it happened; the agent was told it failed
