"""The runtime owns workflow truth and termination for every architecture (scripted model, in-process agents)."""

from __future__ import annotations

import json

import pytest

from coord.arch_c import InProcessDelegator
from coord.contracts import ExecutionView
from coord.metrics import measure
from coord.models import ModelReply
from coord.scripted import ScriptedProvider
from coord.specialists import SpecialistEnv
from tests.conftest import run_one

pytestmark = pytest.mark.mcp


def inproc(session):
    session.extras["delegator"] = InProcessDelegator(SpecialistEnv(session.gateway, session.model, session.tokens, session.limits))


async def test_same_contract_for_every_architecture(session):
    inproc(session)
    views = [await run_one(session, "B8", arch, f"wf-{arch}") for arch in ("A", "B", "C")]
    keys = {tuple(sorted(v.model_dump())) for v in views}
    assert len(keys) == 1 and all(isinstance(v, ExecutionView) for v in views)
    assert all(v.intent == "investigate_incident" and v.invoker == "svc.incident-console" for v in views)


async def test_outcome_comes_from_the_ledger_not_the_claim(session):
    """A claims it executed a rollback; nothing executed: the runtime records a state conflict and NOT_EXECUTED."""
    session.model.provider = ScriptedProvider({"IncidentReport": {
        "root_cause": {"category": "deployment_regression", "summary": "s", "affected_service": "checkout-api", "evidence": [], "confidence": "high"},
        "decision": "remediate", "action_taken": {"tool": "rollback_release", "args": {"service": "checkout-api"}}, "rationale": "r"}})
    view = await run_one(session, "B1", "A", "wf-claim")
    assert view.verdict["outcome"] == "NOT_EXECUTED" and view.status == "FAILED"
    res = json.loads(session.store.workflow("wf-claim")["result"])
    assert res["state_conflicts"]


async def test_budget_is_system_level_and_ends_the_workflow(session):
    view = await run_one(session, "B1", "A", "wf-budget", overrides={"workflow": {"max_total_tokens": 500}})
    assert view.verdict["termination"] == "BUDGET_EXCEEDED"


class LoopingCoordinator(ScriptedProvider):
    """Always delegates the same thing: the cycle check must refuse it, then terminate."""

    async def chat(self, messages, tools, schema, seed, caller):
        if tools and any(t["function"]["name"] == "delegate" for t in tools):
            return ModelReply(content="", tool_calls=[{"name": "delegate", "arguments": {"agent": "review", "objective": "check again"}}],
                              model="loop", prompt_tokens=10, completion_tokens=5)
        return await super().chat(messages, tools, schema, seed, caller)


class WanderingCoordinator(ScriptedProvider):
    """Never repeats exactly (new inputs each time) and never finishes: only max_handoffs can stop it."""

    async def chat(self, messages, tools, schema, seed, caller):
        if tools and any(t["function"]["name"] == "delegate" for t in tools):
            n = sum(1 for m in messages if m.get("role") == "tool")
            ids = [f"art-{n}"] if n else []
            return ModelReply(content="", tool_calls=[{"name": "delegate", "arguments": {"agent": ["evidence", "review"][n % 2], "objective": f"step {n}",
                                                                                          "input_artifact_ids": ids}}], model="wander", prompt_tokens=10, completion_tokens=5)
        return await super().chat(messages, tools, schema, seed, caller)


async def test_cycle_detection_terminates_a_delegation_loop(session):
    inproc(session)
    session.model.provider = LoopingCoordinator()
    view = await run_one(session, "B1", "C", "wf-loop")
    assert view.verdict["termination"] == "LOOP_DETECTED"
    m = measure(session.store, "wf-loop", session.home / "traces")
    assert m["cycle_blocks"] == 2 and m["handoffs"] == 1


async def test_max_handoffs_is_enforced_by_the_runtime(session):
    inproc(session)
    session.model.provider = WanderingCoordinator()
    view = await run_one(session, "B1", "C", "wf-hops")
    assert view.verdict["termination"] == "MAX_HANDOFFS"
    assert measure(session.store, "wf-hops", session.home / "traces")["handoffs"] == session.limits["multi_agent_c"]["max_handoffs"]


async def test_without_termination_ownership_only_the_safety_cap_stops_it(session):
    """The E8 ablation's mechanism: no cycle check, no hop limit; the harness's safety cap ends it."""
    inproc(session)
    session.model.provider = LoopingCoordinator()
    view = await run_one(session, "B1", "C", "wf-abl", overrides={"ablation": True})
    assert view.verdict["termination"] == "SAFETY_CAP"
    assert measure(session.store, "wf-abl", session.home / "traces")["handoffs"] == session.limits["ablation_e8"]["safety_cap_handoffs"]


async def test_duplicate_reads_across_agents_are_counted(session):
    inproc(session)
    await run_one(session, "B1", "C", "wf-dup")      # scripted evidence and diagnosis agents both read latency
    m = measure(session.store, "wf-dup", session.home / "traces")
    assert m["duplicate_tool_calls"] >= 1 and m["duplicate_cross_component"] >= 1


class ExecuteWithoutProposal(ScriptedProvider):
    """Asks for an authorized execution without handing over a proposal, then finishes."""

    async def chat(self, messages, tools, schema, seed, caller):
        if tools and any(t["function"]["name"] == "delegate" for t in tools):
            if not any(m.get("role") == "tool" for m in messages):
                return ModelReply(content="", tool_calls=[{"name": "delegate", "arguments": {
                    "agent": "remediation", "objective": "roll it back", "authorize_execution": True}}], model="x", prompt_tokens=10, completion_tokens=5)
            return ModelReply(content="", tool_calls=[{"name": "finish", "arguments": {
                "outcome": "escalated", "root_cause_category": "undetermined", "affected_service": "", "summary": "s"}}], model="x", prompt_tokens=10, completion_tokens=5)
        return await super().chat(messages, tools, schema, seed, caller)


async def test_execute_without_a_proposal_is_refused_fail_closed(session):
    """Regression for DEVIATIONS D3: no proposal -> no delegation, no token, no write authority anywhere."""
    inproc(session)
    session.model.provider = ExecuteWithoutProposal()
    await run_one(session, "B1", "C", "wf-noprop")
    assert session.store.rows("SELECT * FROM delegations WHERE workflow_id='wf-noprop'") == []
    steps = session.store.rows("SELECT kind FROM steps WHERE workflow_id='wf-noprop' AND kind='execute_refused'")
    assert len(steps) == 1
    assert [c for c in session.store.calls("wf-noprop") if c["kind"] == "write"] == []


async def test_scopes_without_a_proposal_never_include_a_write(session):
    from coord.arch_c import Coordinator, WRITE_TOOLS
    from coord.runtime import WorkflowCtx
    ctx = WorkflowCtx(session, "wf-s", "C", {}, "INC", "svc", "production", None, session.limits)
    c = Coordinator(ctx, delegator=None)
    assert not any(s.startswith("write:") for s in c.scopes_for("remediation", True, []))
    prop = [{"kind": "remediation_proposal", "body": {"action": {"tool": "rollback_release", "args": {}}}}]
    assert [s for s in c.scopes_for("remediation", True, prop) if s.startswith("write:")] == ["write:rollback"]
    assert len(WRITE_TOOLS) > 1
    c.execute_without_proposal = "all_writes"  # the as-run fallback of the blind run, kept only for replay
    assert len([s for s in c.scopes_for("remediation", True, []) if s.startswith("write:")]) > 1
