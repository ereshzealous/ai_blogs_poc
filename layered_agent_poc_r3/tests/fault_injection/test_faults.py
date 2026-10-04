import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from layered_platform.contracts import ActionContext, StartRequest
from layered_platform.service import PlatformService
from tests.fakes import ScriptedModel

pytestmark = pytest.mark.mcp
HERE = Path(__file__).parent
ROLLBACK = {"service": "checkout-api", "environment": "production", "to_release": "rel-2030"}


def test_lost_response_after_commit_executes_once(world, tmp_path, monkeypatch):
    monkeypatch.setenv("F2_TOOL_TIMEOUT_S", "1")
    world.arm_fault("rollback_release", "lose_response", 3, 1)

    async def go():
        async with PlatformService.open(tmp_path / "p", str(world.path)) as svc:
            req = svc.approvals.request("wf1", "deploy.rollback", ROLLBACK, "sre.alice", "incident-commander")
            svc.approvals.decide(req["id"], "ic.bob", True)
            ctx = ActionContext(workflow_id="wf1", step="execute", principal="sre.alice", approval_id=req["id"])
            result = await svc.gateway.execute("deploy.rollback", ROLLBACK, ctx)
            outcomes = [r[0] for r in svc.db.execute("SELECT outcome FROM tool_calls ORDER BY seq")]
            return result, outcomes

    result, outcomes = asyncio.run(go())
    assert outcomes == ["timeout", "ok"] and result["idempotent_replay"] is True
    assert len(world.executions("rollback_release")) == 1 and world.replays("rollback_release") == 1


def _proc(workdir, phase, env):
    return subprocess.run([sys.executable, str(HERE / "_layered_proc.py"), str(workdir), phase], env=env, capture_output=True, text=True, timeout=180).returncode


def test_sigkill_after_the_side_effect_resumes_without_repeating_it(world, tmp_path):
    env = dict(os.environ, F2_WORLD_DB=str(world.path), F2_CRASH_MARKER=str(tmp_path / ".crashed"),
               F2_CRASH_AT="after_tool_result:deploy.rollback", PYTHONPATH=str(HERE.parents[1]))
    wd = tmp_path / "p"
    assert _proc(wd, "start", env) == 0
    assert _proc(wd, "approve", env) == -9                       # real SIGKILL, right after the rollback committed
    assert len(world.executions("rollback_release")) == 1
    assert _proc(wd, "recover", env) == 0                        # a new process picks the workflow up
    db = sqlite3.connect(wd / "platform.db")
    status = db.execute("SELECT status FROM workflows").fetchone()[0]
    started = [r[0] for r in db.execute("SELECT step FROM workflow_events WHERE kind='step.started' ORDER BY seq")]
    assert status == "COMPLETED"
    assert len(world.executions("rollback_release")) == 1 and world.replays("rollback_release") == 1
    assert [s for s in set(started) if started.count(s) > 1] == ["execute"]   # only the interrupted step ran twice


def test_crash_between_approval_and_resume_is_recovered(world, tmp_path):
    async def go():
        async with PlatformService.open(tmp_path / "p", str(world.path)) as svc:
            svc.workflow.model = ScriptedModel()
            v = await svc.start(StartRequest(incident_id="INC-4917", requested_by="sre.alice", request_id="r3"))
            rec = svc.store.load(v.workflow_id)
            svc.workflow.decide(v.workflow_id, rec["state"], "ic.bob", True, "")   # decision stored, then "crash"
            assert svc.store.load(v.workflow_id)["status"] == "WAITING_APPROVAL"
            views = await svc.recover()
            return views

    views = asyncio.run(go())
    assert views and views[0].status == "COMPLETED" and len(world.executions("rollback_release")) == 1
