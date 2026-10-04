import asyncio
import json

import pytest

from layered_platform.contracts import ActionContext, ApprovalDecision, StartRequest
from layered_platform.evals.checks import evaluate
from layered_platform.experience import render
from layered_platform.service import PlatformService
from layered_platform.tools.gateway import ActionDenied, ApprovalRequired
from layered_platform.tools.toolbox import ReadOnlyToolbox
from tests.fakes import ScriptedModel

pytestmark = pytest.mark.mcp
ROLLBACK = {"service": "checkout-api", "environment": "production", "to_release": "rel-2030"}


def run(coro):
    return asyncio.run(coro)


def test_gateway_reads_blocks_unapproved_writes_and_keys_approved_ones(world, tmp_path):
    async def go():
        async with PlatformService.open(tmp_path / "p", str(world.path)) as svc:
            ctx = ActionContext(workflow_id="wf1", step="execute", principal="sre.alice")
            assert (await svc.gateway.execute("incident.get", {"incident_id": "INC-4917"}, ctx))["id"] == "INC-4917"
            with pytest.raises(ApprovalRequired):
                await svc.gateway.execute("deploy.rollback", ROLLBACK, ctx)
            assert world.executions("rollback_release") == []
            req = svc.approvals.request("wf1", "deploy.rollback", ROLLBACK, "sre.alice", "incident-commander")
            svc.approvals.decide(req["id"], "ic.bob", True)
            granted = ctx.model_copy(update={"approval_id": req["id"]})
            await svc.gateway.execute("deploy.rollback", ROLLBACK, granted)
            await svc.gateway.execute("deploy.rollback", ROLLBACK, granted)       # same step again: platform dedup
            ex = world.executions("rollback_release")
            assert len(ex) == 1 and ex[0]["idempotency_key"].startswith("op-")
            rows = [dict(r) for r in svc.db.execute("SELECT outcome FROM tool_calls WHERE capability='deploy.rollback'")]
            assert [r["outcome"] for r in rows] == ["ok", "deduplicated_by_platform"]
    run(go())


def test_unregistered_write_is_denied_before_any_mcp_call(world, tmp_path):
    async def go():
        async with PlatformService.open(tmp_path / "p", str(world.path)) as svc:
            with pytest.raises(ActionDenied):
                await svc.gateway.execute("deploy.flush_sessions", {"service": "checkout-api", "environment": "production"},
                                          ActionContext(workflow_id="wf", step="x", principal="sre.alice"))
            assert not any(c["tool"] == "flush_sessions" for c in world.calls())
    run(go())


def test_agent_toolbox_is_read_only_and_hides_idempotency_keys(world, tmp_path):
    async def go():
        async with PlatformService.open(tmp_path / "p", str(world.path)) as svc:
            ctx = ActionContext(workflow_id="wf", step="investigate", principal="sre.alice")
            box = ReadOnlyToolbox(svc.gateway, ["deploy.history", "telemetry.metrics", "deploy.rollback"], ctx)
            names = {d["function"]["name"] for d in box.definitions()}
            assert names == {"deploy_history", "telemetry_metrics"}
            assert all("idempotency_key" not in json.dumps(d) for d in box.definitions())
            assert (await box.call("deploy_rollback", ROLLBACK)).startswith("Error")
    run(go())


def test_full_workflow_pauses_for_approval_then_completes(world, tmp_path):
    async def go():
        async with PlatformService.open(tmp_path / "p", str(world.path)) as svc:
            svc.workflow.model = ScriptedModel()
            v = await svc.start(StartRequest(incident_id="INC-4917", requested_by="sre.alice", request_id="r1"))
            assert v.status == "WAITING_APPROVAL" and v.policy["rule"] == "P3-high-risk-production-write"
            assert world.executions("rollback_release") == []
            chat = render.chat(v)
            assert any(b["type"] == "actions" for b in chat["blocks"])
            again = await svc.start(StartRequest(incident_id="INC-4917", requested_by="sre.alice", request_id="r1"))
            assert again.workflow_id == v.workflow_id                     # a repeated request is the same workflow
            done = await svc.approve(ApprovalDecision(workflow_id=v.workflow_id, decided_by="ic.bob", approve=True))
            assert done.status == "COMPLETED" and "Root cause" in render.text(done)
            checks = evaluate(done.report, world, True)
            assert all(checks.values()), checks
    run(go())


def test_rejection_is_recorded_and_nothing_executes(world, tmp_path):
    async def go():
        async with PlatformService.open(tmp_path / "p", str(world.path)) as svc:
            svc.workflow.model = ScriptedModel()
            v = await svc.start(StartRequest(incident_id="INC-4917", requested_by="sre.alice", request_id="r2"))
            done = await svc.approve(ApprovalDecision(workflow_id=v.workflow_id, decided_by="ic.bob", approve=False, reason="not now"))
            assert done.status == "COMPLETED" and done.approval["status"] == "REJECTED"
            assert world.executions("rollback_release") == [] and world.incident_doc()["status"] == "investigating"
    run(go())
