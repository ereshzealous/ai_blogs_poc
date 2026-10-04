"""The evidence pipeline: facts.json, freeze.json, verification.json and the claim-to-evidence matrix.

These tests are about the pipeline's rules, not about one run's numbers: a value the run cannot support is absent
rather than guessed, a changed input is noticed, a claim cannot cite evidence that is not there, and the published
reference run still passes every check it claims to pass.
"""

from __future__ import annotations

import json

import pytest

from experiments import claims, facts, freeze, verify
from experiments.poc import REFERENCE_RUN
from tests.conftest import ROOT

REFERENCE = ROOT / "runs" / REFERENCE_RUN


def test_facts_leave_out_what_a_run_cannot_support(tmp_path):
    (tmp_path / "run.json").write_text(json.dumps({"mode": "live", "profile": "quick", "models": ["m"]}))
    built = facts.build(tmp_path)

    assert built["run"]["profile"] == "quick"
    for absent in ("platform", "crash", "faults", "monolith", "tests", "sample_run"):
        assert absent not in built, f"{absent} was invented for a run that has no such experiment"


def test_facts_are_the_numbers_the_article_prints():
    built = facts.build(REFERENCE)
    published = json.loads((REFERENCE / "facts.json").read_text())

    for section in ("platform", "crash", "faults", "monolith", "tests", "remediation_repairs", "sample_run"):
        assert built[section] == published[section], f"{section} changed since the run was published"


def test_freeze_notices_a_changed_input(tmp_path, monkeypatch):
    source = tmp_path / "config"
    source.mkdir()
    (source / "a.yaml").write_text("one: 1")
    monkeypatch.setattr(freeze, "ROOT", tmp_path)
    monkeypatch.setattr(freeze, "INPUTS", ["config/*.yaml"])
    freeze.write(tmp_path)

    assert freeze.check(tmp_path)["changed"] == []
    (source / "a.yaml").write_text("one: 2")
    moved = freeze.check(tmp_path)
    assert moved["changed"] == ["config/a.yaml"]
    assert moved["digest_now"] != moved["digest_recorded"]


def test_freeze_written_after_a_run_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(freeze, "ROOT", tmp_path)
    monkeypatch.setattr(freeze, "INPUTS", [])
    assert json.loads(freeze.write(tmp_path).read_text())["retrospective"] is False
    assert json.loads(freeze.write(tmp_path, retrospective=True).read_text())["retrospective"] is True


def test_verify_refuses_a_run_without_facts(tmp_path):
    with pytest.raises(SystemExit):
        verify.verify(tmp_path)


def test_the_published_run_verifies():
    result = verify.verify(REFERENCE)

    assert result["failed"] == 0, [r for r in result["checks"] if r["status"] == "fail"]
    assert result["ok"] is True
    for check in ("writes land once", "approval binds the write", "crash and resume", "one trace across the kills"):
        assert [r for r in result["checks"] if r["check"] == check][0]["status"] == "pass"


def test_a_skipped_check_is_never_a_pass(tmp_path):
    (tmp_path / "facts.json").write_text(json.dumps({"run_id": tmp_path.name}))
    result = verify.verify(tmp_path)

    assert result["passed"] == 0
    assert {r["status"] for r in result["checks"]} <= {"skip", "fail"}


def test_every_claim_resolves_against_the_published_run():
    resolved, problems = claims.check(REFERENCE)

    assert problems == []
    assert len(resolved) == len(json.loads(claims.CLAIMS.read_text())["claims"])
    for claim in resolved:
        assert claim["limits"], f"{claim['id']} does not say what it fails to show"
        assert claim["facts"] or claim["tests"] or claim["verified_by"], f"{claim['id']} rests on nothing"


def test_a_claim_cannot_cite_evidence_that_is_not_there(tmp_path, monkeypatch):
    invented = tmp_path / "claims.json"
    invented.write_text(json.dumps({"claims": [{
        "id": "X-01", "section": "s", "claim": "c", "kind": "measured", "facts": ["platform.no-such-model.runs"],
        "placeholders": [], "verified_by": ["no such check"], "evidence": ["no-such-file.json"],
        "tests": ["tests/test_evidence.py::test_no_such_test"], "limits": "l"}]}))
    monkeypatch.setattr(claims, "CLAIMS", invented)
    problems = claims.check(REFERENCE)[1]

    assert len(problems) == 4
    assert any("facts.json has no" in p for p in problems)
    assert any("no check" in p for p in problems)
    assert any("no file in the run" in p for p in problems)
    assert any("has no test_no_such_test" in p for p in problems)


def test_the_matrix_lists_every_claim_with_its_limits():
    resolved = claims.check(REFERENCE)[0]
    text = claims.matrix(REFERENCE, resolved)

    assert text.startswith("# Claim-to-evidence matrix")
    for claim in resolved:
        assert claim["id"] in text and claim["limits"] in text
