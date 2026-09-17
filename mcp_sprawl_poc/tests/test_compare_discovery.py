"""The discovery v1/v2 comparison is computed from saved, rescored selection rows, and pairs v1 with v2 case by case."""

from __future__ import annotations

import json

import pytest

from benchmark.reports.compare_discovery import ARMS, compare, load_arm, render_markdown, write_outputs


def row(case, *, catalog="catalog_500", mode="control_plane", exact=False, capability=False, valid=None, in_prompt=True,
        tokens=600, unsafe=False, executed_unsafe=False, split="test", discovery=None, ladder=True):
    return {"catalog": catalog, "mode": mode, "case_id": case, "split": split, "exact": exact, "capability_correct": capability,
            "valid_call": capability if valid is None else valid, "golden_in_prompt": in_prompt, "prompt_tokens": tokens,
            "unsafe_selection": unsafe, "unsafe_execution": executed_unsafe, "discovery": discovery, "ladder_subset": ladder}


CASES = ("C1", "C2", "C3", "C4")
BASELINE = [row(c, mode="baseline", exact=True, capability=True, tokens=24000) for c in CASES[:3]] + [row("C4", mode="baseline")]
SEARCH = [row(c, mode="search", capability=c == "C1", tokens=550) for c in CASES]
V1 = [row("C1", exact=True, capability=True), row("C2", capability=True), row("C3", in_prompt=False), row("C4", unsafe=True)]
V2 = [row("C1", exact=True, capability=True, discovery="v2"), row("C2", exact=True, capability=True, discovery="v2"),
      row("C3", exact=True, capability=True, discovery="v2"), row("C4", discovery="v2")]


@pytest.fixture
def result():
    return compare({"baseline": BASELINE, "search": SEARCH, "control_plane_v1": V1, "control_plane_v2": V2})


def test_every_arm_is_summarised_per_catalog(result):
    arms = result["catalogs"]["catalog_500"]
    assert [a for a in ARMS if a in arms] == list(ARMS)
    assert (arms["baseline"]["n"], arms["baseline"]["capability_correct"]) == (4, 0.75)
    assert (arms["control_plane_v1"]["exact"], arms["control_plane_v2"]["exact"]) == (0.25, 0.75)
    assert (arms["control_plane_v1"]["golden_in_prompt"], arms["control_plane_v2"]["capability_correct"]) == (0.75, 0.75)
    assert arms["control_plane_v1"]["unsafe_selections"] == 1
    assert arms["baseline"]["mean_prompt_tokens"] == 24000 * 3 / 4 + 600 / 4
    low, high = arms["control_plane_v2"]["capability_ci"]
    assert low < 0.75 < high


def test_v2_is_paired_with_v1_on_the_same_cases(result):
    pairs = result["paired"]["catalog_500"]
    assert pairs["capability"] == {"n": 4, "fixed": 1, "broke": 0, "both_right": 2, "both_wrong": 1}
    assert pairs["exact"] == {"n": 4, "fixed": 2, "broke": 0, "both_right": 1, "both_wrong": 1}
    assert pairs["fixed_cases"] == ["C3"] and pairs["broken_cases"] == []


def test_cases_missing_from_one_profile_are_not_paired():
    pairs = compare({"control_plane_v1": V1, "control_plane_v2": V2[:2]})["paired"]["catalog_500"]
    assert pairs["capability"]["n"] == 2


def test_rows_of_the_other_split_are_ignored():
    dev_row = row("C9", split="dev", capability=True)
    assert compare({"control_plane_v1": V1 + [dev_row], "control_plane_v2": V2})["catalogs"]["catalog_500"]["control_plane_v1"]["n"] == 4


def test_the_report_names_both_profiles_and_the_pairing(result):
    md = render_markdown(result, {"baseline": "pub", "search": "pub", "control_plane_v1": "rerun-v1", "control_plane_v2": "run-v2"})
    assert "| Right capability | 75.0% | 25.0% | 50.0% | 75.0% |" in md
    assert "`rerun-v1`" in md and "`run-v2`" in md
    assert "fixed 1 · broke 0" in md
    assert "tuned on the dev split" in md


def test_a_saved_selection_row_is_rescored_with_the_current_labels(tmp_path):
    raw = {"run_id": "r", "catalog": "catalog_50", "mode": "control_plane", "case_id": "D08", "split": "dev",
           "selected": "source_control.get_diff", "arguments": {"sha": "a91f3c2"}, "executed": True, "execution_error": False,
           "candidates": ["source_control.get_diff"], "prompt_tokens": 547, "discovery": "v2"}
    (tmp_path / "r").mkdir()
    (tmp_path / "r" / "selection.jsonl").write_text(json.dumps(raw) + "\n")
    [scored] = load_arm("r", "control_plane", runs_dir=tmp_path)
    assert scored["exact"] and scored["capability_correct"] and scored["golden_in_prompt"]


def test_outputs_are_written(result, tmp_path):
    write_outputs(result, {"control_plane_v1": "a", "control_plane_v2": "b"}, tmp_path)
    assert json.loads((tmp_path / "comparison.json").read_text())["paired"]["catalog_500"]["capability"]["fixed"] == 1
    for name in ("comparison.md", "discovery-v2-accuracy.png", "discovery-v2-accuracy.svg"):
        assert (tmp_path / name).stat().st_size > 0


def test_only_catalogs_with_control_plane_rows_are_reported():
    extra = [row("C1", catalog="catalog_10", mode="baseline", capability=True)]
    result = compare({"baseline": BASELINE + extra, "control_plane_v1": V1, "control_plane_v2": V2})
    assert list(result["catalogs"]) == ["catalog_500"]


def test_a_dev_split_report_says_it_is_the_tuning_split():
    md = render_markdown(compare({"control_plane_v1": V1, "control_plane_v2": V2}, split="dev"), {})
    assert "used to tune discovery v2" in md and "run once" not in md


def test_the_size_curve_uses_only_cases_present_at_every_size():
    at_100 = lambda rows: [r | {"catalog": "catalog_100"} for r in rows]
    v1 = V1 + at_100(V1) + [row("C5", capability=True)]  # C5 only at 500 tools
    v2 = V2 + at_100(V2)
    result = compare({"control_plane_v1": v1, "control_plane_v2": v2})
    assert result["catalogs"]["catalog_500"]["control_plane_v1"]["n"] == 5
    assert result["ladder"]["catalog_500"]["control_plane_v1"]["n"] == 4
    assert result["ladder"]["catalog_100"]["control_plane_v1"]["n"] == 4
    assert "overlap" not in "".join(result["ladder"])


def test_end_labels_are_spread_apart():
    from benchmark.reports.compare_discovery import spread
    assert spread([80.2, 77.9, 76.7, 58.1], gap=4) == [80.2, 76.2, 72.2, 58.1]
    assert spread([10, 50], gap=4) == [10, 50]


def test_a_run_without_rows_for_the_mode_is_named(tmp_path):
    with pytest.raises(FileNotFoundError, match="no control_plane rows in run 'never-ran'"):
        load_arm("never-ran", "control_plane", runs_dir=tmp_path)


def test_the_candidate_profile_is_named(result, tmp_path):
    md = render_markdown(result, {"control_plane_v1": "a", "control_plane_v2": "b"}, candidate="v3")
    assert md.startswith("# Discovery v3 comparison") and "Control plane, discovery v3" in md
    assert "Control plane, discovery v2" not in md
    write_outputs(result, {"control_plane_v1": "a", "control_plane_v2": "b"}, tmp_path, candidate="v3")
    assert (tmp_path / "discovery-v3-accuracy.png").stat().st_size > 0


def test_a_holdout_report_explains_the_held_out_cases():
    md = render_markdown(compare({"control_plane_v1": V1, "control_plane_v2": V2}, split="holdout"), {}, candidate="v3")
    assert "held-out" in md and "tuned on the dev split only" not in md


def test_a_v3_report_names_the_run_baseline_came_from(result):
    md = render_markdown(result, {"baseline": "holdout-run", "search": "holdout-run"}, candidate="v3")
    assert "Baseline and tool search come from `holdout-run`" in md and "published run;" not in md


def test_catalogs_one_profile_did_not_run_are_left_out_of_the_size_curve(tmp_path):
    only_v1 = [r | {"catalog": "catalog_10"} for r in V1]
    result = compare({"control_plane_v1": V1 + only_v1, "control_plane_v2": V2})
    assert list(result["ladder"]) == ["catalog_500"] and result["ladder"]["catalog_500"]["control_plane_v1"]["n"] == 4
    write_outputs(result, {}, tmp_path, candidate="v3")
    assert (tmp_path / "discovery-v3-accuracy.png").exists()


def test_v4_input_tokens_include_the_rewrite_call():
    v2 = [r | {"discovery_prompt_tokens": 150} for r in V2]
    tokens = compare({"control_plane_v1": V1, "control_plane_v2": v2})["catalogs"]["catalog_500"]
    assert tokens["control_plane_v1"]["mean_prompt_tokens"] == 600
    assert tokens["control_plane_v2"]["mean_prompt_tokens"] == 750
    md = render_markdown(compare({"control_plane_v1": V1, "control_plane_v2": v2}), {}, candidate="v4")
    assert "include the rewrite call" in md


def test_asking_the_user_is_reported_next_to_accuracy():
    asked = [r | {"asked": r["case_id"] == "C3"} for r in V2]
    result = compare({"control_plane_v1": V1, "control_plane_v2": asked})
    arm = result["catalogs"]["catalog_500"]["control_plane_v2"]
    assert (arm["asked"], arm["right_without_asking"], arm["capability_correct"]) == (0.25, 0.5, 0.75)
    assert "asked" not in result["catalogs"]["catalog_500"]["control_plane_v1"]
    md = render_markdown(result, {}, candidate="v4")
    assert "| Asked the user | n/a | 25.0% |" in md and "| Right without asking | n/a | 50.0% |" in md


def test_a_failed_model_call_is_left_out_of_the_token_mean():
    rows = V1[:3] + [row("C4") | {"prompt_tokens": None}]
    assert compare({"control_plane_v1": rows, "control_plane_v2": V2})["catalogs"]["catalog_500"]["control_plane_v1"]["mean_prompt_tokens"] == 600


def test_a_very_small_p_value_is_not_printed_as_zero():
    from benchmark.reports.compare_discovery import _paired_line
    p = {"capability": {"n": 100, "fixed": 22, "broke": 1, "both_right": 74, "both_wrong": 3}, "capability_mcnemar_p": 0.0000057,
         "exact": {"fixed": 22, "broke": 1}, "exact_mcnemar_p": 0.0000057, "fixed_cases": [], "broken_cases": []}
    line = _paired_line(p, "v4")
    assert "p < 0.001" in line and "p = 0.00" not in line
