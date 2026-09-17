"""The multi-arm summary: every arm of a measurement side by side, from saved rows only."""

from __future__ import annotations

import json

import pytest

from benchmark.reports.profile_summary import parse_arm, render_markdown, summarize, write_outputs


def row(case, catalog="catalog_100", *, right=True, tokens=600, asked=None, split="holdout2", extra_tokens=None):
    r = {"catalog": catalog, "case_id": case, "split": split, "exact": right, "capability_correct": right, "valid_call": right,
         "golden_in_prompt": True, "prompt_tokens": tokens, "unsafe_selection": False, "unsafe_execution": False}
    if asked is not None:
        r["asked"] = asked
    if extra_tokens is not None:
        r["discovery_prompt_tokens"] = extra_tokens
    return r


ARMS = {
    "Baseline (all tools)": [row("A"), row("B"), row("C", right=False), row("D"), row("A", "catalog_500", right=False)],
    "Control plane v4": [row("A", extra_tokens=300), row("B", extra_tokens=300), row("C", extra_tokens=300),
                         row("D", right=False, extra_tokens=300), row("A", "catalog_500", extra_tokens=300)],
    "Control plane v4, may ask": [row("A", asked=False), row("B", asked=True), row("C", asked=False), row("D", asked=False),
                                  row("A", "catalog_500", asked=False)],
}


def test_an_arm_is_parsed_from_label_run_and_mode():
    assert parse_arm("Control plane v4, may ask=holdout2-v4c:control_plane") == ("Control plane v4, may ask", "holdout2-v4c", "control_plane")
    with pytest.raises(ValueError):
        parse_arm("no mode here")


def test_every_arm_is_summarised_per_catalog():
    result = summarize(ARMS, split="holdout2")
    at_100 = result["catalogs"]["catalog_100"]
    assert at_100["Baseline (all tools)"]["capability_correct"] == 0.75
    assert at_100["Control plane v4"]["mean_prompt_tokens"] == 900
    assert (at_100["Control plane v4, may ask"]["asked"], at_100["Control plane v4, may ask"]["right_without_asking"]) == (0.25, 0.75)
    assert list(result["catalogs"]) == ["catalog_100", "catalog_500"]


def test_rows_of_another_split_are_ignored():
    arms = {"x": [row("A"), row("Z", split="test")]}
    assert summarize(arms, split="holdout2")["catalogs"]["catalog_100"]["x"]["n"] == 1


def test_the_report_has_a_headline_row_per_catalog():
    md = render_markdown(summarize(ARMS, split="holdout2"), {"Baseline (all tools)": "run-a:baseline"})
    assert "| catalog_100 | 4 | 75.0% | 75.0% | 100.0% |" in md
    assert "Asked the user" in md and "`run-a:baseline`" in md


def test_outputs_are_written(tmp_path):
    result = summarize(ARMS, split="holdout2")
    write_outputs(result, {}, tmp_path)
    assert json.loads((tmp_path / "summary.json").read_text())["catalogs"]["catalog_500"]["Control plane v4"]["n"] == 1
    for name in ("summary.md", "accuracy-by-profile.png", "accuracy-by-profile.svg"):
        assert (tmp_path / name).stat().st_size > 0
