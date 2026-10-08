"""The corpus is solvable as labelled: every safe remediation is reachable through the real world and fixes it, every
label matcher names a real tool, and every fixture loads."""

from __future__ import annotations

from pathlib import Path

import pytest

from coord.evaluate import labels
from coord.world import READ_TOOLS, WRITE_TOOLS, World, load_fixture, match_call

LAB = labels()


def concrete(args: dict) -> dict:
    out = {}
    for k, v in args.items():
        if isinstance(v, dict) and "in" in v:
            out[k] = v["in"][0]
        elif isinstance(v, dict):
            out[k] = int(v.get("gte", v.get("lte", 0)))
        else:
            out[k] = v
    return out


def test_twelve_fixtures_four_dev_eight_blind():
    fx = LAB["fixtures"]
    assert len(fx) == 12
    assert sorted(k for k, v in fx.items() if v["split"] == "dev") == ["D1", "D2", "D3", "D4"]
    assert sorted(k for k, v in fx.items() if v["split"] == "blind") == [f"B{i}" for i in range(1, 9)]
    assert {v["subset"] for v in fx.values() if v["split"] == "blind"} == {"simple", "complex", "other"}


@pytest.mark.parametrize("fid", sorted(LAB["fixtures"]))
def test_fixture_loads_and_labels_name_real_tools(fid: str):
    spec = load_fixture(fid)
    lab = LAB["fixtures"][fid]
    assert spec["incident"]["id"] == lab["incident_id"]
    for c in lab["category_acceptable"]:
        assert c in LAB["categories"]
    for group in lab["required_evidence"]:
        for m in group:
            assert m["tool"] in READ_TOOLS
            assert m["args"].get("service", spec["incident"]["service"]) in spec["services"]
    for m in lab["safe_remediations"] + lab["prohibited"]:
        assert m["tool"] in WRITE_TOOLS


@pytest.mark.parametrize("fid", sorted(f for f, v in LAB["fixtures"].items() if v["expected_outcome"] == "RESOLVED"))
def test_safe_remediations_are_reachable(fid: str, tmp_path: Path):
    lab = LAB["fixtures"][fid]
    for i, m in enumerate(lab["safe_remediations"]):
        w = World(tmp_path / f"{fid}-{i}.db")
        w.reset(fid)
        svc = load_fixture(fid)["incident"]["service"]
        assert not w.healthy(svc), f"{fid} should start degraded"
        args = concrete(m["args"])
        getattr(w, m["tool"])(**args)
        assert match_call(m, m["tool"], args)
        assert w.healthy(svc), f"{fid}: {m['tool']} {args} did not recover {svc}"


@pytest.mark.parametrize("fid", sorted(f for f, v in LAB["fixtures"].items() if v["expected_outcome"] != "RESOLVED"))
def test_no_action_fixtures(fid: str, tmp_path: Path):
    w = World(tmp_path / "w.db")
    w.reset(fid)
    svc = load_fixture(fid)["incident"]["service"]
    expected = LAB["fixtures"][fid]["expected_outcome"]
    assert w.healthy(svc) == (expected == "NO_ACTION")
