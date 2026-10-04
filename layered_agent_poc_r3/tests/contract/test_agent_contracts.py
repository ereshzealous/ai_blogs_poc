import asyncio

import pytest
from pydantic import ValidationError

from layered_platform.contracts import DiagnosisReport, RemediationProposal
from layered_platform.runtime.agent_loop import AgentFailed, AgentSpec, run_agent
from tests.fakes import ScriptedModel


class FakeTools:
    def __init__(self):
        self.calls = []

    def definitions(self):
        return [{"type": "function", "function": {"name": n, "description": "", "parameters": {"type": "object"}}} for n in ("deploy_history", "telemetry_metrics")]

    async def call(self, name, arguments):
        self.calls.append(name)
        return '{"ok": true}'


def test_rollback_proposal_needs_a_target():
    with pytest.raises(ValidationError):
        RemediationProposal(action="rollback_release", service="checkout-api", environment="production", rationale="x")


def test_proposal_action_is_a_closed_set():
    with pytest.raises(ValidationError):
        RemediationProposal(action="delete_database", service="checkout-api", environment="production", rationale="x")


def test_agent_loop_uses_tools_then_returns_a_validated_contract():
    tools, model = FakeTools(), ScriptedModel()
    spec = AgentSpec(name="diagnostician", route="reasoning", instructions="x")
    out, stats = asyncio.run(run_agent(spec, [{"role": "user", "content": "go"}], model, tools, DiagnosisReport, "wf"))
    assert isinstance(out, DiagnosisReport) and out.suspect_release == "rel-2031"
    assert tools.calls == ["deploy_history", "telemetry_metrics"] and stats["tool_calls"] == 2
    assert model.calls[-1]["schema"] and all(c["route"] == "reasoning" for c in model.calls)


def test_invalid_structured_output_gets_one_repair():
    model = ScriptedModel(bad_first_json=True)
    spec = AgentSpec(name="remediator", route="structured", instructions="x")
    out, stats = asyncio.run(run_agent(spec, [{"role": "user", "content": "go"}], model, None, RemediationProposal, "wf"))
    assert out.target_release == "rel-2030" and stats["repairs"] == 1


def test_agent_fails_closed_when_output_never_validates():
    class Broken(ScriptedModel):
        async def generate(self, *a, **k):
            r = await super().generate(*a, **k)
            r.content = "not json"
            return r

    with pytest.raises(AgentFailed):
        asyncio.run(run_agent(AgentSpec(name="remediator", route="structured", instructions="x"), [], Broken(), None, RemediationProposal, "wf"))
