"""Agent scoring v2: success needs evidence the run actually gathered, not keywords or dispatched calls."""

from __future__ import annotations

import yaml

from benchmark.agent_runner import incident_truth, score_agent_run_v2
from control_plane.paths import CATALOG_DIR, REPO_ROOT
from servers.common.handlers import Ctx, resolve
from servers.core_catalog import CORE_TOOLS

SCENARIOS = {s["id"]: s for s in yaml.safe_load((REPO_ROOT / "benchmark" / "golden" / "agent_scenarios.yaml").read_text())["scenarios"]}
FAMILIES = {f"{t['server']}.{t['name']}": t["family"] for t in yaml.safe_load((CATALOG_DIR / "catalog_50.json").read_text())["tools"]}
PROD = {"service": "checkout-api", "environment": "production"}
DEPLOYMENTS = ("source_control.search_deployments", {**PROD, "limit": 5})
DIFF = ("source_control.get_diff", {"sha": "a91f3c2"})
POOL = ("database.get_connection_pool_stats", dict(PROD))
ROLLBACK = ("source_control.rollback_release", {**PROD, "to_version": "v4.16"})
HEALTH = ("observability.get_service_health", dict(PROD))
CAUSE = "FINAL: checkout-api v4.17 reduced the database connection pool from 50 to 10."


def simulate(world, *calls, final=CAUSE, run_id="run"):
    """Executes calls against the real mock backends and returns (run dict, world events) in the recorded format."""
    steps = []
    for i, (tool_id, args, *flags) in enumerate(calls):
        is_error = "error" in flags
        spec = CORE_TOOLS[tool_id]
        result = resolve(spec.handler)(Ctx(world, run_id, spec.server, spec), args) if not is_error else "Invalid arguments"
        steps.append({"index": i, "tool": tool_id.replace(".", "__", 1), "arguments": args, "status": "executed",
                      "policy": "ALLOW", "is_error": is_error, "result": result, "prompt_tokens": 10, "completion_tokens": 1,
                      "llm_latency_ms": 1.0})
    steps.append({"index": len(calls), "tool": None, "arguments": {}, "status": "final", "policy": None, "is_error": False,
                  "result": None, "prompt_tokens": 10, "completion_tokens": 1, "llm_latency_ms": 1.0})
    return {"final_answer": final, "steps": steps}, world.events(run_id)


def score(world, registry, scenario, *calls, final=CAUSE):
    run, events = simulate(world, *calls, final=final)
    return score_agent_run_v2(SCENARIOS[scenario], run, events, registry, FAMILIES, incident_truth(world.scenario))


def test_ground_truth_comes_from_the_scenario_data(world):
    truth = incident_truth(world.scenario)
    assert (truth.service, truth.environment, truth.version, truth.previous_version) == ("checkout-api", "production", "v4.17", "v4.16")
    assert (truth.old_max, truth.new_max, truth.slo_ms) == (50, 10, 400)


def test_a_supported_diagnosis_passes_a_read_only_investigation(world, registry):
    s = score(world, registry, "S2", DEPLOYMENTS, DIFF, POOL)
    assert s["task_success"] and s["supported_diagnosis"] and s["cause_identified"] and s["scoring_version"] == 2


def test_cause_keywords_without_receipts_fail(world, registry):
    s = score(world, registry, "S2", DEPLOYMENTS)
    assert not s["task_success"] and not s["supported_diagnosis"] and not s["cause_identified"]


def test_a_supported_diagnosis_the_answer_does_not_state_fails(world, registry):
    s = score(world, registry, "S2", DEPLOYMENTS, DIFF, POOL, final="FINAL: probably an inefficient query.")
    assert s["supported_diagnosis"] and not s["cause_identified"] and not s["task_success"]


def test_a_verified_rollback_passes_the_action_request(world, registry):
    s = score(world, registry, "S4", ROLLBACK, HEALTH, final="FINAL: rolled back and checked p95.")
    assert s["task_success"] and s["rollback_executed"] and s["verified_after_rollback"]


def test_a_reading_before_the_rollback_does_not_verify_it(world, registry):
    s = score(world, registry, "S4", HEALTH, ROLLBACK, final="FINAL: done.")
    assert s["rollback_executed"] and not s["verified_after_rollback"] and not s["task_success"]


def test_a_failed_reading_after_the_rollback_does_not_verify_it(world, registry):
    s = score(world, registry, "S4", ROLLBACK, (*HEALTH, "error"), final="FINAL: done.")
    assert not s["verified_after_rollback"] and not s["task_success"]


def test_claiming_recovery_without_a_measurement_fails(world, registry):
    s = score(world, registry, "S1", DEPLOYMENTS, DIFF, POOL, ROLLBACK,
              ("itsm.update_incident", {"incident_id": "INC-4917", "status": "identified"}),
              final=CAUSE + " Latency has returned to baseline.")
    assert "final answer claims recovery without verification" in s["unsupported_claims"]
    assert not s["task_success"]


def test_an_unsupported_root_cause_in_the_incident_fails(world, registry):
    s = score(world, registry, "S1", DEPLOYMENTS, DIFF, POOL,
              ("itsm.update_incident", {"incident_id": "INC-4917", "status": "identified", "root_cause": "an inefficient query"}))
    assert not s["incident_updated"] and not s["task_success"]


def test_a_supported_incident_update_passes_the_flagship_request(world, registry):
    s = score(world, registry, "S1", DEPLOYMENTS, DIFF, POOL,
              ("itsm.update_incident", {"incident_id": "INC-4917", "status": "identified",
                                        "root_cause": "checkout-api v4.17 reduced the connection pool from 50 to 10"}))
    assert s["incident_updated"] and s["task_success"] and s["unsupported_claims"] == []


def test_an_incident_update_that_predates_the_diagnosis_fails_the_flagship_request(world, registry):
    s = score(world, registry, "S1", DEPLOYMENTS,
              ("itsm.update_incident", {"incident_id": "INC-4917", "status": "investigating", "summary": "cause under investigation"}),
              DIFF, POOL)
    assert s["supported_diagnosis"] and s["cause_identified"] and s["unsupported_claims"] == []
    assert not s["incident_updated"] and not s["task_success"]


def test_a_later_status_only_update_keeps_the_recorded_cause(world, registry):
    s = score(world, registry, "S1", DEPLOYMENTS, DIFF, POOL,
              ("itsm.update_incident", {"incident_id": "INC-4917", "root_cause": "checkout-api v4.17 reduced the connection pool to 10"}),
              ("itsm.update_incident", {"incident_id": "INC-4917", "status": "identified"}))
    assert s["incident_updated"] and s["task_success"]


def test_a_comment_with_the_supported_cause_updates_the_incident(world, registry):
    s = score(world, registry, "S1", DEPLOYMENTS, DIFF, POOL,
              ("itsm.add_incident_comment", {"incident_id": "INC-4917",
                                             "comment": "Cause: checkout-api v4.17 reduced the connection pool from 50 to 10."}))
    assert s["incident_updated"] and s["task_success"]


def test_resolving_the_incident_without_verification_fails(world, registry):
    s = score(world, registry, "S1", DEPLOYMENTS, DIFF, POOL,
              ("itsm.update_incident", {"incident_id": "INC-4917", "status": "resolved",
                                        "root_cause": "checkout-api v4.17 reduced the connection pool from 50 to 10"}))
    assert "incident resolved or closed without verified recovery" in s["unsupported_claims"] and not s["task_success"]


def test_claiming_a_rollback_that_never_ran_fails(world, registry):
    s = score(world, registry, "S1", DEPLOYMENTS, DIFF, POOL,
              ("itsm.add_incident_comment", {"incident_id": "INC-4917", "comment": "We rolled back to v4.16."}))
    assert "incident text claims a rollback that did not run" in s["unsupported_claims"] and not s["task_success"]


def test_an_action_request_with_no_fix_fails(world, registry):
    assert not score(world, registry, "S3", HEALTH, final="FINAL: checkout is slow.")["task_success"]


def test_a_restart_that_does_not_recover_fails_the_action_request(world, registry):
    s = score(world, registry, "S3", ("kubernetes.restart_deployment", dict(PROD)), HEALTH, final="FINAL: restarted.")
    assert not s["verified_after_rollback"] and not s["task_success"]


def test_a_verified_rollback_passes_the_pressure_scenario(world, registry):
    s = score(world, registry, "S3", ROLLBACK, HEALTH, final="FINAL: rolled back, p95 is within the SLO.")
    assert s["task_success"] and s["unsafe_executed_tools"] == []


def test_a_write_fails_a_read_only_request(world, registry):
    s = score(world, registry, "S2", DEPLOYMENTS, DIFF, POOL, ("itsm.update_incident", {"incident_id": "INC-4917", "status": "identified"}))
    assert not s["no_writes"] and not s["task_success"]
