"""The capability-resolution report: every arm side by side, per catalog."""

from __future__ import annotations

import json

from benchmark.reports.resolution_report import render_markdown, summarize, write_outputs


def row(catalog, kind="clear", resolved=True, asked=False, auto=None, split="holdout3"):
    auto = (not asked) if auto is None else auto
    return {"catalog": catalog, "split": split, "kind": kind, "resolved": resolved if kind != "trap" else None,
            "asked": asked, "abstained": False, "automatic": auto, "wrongly_confident": auto and not resolved,
            "selected_tier": "READ_ONLY", "right_tool_shown": True, "guess": kind == "ambiguous" and not asked,
            "lucky_guess": kind == "ambiguous" and not asked and resolved, "trap_ok": True if kind == "trap" else None,
            "exact": resolved, "valid_call": resolved, "unsafe_selection": False, "unsafe_execution": False,
            "prompt_tokens": 800, "discovery_prompt_tokens": 600, "case_wall_ms": 2000.0}


ARMS = {
    "Baseline (all tools)": [row("catalog_100"), row("catalog_100", "ambiguous", resolved=False), row("catalog_100", "trap"),
                             row("catalog_500", resolved=False), row("catalog_100", split="test")],
    "Control plane v5": [row("catalog_100"), row("catalog_100", "ambiguous", asked=True), row("catalog_100", "trap"),
                         row("catalog_500")],
}
SOURCES = {"Baseline (all tools)": "r1:baseline", "Control plane v5": "r2:control_plane"}


def test_arms_are_summarised_per_catalog_on_the_split():
    result = summarize(ARMS, "holdout3")
    base = result["catalogs"]["catalog_100"]["Baseline (all tools)"]
    v5 = result["catalogs"]["catalog_100"]["Control plane v5"]
    assert base["n"] == {"clear": 1, "ambiguous": 1, "trap": 1}
    assert base["overall_resolution"]["count"] == [1, 2] and v5["overall_resolution"]["count"] == [2, 2]
    assert v5["ask_rate"]["count"] == [1, 2] and base["lucky_guesses"]["count"] == [0, 1]
    assert list(result["catalogs"]) == ["catalog_100", "catalog_500"]


def test_only_the_named_catalogs_are_summarised():
    result = summarize(ARMS, "holdout3", catalogs=["catalog_100"])
    assert list(result["catalogs"]) == ["catalog_100"]
    assert summarize(ARMS, "holdout3", catalogs=None)["catalogs"].keys() == {"catalog_100", "catalog_500"}


def test_the_report_leads_with_overall_resolution():
    md = render_markdown(summarize(ARMS, "holdout3"), SOURCES)
    assert "| catalog_100 | 50.0% (1/2) | 100.0% (2/2) |" in md
    assert "Wrongly confident, by tier" in md and "`r2:control_plane`" in md
    assert "1 clear, 1 ambiguous and 1 trap requests." in md


def test_outputs_are_written(tmp_path):
    write_outputs(summarize(ARMS, "holdout3"), SOURCES, tmp_path)
    data = json.loads((tmp_path / "summary.json").read_text())
    assert data["catalogs"]["catalog_500"]["Control plane v5"]["overall_resolution"]["value"] == 1.0
    for name in ("summary.md", "resolution-by-arm.png", "resolution-by-arm.svg"):
        assert (tmp_path / name).stat().st_size > 0
