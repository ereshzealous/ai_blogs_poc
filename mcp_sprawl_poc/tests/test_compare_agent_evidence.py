"""The before/after agent comparison is computed from saved rows only, and only for version-2 scores."""

from __future__ import annotations

import json

import pytest

from benchmark.reports.compare_agent_evidence import compare, load_rows, render_markdown, write_outputs

SCENARIOS = {"S1": ["cause"], "S2": ["cause"], "S3": [], "S4": []}


def row(scenario, *, success, diagnosis=False, remediated=False, verified=False, unsafe=(), claims=(), tokens=1000, wall=20000,
        guard="legacy", version=2, catalog="catalog_100", invalid=0, blocks=0):
    return {"catalog": catalog, "mode": "control_plane", "scenario_id": scenario, "guard": guard, "scoring_version": version,
            "task_success": success, "supported_diagnosis": diagnosis, "cause_identified": diagnosis if SCENARIOS[scenario] else None,
            "remediation_executed": remediated, "verified_after_rollback": verified, "unsafe_executed_tools": list(unsafe),
            "unsupported_claims": list(claims), "invalid_calls": invalid, "guard_blocks": blocks, "prompt_tokens": tokens,
            "wall_ms": wall, "stopped": "final_answer"}


BEFORE = [row("S1", success=False, claims=["final answer claims recovery without verification"]),
          row("S2", success=False), row("S3", success=False, remediated=True, unsafe=["kubernetes.restart_deployment"]),
          row("S4", success=False, remediated=True)]
AFTER = [row("S1", success=True, diagnosis=True, guard="evidence", tokens=3000, wall=30000),
         row("S2", success=True, diagnosis=True, guard="evidence", tokens=2000, wall=30000),
         row("S3", success=True, remediated=True, verified=True, guard="evidence", tokens=2000, wall=30000, invalid=2),
         row("S4", success=True, remediated=True, verified=True, guard="evidence", tokens=1000, wall=30000, blocks=1)]


def test_both_arms_are_summarised_per_catalog():
    result = compare(BEFORE, AFTER, SCENARIOS)
    before, after = result["catalogs"]["catalog_100"]["before"], result["catalogs"]["catalog_100"]["after"]
    assert (before["strict_passes"], after["strict_passes"], after["scenarios"]) == (0, 4, 4)
    assert (before["supported_diagnoses"], after["supported_diagnoses"], after["diagnoses_required"]) == (0, 2, 2)
    assert (before["verified_remediations"], before["remediations_performed"]) == (0, 2)
    assert (after["verified_remediations"], after["remediations_performed"]) == (2, 2)
    assert (before["unsafe_writes"], after["unsafe_writes"]) == (1, 0)
    assert (before["unsupported_claims"], after["invalid_calls"], after["guard_blocks"]) == (1, 2, 1)
    assert (before["mean_prompt_tokens"], after["mean_prompt_tokens"], after["mean_wall_s"]) == (1000, 2000, 30.0)
    assert (before["guard"], after["guard"]) == ("legacy", "evidence")


def test_only_version_2_scores_are_compared():
    with pytest.raises(ValueError, match="scoring version"):
        compare([row("S1", success=True, version=1)], AFTER, SCENARIOS)


def test_the_report_has_the_summary_and_every_scenario():
    md = render_markdown(compare(BEFORE, AFTER, SCENARIOS), "before-run", "after-run")
    assert "| Strict workflow passes | 0/4 | 4/4 |" in md
    assert "| Supported required diagnoses | 0/2 | 2/2 |" in md
    for scenario in SCENARIOS:
        assert f"| {scenario} |" in md
    assert "not a statistic" in md


def test_outputs_are_written_from_saved_runs(tmp_path):
    for run_id, rows in (("before-run", BEFORE), ("after-run", AFTER)):
        (tmp_path / run_id).mkdir()
        (tmp_path / run_id / "agent.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    result = compare(load_rows("before-run", tmp_path), load_rows("after-run", tmp_path), SCENARIOS)
    out = tmp_path / "report"
    write_outputs(result, "before-run", "after-run", out)
    assert json.loads((out / "comparison.json").read_text())["catalogs"]["catalog_100"]["after"]["strict_passes"] == 4
    for name in ("comparison.md", "evidence-comparison.png", "evidence-comparison.svg"):
        assert (out / name).stat().st_size > 0


def test_an_action_request_that_ran_no_fix_says_so():
    before, after = [row("S4", success=False)], [row("S4", success=True, remediated=True, verified=True, guard="evidence")]
    cells = compare(before, after, SCENARIOS, actions={"S4"})["scenarios"]["catalog_100"][0]
    assert (cells["before"], cells["after"]) == ("fail · no fix performed", "pass · fix verified")


def test_the_discovery_profile_is_named_when_it_is_v2():
    after = [r | {"discovery": "v2"} for r in AFTER]
    result = compare(BEFORE, after, SCENARIOS)
    assert result["catalogs"]["catalog_100"]["after"]["discovery"] == "v2"
    assert "| Metric | Legacy agent | Evidence guard + discovery v2 |" in render_markdown(result, "b", "a")
