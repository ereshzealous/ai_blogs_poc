"""The real A2A boundary: separate OS processes, official SDK, Agent Card discovery, Bearer auth, trace propagation,
and what a SIGKILL does to an in-flight task."""

from __future__ import annotations

import asyncio
import json

import pytest

from coord.a2a_link import A2ALink, DelegationError
from coord.supervisor import Supervisor

pytestmark = [pytest.mark.a2a, pytest.mark.mcp]


def payload(wf: str, dlg: str, agent: str = "diagnosis") -> dict:
    return {"workflow_id": wf, "delegation_id": dlg, "agent": agent, "objective": "diagnose", "authorize_execution": False, "inputs": [],
            "incident": {"id": "INC-4917", "service": "checkout-api", "environment": "production", "alert": "latency"}}


@pytest.fixture
async def agents(session, home):
    sup = Supervisor(home, env={"C1_SCRIPTED": "1"})
    sup.start("diagnosis")
    await sup.ready("diagnosis")
    link = A2ALink()
    session.world.reset("B1")
    yield sup, link
    sup.stop_all()
    await link.close()


def token(session, wf: str, dlg: str, target: str = "agent.diagnosis") -> str:
    if not session.store.workflow(wf):
        session.store.create_workflow(workflow_id=wf, arch="C", fixture_id="B1", status="RUNNING", started=0)
    root = session.tokens.issue_root(subject="alice", invoker="svc.incident-console", actor="agent.coordinator", wf=wf)
    return session.tokens.encode(session.tokens.exchange(root, target=target, dlg=dlg))


async def test_agent_card_declares_bearer_auth_and_a_skill(agents):
    _, link = agents
    card = await link.card("diagnosis")
    assert card["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC" and card["supportedInterfaces"][0]["protocolVersion"] == "1.0"
    assert card["securitySchemes"]["bearer"]["httpAuthSecurityScheme"]["scheme"] == "Bearer"
    assert card["skills"][0]["id"] == "incident-diagnosis"


async def test_delegation_round_trip_with_lifecycle_and_artifact(agents, session):
    _, link = agents
    out = await link.delegate("diagnosis", payload("wf-a", "d1"), token(session, "wf-a", "d1"), timeout_s=60, message_id="d1")
    assert out.states[-1] == "TASK_STATE_COMPLETED" and "TASK_STATE_WORKING" in out.states
    assert out.out["kind"] == "diagnosis" and out.out["server_ms"] <= out.client_ms
    assert out.req_bytes > 0 and out.resp_bytes > 0
    calls = session.store.calls("wf-a")
    assert calls and calls[0]["component"] == "agent.diagnosis"
    assert calls[0]["actor_chain"] == "agent.diagnosis <- agent.coordinator <- svc.incident-console <- alice"


async def test_token_for_another_agent_is_rejected(agents, session):
    _, link = agents
    with pytest.raises(DelegationError) as e:
        await link.delegate("diagnosis", payload("wf-b", "d1"), token(session, "wf-b", "d1", target="agent.review"), timeout_s=60, message_id="d1")
    assert e.value.kind == "rejected" and session.store.calls("wf-b") == []


async def test_killed_agent_loses_its_task_and_a_restart_does_not_resume_it(agents, session):
    sup, link = agents
    out = await link.delegate("diagnosis", payload("wf-k", "d1"), token(session, "wf-k", "d1"), timeout_s=60, message_id="d1")
    assert await link.get_task("diagnosis", out.task_id) == "TASK_STATE_COMPLETED"
    sup.kill("diagnosis")
    with pytest.raises(DelegationError) as e:
        await link.delegate("diagnosis", payload("wf-k", "d2"), token(session, "wf-k", "d2"), timeout_s=10, message_id="d2")
    assert e.value.kind == "transport"
    info = await sup.ensure("diagnosis")
    assert info["restarted"] and info["new_pid"] != info["old_pid"]
    assert (await link.get_task("diagnosis", out.task_id)).startswith("error:")   # InMemoryTaskStore: the task is gone


async def test_trace_continues_across_the_process_boundary(agents, session, home):
    from coord.telemetry import current_ids, span
    _, link = agents
    with span("test.root"):
        tid, _ = current_ids()
        await link.delegate("diagnosis", payload("wf-t", "d1"), token(session, "wf-t", "d1"), timeout_s=60, message_id="d1")
    await asyncio.sleep(0.3)
    spans = [json.loads(line) for f in (home / "traces").glob(f"{tid}.*.jsonl") for line in f.read_text().splitlines()]
    services = {s["service"] for s in spans}
    assert "agent.diagnosis" in services and len({s["pid"] for s in spans}) >= 2
