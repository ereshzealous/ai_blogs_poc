"""Documentation/evidence validation: the published run is complete, frozen and self-consistent."""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
POINTER = ROOT / "runs" / "PUBLISHED"
pytestmark = pytest.mark.skipif(not POINTER.exists(), reason="no published run yet")


def run_dir() -> Path:
    return ROOT / "runs" / POINTER.read_text().strip()


def test_manifest_has_the_required_fields():
    m = json.loads((run_dir() / "manifest.json").read_text())
    for k in ("run_id", "started_utc", "finished_utc", "platform", "python", "models", "ollama_version", "hashes", "tests", "mode"):
        assert k in m, k


def test_plan_hash_in_manifest_matches_the_plan_on_disk():
    m = json.loads((run_dir() / "manifest.json").read_text())
    plan = ROOT / "experiments/preregistration/experiment_plan.yaml"
    assert m["hashes"]["experiment_plan"] == hashlib.sha256(plan.read_bytes()).hexdigest()


def test_summary_covers_every_experiment_and_scenario():
    s = json.loads((run_dir() / "summary.json").read_text())
    assert set(s["experiments"]) >= {f"E{i}" for i in range(1, 10)}
    assert s["integrity"]["scenarios_expected"] == s["integrity"]["scenarios_present"]


def test_every_scenario_has_raw_evidence():
    for sdir in (run_dir() / "scenarios").iterdir():
        assert (sdir / "score.json").exists() and (sdir / "raw" / "executions.jsonl").exists(), sdir.name
