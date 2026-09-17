"""Case sets: the main set (dev/test by hash) and an optional held-out set with its own fixed split."""

from __future__ import annotations

import argparse
import json

import pytest

from benchmark.evaluator import metrics
from benchmark.evaluator.metrics import load_all_cases, load_cases
from control_plane.paths import CATALOG_DIR

HOLDOUT = """
defaults:
  identity: { user_id: oncall-1, roles: [sre-oncall] }
  split: holdout
cases:
  - id: H901
    category: direct
    prompt: Show checkout-api pods in production.
    golden_tool: kubernetes.get_pods
    expected_args: { service: checkout-api, environment: production }
    expected_policy: ALLOW
"""


@pytest.fixture
def holdout_file(tmp_path, monkeypatch):
    path = tmp_path / "holdout_cases.yaml"
    path.write_text(HOLDOUT)
    monkeypatch.setattr(metrics, "HOLDOUT_FILE", path)
    return path


def test_a_held_out_case_keeps_its_own_split(holdout_file):
    [case] = load_cases(holdout_file)
    assert case.split == "holdout" and case.id == "H901"


def test_main_cases_keep_the_hash_split():
    assert {c.split for c in load_cases()} == {"dev", "test"}


def test_all_cases_include_the_held_out_set(holdout_file):
    ids = [c.id for c in load_all_cases()]
    assert "H901" in ids and "D01" in ids and len(ids) == len(set(ids))


def test_duplicate_ids_across_sets_are_rejected(tmp_path, monkeypatch):
    path = tmp_path / "holdout_cases.yaml"
    path.write_text(HOLDOUT.replace("H901", "D01"))
    monkeypatch.setattr(metrics, "HOLDOUT_FILE", path)
    with pytest.raises(ValueError, match="D01"):
        load_all_cases()


def test_a_second_held_out_set_has_its_own_split(tmp_path, monkeypatch, holdout_file):
    second = tmp_path / "holdout2_cases.yaml"
    second.write_text(HOLDOUT.replace("split: holdout", "split: holdout2").replace("H901", "H990"))
    monkeypatch.setattr(metrics, "HOLDOUT2_FILE", second)
    by_id = {c.id: c for c in load_all_cases()}
    assert by_id["H990"].split == "holdout2" and by_id["H901"].split == "holdout"
    from benchmark.runner import _select_cases
    assert [c.id for c in _select_cases(argparse.Namespace(case_set="holdout2", cases="", split="all"))] == ["H990"]


def test_the_runner_selects_the_held_out_set(holdout_file):
    from benchmark.runner import _select_cases
    args = argparse.Namespace(case_set="holdout", cases="", split="all")
    assert [c.id for c in _select_cases(args)] == ["H901"]


def test_a_held_out_row_is_rescored(holdout_file):
    from benchmark.reports.build_report import rescore_selection
    row = {"catalog": "catalog_50", "case_id": "H901", "selected": "kubernetes.get_pods",
           "arguments": {"service": "checkout-api", "environment": "production"}, "executed": True,
           "execution_error": False, "candidates": ["kubernetes.get_pods"]}
    summary = rescore_selection([row])
    assert row["exact"] and row["capability_correct"] and "holdout_sha256" in summary


def test_published_rescoring_output_is_unchanged():
    from benchmark.reports.build_report import rescore_selection
    row = {"catalog": "catalog_50", "case_id": "D08", "selected": "source_control.get_diff", "arguments": {"sha": "a91f3c2"},
           "executed": True, "execution_error": False, "candidates": None}
    assert "holdout_sha256" not in rescore_selection([row])


# ---------------------------------------------------------------------------------------------- integrity
CATEGORIES = {"direct", "ambiguity", "cross_domain", "multi_step", "risky", "adversarial"}


@pytest.fixture(scope="module")
def core_tools():
    manifest = json.loads((CATALOG_DIR / "catalog_50.json").read_text())
    return {f"{t['server']}.{t['name']}": t for t in manifest["tools"]}


@pytest.mark.parametrize("case", load_all_cases(), ids=lambda c: c.id)
def test_every_case_is_well_formed(case, core_tools, registry):
    assert case.category in CATEGORIES
    assert case.golden_tool in core_tools, "golden tools are core tools"
    for tool in case.acceptable_tools:
        rec = registry.get(tool)
        assert rec is not None and rec.lifecycle == "active", tool
    props = core_tools[case.golden_tool]["input_schema"].get("properties", {})
    assert set(case.expected_args) <= set(props), set(case.expected_args) - set(props)


def test_the_run_config_fingerprints_the_discovery_and_selection_code():
    from benchmark.runner import _base_config, discovery_code_sha256
    config = _base_config(argparse.Namespace(case_set="main", k=5), ["catalog_50"])
    assert config["discovery_code_sha256"] == discovery_code_sha256() and len(config["discovery_code_sha256"]) == 64
