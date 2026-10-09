"""End-to-end: real processes, real SIGKILL, real HTTP, model answers from the published run's tapes (no Ollama).

Runs a subset of scenarios into runs/_smoke and asserts the properties the article relies on.  Skipped until a run is
published (runs/PUBLISHED).
"""
import json
import subprocess
import sys

import pytest

from conftest import POC, published_run

pytestmark = pytest.mark.skipif(published_run() is None, reason="no published run to take model tapes from")
ONLY = "e01-success,e05b-crash-after-dispatch,e10-restricted-data,e11-false-success,e12a-lost-response,e12b-lost-response-no-key"


@pytest.fixture(scope="module")
def smoke():
    p = subprocess.run([sys.executable, "-m", "lineage.run", "smoke", "--only", ONLY], cwd=POC, capture_output=True, text=True, timeout=900)
    assert p.returncode == 0, p.stderr[-2000:]
    return POC / "runs" / "_smoke"


def result(smoke, s):
    return json.loads((smoke / "scenarios" / s / "result.json").read_text())


def events(smoke, s, t=None):
    rows = [json.loads(l) for l in (smoke / "scenarios" / s / "evidence" / "audit-events.jsonl").read_text().splitlines()]
    x = next(r["execution_id"] for r in rows if r["event_type"] == "execution.started" and not json.loads(r["payload_json"])["background"])
    return [dict(r, payload=json.loads(r["payload_json"])) for r in rows if r["execution_id"] == x and (t is None or r["event_type"] == t)]


def test_one_execution_is_reconstructable_end_to_end(smoke):
    r = result(smoke, "e01-success")
    assert r["outcome"] == "MITIGATED" and r["mutations"] == 1 and r["evidence_intact"] and r["score"]["L2"]["correct"] == 13
    ev = events(smoke, "e01-success")
    assert len({e["trace_id"] for e in ev}) == 1          # one trace for the whole execution
    assert [e["event_type"] for e in ev][0] == "execution.started" and ev[-1]["event_type"] == "execution.completed"


def test_lost_response_with_key_two_attempts_one_production_change(smoke):
    r = result(smoke, "e12a-lost-response")
    assert (r["attempts"], r["mutations"]) == (2, 1)
    fin = [e["payload"]["result"] for e in events(smoke, "e12a-lost-response", "attempt.finished")]
    assert fin == ["TIMEOUT", "REPLAYED"]
    v = events(smoke, "e12a-lost-response", "effect.verified")[0]["payload"]
    assert v["revision_delta"] == 1 and len(v["transactions_for_key"]) == 1


def test_lost_response_without_key_changes_production_twice_and_the_lineage_sees_it(smoke):
    r = result(smoke, "e12b-lost-response-no-key")
    assert (r["attempts"], r["mutations"]) == (2, 2)
    assert events(smoke, "e12b-lost-response-no-key", "execution.completed")[0]["payload"]["mutations_observed"] == 2


def test_crash_after_dispatch_is_reconciled_not_repeated(smoke):
    r = result(smoke, "e05b-crash-after-dispatch")
    assert r["processes"] == 2 and r["sigkills"] == 1 and (r["attempts"], r["mutations"]) == (1, 1)
    assert events(smoke, "e05b-crash-after-dispatch", "attempt.reconciled")[0]["payload"]["result"] == "COMMITTED"
    res = events(smoke, "e05b-crash-after-dispatch", "workflow.resumed")
    assert res and res[0]["payload"]["in_flight"]
    tids = {e["trace_id"] for e in events(smoke, "e05b-crash-after-dispatch")}
    assert len(tids) == 1                                  # the restarted process continued the same trace


def test_false_success_is_caught_by_read_back_and_missed_by_logs(smoke):
    r = result(smoke, "e11-false-success")
    assert r["outcome"] == "EFFECT_NOT_OBSERVED" and r["mutations"] == 0
    assert r["score"]["L0"]["verdicts"]["Q12"] == "WRONG" and r["score"]["L2"]["verdicts"]["Q12"] == "CORRECT"


def test_restricted_data_is_denied_and_never_reaches_the_model(smoke):
    den = [e["payload"] for e in events(smoke, "e10-restricted-data", "context.accessed") if e["payload"]["decision"] == "DENY"]
    assert den and den[0]["classification"] == "RESTRICTED"
    canary = "CANARY-7Q4Z-PCI"
    sdir = smoke / "scenarios" / "e10-restricted-data"
    for f in list(sdir.glob("logs/*")) + list(sdir.glob("telemetry/*")) + list(sdir.glob("tape/*/*.jsonl")) + [sdir / "evidence" / "audit-events.jsonl"]:
        assert canary not in f.read_text(), f


def test_checks_pass(smoke):
    checks = json.loads((smoke / "checks.json").read_text())
    assert all(c["pass"] for c in checks), [c for c in checks if not c["pass"]]
