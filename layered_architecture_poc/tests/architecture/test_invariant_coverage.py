"""docs/invariants.yaml must stay true: every invariant enforced, every citation real.

An invariants document is worthless if it can drift from the repository. These tests check, for each invariant:

- it has at least one enforcement (static, test, experiment or recomputed);
- every test it names exists, as a file and as a test function;
- every facts path it names exists in the published run's facts.json;
- every recomputed check it names appears in that run's verification.json;
- every experiment it names has scenarios in the run.

They also check the reverse direction: every test file in the suite belongs to a category the taxonomy knows, and
every invariant id used by a test marker exists here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs"
INVARIANTS = ROOT / "docs" / "invariants.yaml"
KINDS = ("static", "tests", "experiments", "recomputed")
CATEGORIES = {"unit", "contract", "architecture", "integration", "evidence", "fault_injection", "model", "publication"}


def doc() -> dict:
    return yaml.safe_load(INVARIANTS.read_text())


def published_run() -> Path:
    return RUNS / (RUNS / "PUBLISHED").read_text().strip()


def facts() -> dict:
    return json.loads((published_run() / "facts.json").read_text())


def ids() -> list[str]:
    return sorted(doc()["invariants"])


def test_the_document_parses_and_covers_l1_to_l15():
    got = set(doc()["invariants"])
    assert got == {f"L{i}" for i in range(1, 16)}, f"unexpected invariant ids: {sorted(got)}"
    assert set(doc()["not_enforced"]) == {f"N{i}" for i in range(1, 7)}


@pytest.mark.parametrize("inv", ids())
def test_every_invariant_is_enforced_somehow(inv):
    body = doc()["invariants"][inv]
    assert any(body.get(k) for k in KINDS), f"{inv} has no enforcement: it is prose, so move it to not_enforced"
    assert body.get("statement"), f"{inv} has no statement"
    assert body.get("does_not_show"), f"{inv} does not say what it fails to show"


@pytest.mark.parametrize("inv", ids())
def test_every_test_an_invariant_names_exists(inv):
    body = doc()["invariants"][inv]
    missing = []
    for node in list(body.get("static", [])) + list(body.get("tests", [])):
        rel, _, name = node.partition("::")
        name = re.sub(r"\[.*\]$", "", name)  # a parametrized id names one case of a real function
        path = ROOT / rel
        if not path.exists():
            missing.append(f"no file {rel}")
        elif f"def {name}(" not in path.read_text():
            missing.append(f"{rel} has no {name}")
    assert not missing, f"{inv}: {missing}"


@pytest.mark.parametrize("inv", ids())
def test_every_facts_path_an_invariant_names_exists(inv):
    run = published_run()
    if not run.exists():
        pytest.skip(f"{run.name} is not present")
    f = facts()
    missing = [p for p in doc()["invariants"][inv].get("facts", []) if p not in f]
    assert not missing, f"{inv} cites facts paths the published run does not have: {missing}"


@pytest.mark.parametrize("inv", ids())
def test_every_experiment_an_invariant_names_ran(inv):
    """An experiment is present if it ran scenarios, or if it is an analysis with its own result file.

    E8 is the second kind: it scores the spans the other scenarios emitted, so it has `experiments/E8.json` but no
    `scenarios/E8-*` directory. See docs/experiment-inventory.md for why the ids are what they are.
    """
    run = published_run()
    if not run.exists():
        pytest.skip(f"{run.name} is not present")
    from_scenarios = {d.name.split("-")[0] for d in (run / "scenarios").iterdir()}
    from_analyses = {p.stem.split("_")[0] for p in (run / "experiments").glob("*.json")}
    missing = [e for e in doc()["invariants"][inv].get("experiments", []) if e not in from_scenarios | from_analyses]
    assert not missing, f"{inv} cites experiments with neither scenarios nor a result file: {missing}"


@pytest.mark.parametrize("inv", ids())
def test_every_recomputed_check_an_invariant_names_ran(inv):
    run = published_run()
    verification = run / "verification.json"
    if not verification.exists():
        pytest.skip("the run has no verification.json yet")
    names = {c["check"] for c in json.loads(verification.read_text())["checks"]}
    missing = [c for c in doc()["invariants"][inv].get("recomputed", []) if c not in names]
    assert not missing, f"{inv} cites recomputation checks the verifier does not run: {missing}"


def test_every_test_file_sits_in_a_known_category():
    stray = [str(p.relative_to(ROOT)) for p in (ROOT / "tests").rglob("test_*.py")
             if p.parent.name not in CATEGORIES]
    assert not stray, f"tests outside the taxonomy: {stray}"


def test_the_taxonomy_matches_the_directories():
    """Every directory that holds tests is a known category. Directories of fixtures or data are not categories."""
    dirs = {p.name for p in (ROOT / "tests").iterdir()
            if p.is_dir() and not p.name.startswith("__") and any(p.rglob("test_*.py"))}
    unknown = dirs - CATEGORIES
    assert not unknown, f"test directories the taxonomy does not know: {sorted(unknown)}"


def test_invariants_referenced_by_markers_exist():
    """A test may declare the invariant it covers with @pytest.mark.invariant("L8"). Those ids must be real."""
    known = set(doc()["invariants"])
    bad = []
    for path in (ROOT / "tests").rglob("test_*.py"):
        for m in re.finditer(r'invariant\("([^"]+)"\)', path.read_text()):
            if m.group(1) not in known:
                bad.append(f"{path.name}: {m.group(1)}")
    assert not bad, f"tests mark invariants that do not exist: {bad}"
