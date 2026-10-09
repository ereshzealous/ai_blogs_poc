"""End-to-end: the ten tests the brief asked for, each through real worker processes against the simulated providers.

Each runs one scenario through a runtime with harness.run_one and evaluates the run with the same eval suite the
recorded run uses.  Effects are counted from the providers' own ledgers.
"""
import pytest

from recovery.common import read_jsonl
from recovery.evals import evaluate
from recovery.harness import run_one


def go(tmp_path, sc, sid, arm, **kw):
    d = tmp_path / sid / arm
    run_one(d, sc[sid], arm, **kw)
    return d, evaluate(d, sc[sid], arm)


def decisions(e):
    return [tuple(x) for x in e["decisions"]]


def test_01_safe_retry_when_definitely_not_executed(tmp_path, sc):
    d, e = go(tmp_path, sc, "S08", "A2")
    assert decisions(e) == [("TOOL_UNAVAILABLE", "NOT_EXECUTED", "RETRY")]
    assert e["effects"]["credits_total"] == 1


@pytest.mark.parametrize("arm,credits", [("A0", 2), ("A2", 1)])
def test_02_lost_response_after_commit_is_not_blindly_executed_again(tmp_path, sc, arm, credits):
    d, e = go(tmp_path, sc, "S09", arm)
    assert e["effects"]["credits_total"] == credits                    # A0 shows the hazard; A2 does not resend
    if arm == "A2":
        disp = [x for x in read_jsonl(d / "events.jsonl") if x["kind"] == "tool.dispatch" and x["step"] == "credit"]
        assert len(disp) == 1


def test_03_unknown_outcome_triggers_reconciliation(tmp_path, sc):
    d, e = go(tmp_path, sc, "S09", "A2")
    assert decisions(e) == [("RESPONSE_LOST", "UNKNOWN", "RECONCILE"), ("RECONCILED", "EXECUTED", "CONTINUE")]
    assert e["effects"]["credits_total"] == 1 and e["answer"]["status"] == "COMPLETED"


def test_04_idempotency_prevents_the_duplicate_only_where_supported(tmp_path, sc):
    _, keyed = go(tmp_path, sc, "S09", "A1")
    _, unkeyed = go(tmp_path, sc, "S11", "A1")
    assert keyed["effects"]["credits_total"] == 1
    assert unkeyed["effects"]["tickets"] == 2                          # the ticket API ignores the key


def test_05_crash_and_resume_preserve_semantics(tmp_path, sc):
    for sid, cert in (("S16", "UNKNOWN"), ("S17", "EXECUTED")):
        d, e = go(tmp_path, sc, sid, "A2")
        assert e["decisions"][0][:2] == ["PROCESS_INTERRUPTED", cert]
        assert e["effects"]["credits_total"] == 1 and e["answer"]["status"] == "COMPLETED"
        assert e["checks"]["I7"]["result"] == "PASS" and e["checks"]["I8"]["result"] == "PASS"


def test_06_authorization_denial_is_terminal(tmp_path, sc):
    d, e = go(tmp_path, sc, "S07", "A2")
    assert decisions(e) == [("AUTHORIZATION_DENIED", "NOT_EXECUTED", "ABORT")]
    assert e["answer"]["status"] == "DENIED" and e["effects"]["credits_total"] == 0
    assert not [x for x in read_jsonl(d / "events.jsonl") if x["kind"] == "tool.dispatch"]


def test_07_invalid_arguments_are_not_a_tool_outage(tmp_path, sc):
    d, e = go(tmp_path, sc, "S06", "A2")
    assert e["decisions"][0][0] == "ARGUMENT_VALIDATION" and e["decisions"][0][2] == "REPAIR"
    assert e["effects"]["credits_total"] == 1


def test_08_trace_continuity_across_retry_crash_resume_reconcile(tmp_path, sc):
    d, e = go(tmp_path, sc, "S16", "A2")
    spans = read_jsonl(d / "telemetry" / "spans.jsonl")
    assert len({s["trace_id"] for s in spans}) == 1
    names = [s["name"] for s in spans]
    assert any(n.startswith("reconcile") for n in names)
    assert {s["worker"] for s in spans} == {"w1", "w2"}                 # both workers' spans, one trace
    # the killed worker's root span never ended, so it was never exported: continuity comes from the journal + a link
    root2 = next(s for s in spans if s["name"].startswith("invoke_agent") and s["worker"] == "w2")
    assert root2["links"] and root2["links"][0]["span_id"] in {s["span_id"] for s in spans if s["worker"] == "w1"}
    _, base = go(tmp_path, sc, "S16", "A0")
    assert base["checks"]["I8"]["result"] == "FAIL"


def test_09_evals_catch_a_behavioural_regression(tmp_path, sc):
    d = tmp_path / "X1"
    run_one(d, sc["S11"], "A2", mutant="X1")                          # timeout treated as a failed call
    e = evaluate(d, sc["S11"], "A2")
    assert e["checks"]["I2"]["result"] == "FAIL" and e["checks"]["RE1"]["result"] == "FAIL"


def test_10_model_change_cannot_violate_invariants(tmp_path, sc):
    d, e = go(tmp_path, sc, "S00", "A2", model_change="scripted-v2")
    assert e["effects"]["credits_total"] == 0                          # the wrong charge never gets a credit
    assert e["answer"]["status"] == "REQUIRES_HUMAN"
    assert all(e["checks"][c]["result"] != "FAIL" for c in ("I1", "I2", "I3", "I4", "I9"))
