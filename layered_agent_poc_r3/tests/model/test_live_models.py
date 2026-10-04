"""Live model tests (Ollama).  Slow; skipped when the model is not installed."""

import asyncio

import pytest

from layered_platform.contracts import ApprovalDecision, RemediationProposal, StartRequest
from layered_platform.evals.checks import evaluate
from layered_platform.models.gateway import ModelGateway
from layered_platform.service import PlatformService
from layered_platform.storage.db import connect
from monolith.incident_agent import IncidentAgent
from tests.conftest import need_model

pytestmark = [pytest.mark.model, pytest.mark.mcp]


@need_model("gpt-oss:20b")
def test_layered_end_to_end_with_gpt_oss(world, tmp_path):
    async def go():
        async with PlatformService.open(tmp_path / "p", str(world.path)) as svc:
            v = await svc.start(StartRequest(incident_id="INC-4917", requested_by="sre.alice", request_id="live-1"))
            assert v.status == "WAITING_APPROVAL"
            return await svc.approve(ApprovalDecision(workflow_id=v.workflow_id, decided_by="ic.bob", approve=True))

    done = asyncio.run(go())
    checks = evaluate(done.report, world, True)
    assert done.status == "COMPLETED" and checks["rollback_exactly_once"] and checks["verified_recovery"], checks


@need_model("gpt-oss:20b")
def test_monolith_end_to_end_with_gpt_oss(world, tmp_path):
    async def yes(tool, args):
        return True

    async def go():
        agent = IncidentAgent(session_id="live", approver=yes, workdir=tmp_path, world_db=world.path)
        try:
            return await agent.run("Investigate INC-4917 and remediate it safely.")
        finally:
            await agent.aclose()

    report = asyncio.run(go())
    assert world.running("checkout-api", "production") == "rel-2030" and "root cause" in report.lower()


@need_model("qwen3:8b")
def test_model_b_serves_a_structured_route(tmp_path):
    spec = {"provider": {"kind": "ollama", "url": "http://localhost:11434", "timeout_s": 300}, "routes": {"structured": {"profile": "q"}},
            "profiles": {"q": {"model": "qwen3:8b", "think": False, "options": {"temperature": 0, "seed": 7}}}, "budget": {}}

    async def go():
        gw = ModelGateway(connect(tmp_path / "p.db"), spec)
        try:
            msg = [{"role": "user", "content": "Propose rolling back checkout-api in production to rel-2030. JSON only."}]
            return await gw.generate("structured", msg, schema=RemediationProposal.model_json_schema(), caller="test")
        finally:
            await gw.close()

    reply = asyncio.run(go())
    assert RemediationProposal.model_validate_json(reply.content).action == "rollback_release"
