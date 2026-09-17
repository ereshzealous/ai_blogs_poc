"""End-to-end INC-4917 runs against the local Ollama models and real MCP servers.

These are slow (a gpt-oss:20b investigation takes about two to three minutes on a laptop).
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import time

import anyio
import pytest
from fastapi.testclient import TestClient

from tests.conftest import lap

pytestmark = [pytest.mark.ollama, pytest.mark.mcp]


def _only_workflow(db) -> str:
    rows = sqlite3.connect(db).execute("SELECT id FROM workflows").fetchall()
    assert len(rows) == 1, rows
    return rows[0][0]


def _poll(client, wf, statuses, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = client.get(f"/v1/workflows/{wf}").json()
        if v["status"] in statuses:
            return v
        time.sleep(2)
    raise AssertionError(f"{wf} never reached {statuses}: {v['status']}")


def test_inc4917_end_to_end_over_rest(platform_env, monkeypatch):
    from agent_platform.channels.rest import create_app

    monkeypatch.setenv("LAP_RECOVER_ON_START", "0")
    world = platform_env["world"]
    with TestClient(create_app()) as client:
        r = client.post("/v1/incidents/INC-4917/investigations", headers={"X-User-Id": "alice"},
                        json={"request": "Checkout API latency increased after the 10:15 production deployment. "
                                         "Investigate, recommend the safest remediation, apply it once approved, update the incident."})
        wf = r.json()["workflow_id"]
        waiting = _poll(client, wf, {"WAITING_APPROVAL", "FAILED"})
        assert waiting["status"] == "WAITING_APPROVAL", waiting
        assert world.call_count("source_control.rollback_release") == 0  # nothing happens before approval
        assert client.post(f"/v1/workflows/{wf}/approvals", headers={"X-User-Id": "bob"}, json={"approve": True}).status_code == 403
        assert client.post(f"/v1/workflows/{wf}/approvals", headers={"X-User-Id": "alice"}, json={"approve": True}).status_code == 202
        done = _poll(client, wf, {"COMPLETED", "FAILED"})
        assert done["status"] == "COMPLETED", done
        report = client.app.state.svc.evaluate(wf, backend_rollbacks=len(world.executions("source_control.rollback_release")))
        print(json.dumps(report, indent=1))
        assert report["ok"], report
        spans = client.get(f"/v1/workflows/{wf}/trace").json()
        names = {s["name"].split(" ")[0] for s in spans}
        assert {"invoke_workflow", "invoke_agent", "chat", "execute_tool", "policy.evaluate", "checkpoint.save"} <= names
        assert len({s["trace_id"] for s in spans}) == 1


def test_crash_while_waiting_and_crash_after_the_rollback(platform_env):
    env, world, db = platform_env["env"], platform_env["world"], platform_env["tmp"] / "platform.db"
    r = lap("run", "INC-4917", "--as", "alice", env={**env, "LAP_CRASH_ON": "after_step:await_approval"})
    assert r.returncode == -signal.SIGKILL, r.stderr[-800:]
    wf = _only_workflow(db)

    status = json.loads(lap("--json", "status", wf, env=env).stdout)
    assert status["status"] == "WAITING_APPROVAL" and status["approval"]["status"] == "PENDING"

    r = lap("approve", wf, "--as", "alice", env={**env, "LAP_CRASH_ON": "executed:source_control.rollback_release"})
    assert r.returncode == -signal.SIGKILL, r.stderr[-800:]
    assert len(world.executions("source_control.rollback_release")) == 1
    assert json.loads(lap("--json", "status", wf, env=env).stdout)["status"] == "RUNNING"  # the worker died mid-step

    done = json.loads(lap("--json", "resume", wf, env=env).stdout)
    assert done["status"] == "COMPLETED", done
    assert done["remediation"]["replayed"] is True
    assert len(world.executions("source_control.rollback_release")) == 1  # never rolled back twice
    events = sqlite3.connect(db).execute("SELECT DISTINCT pid FROM workflow_events WHERE workflow_id=?", (wf,)).fetchall()
    assert len(events) >= 3  # three different processes worked on one workflow


def test_crash_inside_a_lost_write_is_replayed_by_the_backend(platform_env):
    env, world, db = platform_env["env"], platform_env["world"], platform_env["tmp"] / "platform.db"
    r = lap("run", "INC-4917", "--as", "alice", env=env)
    assert r.returncode == 0, r.stderr[-800:]
    wf = _only_workflow(db)
    world.arm_fault("source_control.rollback_release", "lose_response", times=1, delay_s=6)
    r = lap("approve", wf, "--as", "alice", env={**env, "LAP_CRASH_ON": "timeout:source_control.rollback_release"})
    assert r.returncode == -signal.SIGKILL, r.stderr[-800:]
    time.sleep(7)  # let the orphaned server finish its delayed reply
    assert len(world.executions("source_control.rollback_release")) == 1  # the write happened before the crash

    done = json.loads(lap("--json", "resume", wf, env=env).stdout)
    assert done["status"] == "COMPLETED", done
    assert done["remediation"]["replayed"] is True
    assert world.replay_count("source_control.rollback_release") == 1
    assert len(world.executions("source_control.rollback_release")) == 1


def test_model_swap_is_configuration(platform_env, monkeypatch):
    """Same code, different model: the platform runs qwen3:8b through config alone."""
    from agent_platform.contracts import StartInvestigation
    from agent_platform.service import PlatformService

    monkeypatch.setenv("LAP_MODEL_REASONING", "qwen3:8b")
    monkeypatch.setenv("LAP_MODEL_SUMMARY", "qwen3:8b")

    async def run():
        async with PlatformService.open() as svc:
            try:
                view = await svc.start_investigation(StartInvestigation(
                    incident_id="INC-4917", request="Checkout latency rose after the 10:15 deploy. Investigate.",
                    user_id="alice", channel="cli"))
            except Exception as exc:  # a weaker model may fail a step; the platform must fail cleanly
                view = {"status": "FAILED", "error": str(exc), "workflow_id": svc.workflows()[0]["workflow_id"]}
            return view, svc.model_usage(view["workflow_id"])

    view, usage = anyio.run(run)
    print(json.dumps({"status": view["status"], "diagnosis": view.get("diagnosis")}, indent=1))
    assert usage and {u["model"] for u in usage} <= {"qwen3:8b", "gpt-oss:20b"}
    assert any(u["model"] == "qwen3:8b" for u in usage)
    assert view["status"] in {"WAITING_APPROVAL", "FAILED"}
