"""The incident agent's evidence guard, end to end: a scripted model, the real gateway and real MCP servers."""

from __future__ import annotations

import yaml
import pytest

from agent.incident_agent import run_incident_agent
from agent.llm import LLMResponse, ToolCall
from control_plane.discovery.pipeline import DiscoveryService
from control_plane.gateway.gateway import Gateway, InvocationContext
from control_plane.paths import CATALOG_DIR, REPO_ROOT
from servers.common.world import World

pytestmark = [pytest.mark.mcp, pytest.mark.anyio]
SCENARIOS = {s["id"]: s for s in yaml.safe_load((REPO_ROOT / "benchmark" / "golden" / "agent_scenarios.yaml").read_text())["scenarios"]}
PROD = {"service": "checkout-api", "environment": "production"}
DEPLOYMENTS = ("source_control__search_deployments", {**PROD, "limit": 5})
DIFF = ("source_control__get_diff", {"sha": "a91f3c2"})
POOL = ("database__get_connection_pool_stats", dict(PROD))
ROLLBACK = ("source_control__rollback_release", {**PROD, "to_version": "v4.16"})
HEALTH = ("observability__get_service_health", dict(PROD))


class ScriptedModel:
    """Stands in for the LLM: returns scripted tool calls, then a final answer, and records what it was shown."""

    model = "scripted"

    def __init__(self, *script):
        self.script = list(script)
        self.tool_counts: list[int] = []
        self.transcripts: list[list[dict]] = []

    def model_info(self):
        return {"provider": "scripted"}

    def chat(self, messages, tools=None, options=None):
        self.tool_counts.append(len(tools or []))
        self.transcripts.append([dict(m) for m in messages])
        item = self.script.pop(0) if self.script else ("FINAL", "FINAL: nothing more to do.")
        if item[0] == "FINAL":
            return LLMResponse(item[1], [], 100, 10, 1.0)
        return LLMResponse("", [ToolCall(item[0], dict(item[1]))], 100, 10, 1.0)


async def approve_rollback(req, decision):
    return req.tool_id == "source_control.rollback_release"


async def run(tmp_path, registry, policy, oncall, scenario, *script, guard="evidence", max_steps=16):
    model = ScriptedModel(*script)
    db = tmp_path / "world.sqlite"
    async with Gateway(CATALOG_DIR / "catalog_50.json", registry, policy, world_db=db) as gw:
        published = {p.tool_id: (p.server, p.tool.name, p.tool.description or "", p.tool.input_schema) for p in gw.tools.values()}
        discovery = DiscoveryService(published, registry, embedder=None)

        def discover(query):
            return [t.replace(".", "__", 1) for t in discovery.control_plane(query, k=5).tool_ids]

        ctx = InvocationContext("t", "t", oncall, "enforce", approve_rollback)
        result = await run_incident_agent(model, gw, SCENARIOS[scenario]["prompt"], ctx, mode="control_plane",
                                          discover=discover, max_steps=max_steps, guard=guard)
    return result, model, World(db).events("t")


async def test_the_guard_sends_the_model_back_when_it_stops_without_evidence(tmp_path, registry, policy, oncall):
    result, model, events = await run(tmp_path, registry, policy, oncall, "S2",
                                      ("FINAL", "FINAL: it was an inefficient query."), DEPLOYMENTS, DIFF, POOL,
                                      ("FINAL", "FINAL: done."))
    assert any(s.status == "guard_continue" for s in result.steps)
    assert any("missing" in m["content"].lower() for m in model.transcripts[1] if m["role"] == "user")
    assert result.complete and result.stopped == "final_answer"
    assert "v4.17" in result.final_answer and "inefficient" not in result.final_answer
    assert result.model_final == "FINAL: done." and result.diagnosis["new_max"] == 10
    assert events == []


async def test_read_only_requests_never_reach_a_backend_write(tmp_path, registry, policy, oncall):
    result, _, events = await run(tmp_path, registry, policy, oncall, "S2", ROLLBACK, DEPLOYMENTS, DIFF, POOL)
    blocked = [s for s in result.steps if s.status == "guard_blocked"]
    assert [s.tool for s in blocked] == ["source_control__rollback_release"]
    assert events == [] and result.complete


async def test_incident_fields_are_rendered_before_they_are_written(tmp_path, registry, policy, oncall):
    update = ("itsm__update_incident", {"incident_id": "INC-4917", "status": "resolved", "severity": "high",
                                         "root_cause": "an inefficient query", "resolution_notes": "Rolled back; latency recovered."})
    result, _, events = await run(tmp_path, registry, policy, oncall, "S1", DEPLOYMENTS, DIFF, POOL, update)
    step = next(s for s in result.steps if s.tool == "itsm__update_incident")
    assert step.status == "executed" and not step.is_error and step.guard == "arguments_rendered"
    fields = next(e["payload"]["fields"] for e in events if e["kind"] == "incident_update")
    assert fields["status"] == "identified" and "v4.17" in fields["root_cause"]
    assert fields["resolution_notes"] is None and fields["severity"] is None
    assert result.complete


async def test_closing_without_verified_recovery_is_blocked(tmp_path, registry, policy, oncall):
    close = ("itsm__close_incident", {"incident_id": "INC-4917", "resolution_code": "rolled_back"})
    result, _, events = await run(tmp_path, registry, policy, oncall, "S1", close, max_steps=3)
    assert result.steps[0].status == "guard_blocked"
    assert not any(e["kind"] == "incident_close" for e in events)


async def test_rollback_then_in_slo_reading_completes_an_action_request(tmp_path, registry, policy, oncall):
    result, _, events = await run(tmp_path, registry, policy, oncall, "S4", DEPLOYMENTS, ROLLBACK, HEALTH)
    assert result.complete and result.verification["p95_ms"] <= result.verification["slo_ms"]
    assert "Recovery check: p95" in result.final_answer
    assert [e["kind"] for e in events] == ["rollback"]


async def test_the_step_limit_yields_an_incomplete_report(tmp_path, registry, policy, oncall):
    result, _, _ = await run(tmp_path, registry, policy, oncall, "S4", HEALTH, HEALTH, max_steps=2)
    assert result.stopped == "max_steps" and not result.complete
    assert "Incomplete" in result.final_answer and "remediation" in result.final_answer


async def test_exposed_tools_stay_bounded_while_evidence_is_gathered(tmp_path, registry, policy, oncall):
    searches = [("find_tools", {"query": q}) for q in ("restart", "logs", "feature flags", "cloud instances", "chat message",
                                                        "service owner", "pods", "alerts")]
    result, model, _ = await run(tmp_path, registry, policy, oncall, "S1", *searches, max_steps=9)
    assert max(model.tool_counts) <= 13  # at most 12 real tools plus find_tools
    assert len(result.steps) == 9


async def test_failed_calls_are_recorded_but_are_not_evidence(tmp_path, registry, policy, oncall):
    bad = ("observability__query_latency", {**PROD, "percentile": "p90"})
    result, _, _ = await run(tmp_path, registry, policy, oncall, "S2", bad, DEPLOYMENTS, DIFF, POOL)
    assert result.steps[0].is_error and result.steps[0].status == "invalid_arguments" and result.steps[0].policy is None
    assert "p90" in result.steps[0].result["message"]
    assert [e["tool_id"] for e in result.evidence] == ["source_control.search_deployments", "source_control.get_diff",
                                                     "database.get_connection_pool_stats"]
    assert "Failed calls, not used as evidence: 1" in result.final_answer


async def test_the_legacy_guard_keeps_the_earlier_behaviour_with_full_results(tmp_path, registry, policy, oncall):
    result, _, _ = await run(tmp_path, registry, policy, oncall, "S2", POOL, ("FINAL", "FINAL: model prose."), guard="legacy")
    assert result.final_answer == "FINAL: model prose." and result.guard == "legacy"
    assert result.steps[0].result["max_connections"] == 10


async def test_an_early_incident_update_is_refreshed_once_the_cause_is_proven(tmp_path, registry, policy, oncall):
    early = ("itsm__update_incident", {"incident_id": "INC-4917", "status": "investigating", "summary": "looking"})
    again = ("itsm__update_incident", {"incident_id": "INC-4917", "status": "identified", "summary": "found it"})
    result, model, events = await run(tmp_path, registry, policy, oncall, "S1", DEPLOYMENTS, early, DIFF, POOL,
                                      ("FINAL", "FINAL: done."), again, ("FINAL", "FINAL: done."))
    pushback = [s for s in result.steps if s.status == "guard_continue"]
    assert pushback and "last updated before the latest evidence" in pushback[-1].result_preview
    updates = [e["payload"]["fields"] for e in events if e["kind"] == "incident_update"]
    assert len(updates) == 2 and updates[0]["root_cause"] is None and "v4.17" in updates[1]["root_cause"]
    assert result.complete and "cause under investigation" not in updates[1]["summary"]


async def test_a_guessed_rollback_version_never_reaches_the_approver(tmp_path, registry, policy, oncall):
    guess = ("source_control__rollback_release", {**PROD, "to_version": "v4.15"})
    result, _, events = await run(tmp_path, registry, policy, oncall, "S4", guess, DEPLOYMENTS, guess, ROLLBACK, HEALTH)
    assert [s.status for s in result.steps if s.tool == "source_control__rollback_release"] == ["guard_blocked", "guard_blocked", "executed"]
    assert [e["kind"] for e in events] == ["rollback"] and result.complete


async def test_repeated_pushback_without_progress_ends_the_run(tmp_path, registry, policy, oncall):
    result, _, _ = await run(tmp_path, registry, policy, oncall, "S4", *[("FINAL", "FINAL: done.")] * 10)
    assert result.stopped == "guard_stalled" and not result.complete
    assert sum(s.status == "guard_continue" for s in result.steps) == 3 and len(result.steps) == 4
    assert "Incomplete" in result.final_answer


async def test_a_rejected_action_is_reported(tmp_path, registry, policy, oncall):
    terminate = ("cloud__terminate_instance", {"instance_id": "i-0c41e7a9d2b3f5812"})
    result, _, events = await run(tmp_path, registry, policy, oncall, "S4", DEPLOYMENTS, terminate, max_steps=3)
    assert result.steps[1].status == "denied" and events == []
    assert "Not executed: cloud.terminate_instance (denied by policy)" in result.final_answer


async def test_an_invented_tool_is_reported_by_its_id(tmp_path, registry, policy, oncall):
    result, _, _ = await run(tmp_path, registry, policy, oncall, "S2", ("ops__fix_everything", {}), max_steps=2)
    assert result.steps[0].status == "unknown_tool"
    assert "Not executed: ops.fix_everything (unknown tool)" in result.final_answer


async def test_an_unrequested_rollback_never_runs(tmp_path, registry, policy, oncall):
    update = ("itsm__update_incident", {"incident_id": "INC-4917", "status": "identified"})
    result, _, events = await run(tmp_path, registry, policy, oncall, "S1", DEPLOYMENTS, ROLLBACK, DIFF, POOL, update)
    assert result.steps[1].status == "guard_blocked"
    assert "rollback" not in [e["kind"] for e in events] and result.complete
    assert "Recommended remediation: roll checkout-api in production back from v4.17 to v4.16" in result.final_answer
