"""The proof pack: run the protocol experiments (H1–H9 × arms A, B, C), the arm-C conformance suite and the HTTP round
trip, then write the pae-proof/v1 evidence.  Refuses to run if a preregistered file changed after the freeze.

    evidence/runs/<run>/
        manifest.json · results.json · facts.json · checks.jsonl · summary.json · summary.md · SHA256SUMS   (pae-proof/v1)
        story.json                                   the opening story (H5c), recorded: timeline, revalidation, every arm's outcome
        experiments.json                             every scenario × arm: oracle, outcome, metrics (the table behind the report)
        prereg/                                      the frozen preregistration, checks, FREEZE.json and DEVIATIONS.md, as run
        raw/scenarios/<sid>/<arm>/                   scenario.json (steps, metrics, reconstruction, transitions, effects),
                                                     audit.jsonl (the hash-chained platform audit), records.json (the arm's own records)
        raw/tests/HITL-Tnn.json · test-report.json · test-report.md      the conformance suite
        raw/api.json · fixtures/
    evidence/negative-control/results.json           arms A and B as the controls (safeguards removed), C as governed
    evidence/published.json                          written only by `hitl promote`

Nothing here types an observed value: facts are read from the outcomes, checks compare facts, claims rest on checks.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import platform
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from hitl import freeze as FZ
from hitl.scenarios import EXPERIMENTS, PREREG, QUESTIONS, SCENARIOS, run_all
from hitl.suite import CATEGORIES, INVARIANTS, TESTS, run_suite

POC = Path(__file__).resolve().parents[1]
ROOT = POC.parent
sys.path.insert(0, str(ROOT / "vendor"))
from evidence_kit import proof  # noqa: E402
from evidence_kit.facts import Facts  # noqa: E402

EVIDENCE = POC / "evidence"
ARMS = PREREG["design"]["arms"]
NUMERIC = ["writes", "state_changes", "unauthorized_executions", "legit_executions", "ineligible_approver_acceptances", "reapproval_requests",
           "rejected_on_resume", "escalations_recorded", "audit_reconstruction_gaps"]
GLOBAL_CLASS = {"mutated_action_bypasses": "mutation", "successful_approval_replays": "replay", "duplicate_external_side_effects": "duplicate",
                "expired_approval_executions": "expiry", "executions_after_deny_or_timeout": "deny", "silent_stale_context_resumes": "stale"}


def _toml(name: str) -> dict:
    return tomllib.loads((POC / "proof" / name).read_text())


def test_report(outcomes, run_id: str) -> dict[str, Any]:
    tests = [{"id": o.id, "name": o.name, "category": f"{o.category} · {CATEGORIES[o.category]}", "invariants": o.invariants,
              "result": "pass" if o.passed else "fail", "error": o.error,
              "assertions": {k: {"observed": v["observed"], "expected": v["expected"], "held": v["held"]} for k, v in o.assertions.items()},
              "measured": o.measured, "evidence": f"raw/tests/{o.id}.json"} for o in outcomes]
    p = sum(t["result"] == "pass" for t in tests)
    return {"suite": "human-in-the-loop-conformance", "version": "2.0", "run_id": run_id, "total": len(tests), "passed": p, "failed": len(tests) - p,
            "invariants": INVARIANTS, "tests": tests}


def report_md(rep: dict[str, Any]) -> str:
    L = [f"# Arm C conformance suite · run `{rep['run_id']}`", "",
         f"**{rep['passed']}/{rep['total']} conformance tests passed** ({rep['failed']} failed). Deterministic: no model, no network, fake clock, "
         "fixed identities, simulated enterprise systems. Each test lists what it observed against what it expected.", "",
         "## Invariants", ""] + [f"- **{k}** {v}" for k, v in rep["invariants"].items()] + ["", "## Tests", "",
         "| Test | Category | Result | Assertions (observed = expected) |", "|---|---|---|---|"]
    for t in rep["tests"]:
        a = "; ".join(f"{k} = {json.dumps(v['observed'])}" + ("" if v["held"] else f" (expected {json.dumps(v['expected'])})") for k, v in t["assertions"].items())
        L.append(f"| {t['id']} · {t['name']} | {t['category'].split(' · ')[0]} | {'PASS' if t['result'] == 'pass' else '**FAIL**'} | {a} |")
    return "\n".join(L) + "\n"


def api_roundtrip(work: Path) -> dict[str, Any]:
    from hitl.api import roundtrip
    return roundtrip(work / "api")


# ---- facts from the scenario outcomes ---------------------------------------------------------------------------------
def scenario_facts(F: Facts, outs: dict, run_id: str, rel: str) -> None:
    for (sid, arm), o in outs.items():
        src, rows = f"{rel}/raw/scenarios/{sid}/{arm}/scenario.json → metrics", {"run": run_id, "ids": [f"{sid}/{arm}"]}
        for k in NUMERIC + ["questions_answered"]:
            if o.metrics.get(k) is not None:
                F.add(f"{sid}.{arm}.{k}", o.metrics[k], source=f"{src}.{k}", rows=rows, derivation="read from the scenario's systems of record")
        F.add(f"{sid}.{arm}.final_code", o.metrics.get("final_code") or "none", source=f"{src}.final_code", rows=rows,
              derivation="the code of the scenario's last resume")
    for x, X in EXPERIMENTS.items():
        sids = [s["id"] for s in X["scenarios"]]
        for arm in ARMS:
            ids = [f"{s}/{arm}" for s in sids]
            for k in NUMERIC:
                F.add(f"{x}.{arm}.{k}", sum(outs[(s, arm)].metrics.get(k, 0) or 0 for s in sids), source=f"{rel}/raw/scenarios/ → {x}*/{arm} metrics.{k} (summed)",
                      rows={"run": run_id, "ids": ids}, derivation=f"sum over {x}'s {len(sids)} scenarios under arm {arm}")
            for k, c in GLOBAL_CLASS.items():                  # the class metrics the preregistration names per experiment (H8)
                F.add(f"{x}.{arm}.{k}", sum(outs[(s, arm)].metrics.get("unauthorized_executions", 0) for s in sids if outs[(s, arm)].metrics.get("class") == c),
                      source=f"{rel}/raw/scenarios/ → {x}*/{arm} metrics.unauthorized_executions where class = {c} (summed)",
                      rows={"run": run_id, "ids": ids}, derivation=f"excess writes in {x}'s scenarios of class {c} under arm {arm}")
    for c in _toml("experiments.toml")["experiments"]:                       # scoped sums the preregistration asks for
        for ch in c.get("checks", []):
            parts = ch["fact"].split(".")
            if len(parts) == 4 and "_" in parts[3] and parts[3] not in F.d:
                x, arm, k, scope = parts
                sids = scope.split("_")
                F.add(ch["fact"], sum(outs[(s, arm)].metrics.get(k, 0) or 0 for s in sids), source=f"{rel}/raw/scenarios/ → {'+'.join(sids)}/{arm} metrics.{k} (summed)",
                      rows={"run": run_id, "ids": [f"{s}/{arm}" for s in sids]}, derivation=f"sum over {', '.join(sids)} under arm {arm}")
    for arm in ARMS:
        ids = [f"{s}/{arm}" for s in SCENARIOS]
        mine = [outs[(s, arm)] for s in SCENARIOS]
        g = {"unauthorized_executions": sum(o.metrics.get("unauthorized_executions", 0) for o in mine),
             "ineligible_approver_acceptances": sum(o.metrics.get("ineligible_approver_acceptances", 0) for o in mine),
             "audit_reconstruction_gaps": sum(o.metrics.get("audit_reconstruction_gaps", 0) for o in mine)}
        g.update({k: sum(o.metrics.get("unauthorized_executions", 0) for o in mine if o.metrics.get("class") == c) for k, c in GLOBAL_CLASS.items()})
        g["writes"] = sum(o.metrics.get("writes", 0) for o in mine)
        g["state_changes"] = sum(o.metrics.get("state_changes", 0) for o in mine)
        g["legit_executions"] = sum(o.metrics.get("legit_executions", 0) for o in mine)
        g["scenarios_completed"] = sum(o.error is None for o in mine)
        for k, v in g.items():
            F.add(f"global.{arm}.{k}", v, source=f"{rel}/experiments.json → arms.{arm}.global.{k}", rows={"run": run_id, "ids": ids},
                  derivation=f"over all {len(ids)} scenarios under arm {arm}")
        F.add(f"all.{arm}.audit_reconstruction_gaps", g["audit_reconstruction_gaps"], source=f"{rel}/experiments.json → arms.{arm}.global.audit_reconstruction_gaps",
              rows={"run": run_id, "ids": ids}, derivation="executed writes whose records answer fewer than 16 questions, all scenarios")
        writes_rec = [r for o in mine for r in o.reconstruction]
        F.add(f"global.{arm}.reconstructed_writes", len(writes_rec), source=f"{rel}/raw/scenarios/ → */{arm} reconstruction", rows={"run": run_id, "ids": ids})


def build_story(run: Path, rel: str) -> dict[str, Any]:
    """The opening story (H5c), from the recorded files only."""
    sc = {arm: json.loads((run / "raw" / "scenarios" / "H5c" / arm / "scenario.json").read_text()) for arm in ARMS}
    c = sc["C"]
    audit = [json.loads(l) for l in (run / "raw" / "scenarios" / "H5c" / "C" / "audit.jsonl").read_text().splitlines()]
    req = next(r for r in audit if r["kind"] == "approval.requested")
    shown = next(r for r in audit if r["kind"] == "channel.posted")["record"]["shown"]
    pol = next(r for r in audit if r["kind"] == "policy.evaluated" and r["proposal_id"] == req["proposal_id"])
    ev = next(r for r in audit if r["kind"] == "event.received")
    resume = next(s for s in c["steps"] if s["kind"] == "resume")
    decision = next(s for s in c["steps"] if s["kind"] == "decision")
    sev = next((e for e in c["effects"] if e["kind"] == "incident.severity"), None)
    checked = {x["check"] for x in resume["result"].get("checks", [])}
    timeline = [{"time": ev["time"], "what": "Datadog event received", "detail": f"{ev['record']['service']} · error rate {ev['record']['signal']['error_rate']:.0%}"},
                {"time": pol["time"], "what": f"Policy → {pol['record']['decision']}", "detail": f"{pol['record']['policy_id']} v{pol['record']['policy_version']} · {pol['record']['rule']}"},
                {"time": req["time"], "what": "Approval request created", "detail": f"action_digest sha256:{req['record']['action_digest'][:12]}…"}]
    timeline += [{"time": s["time"], "what": s["label"], "detail": s["actor"]} for s in c["steps"] if s["kind"] == "world"]
    timeline += [{"time": decision["time"], "what": "Human approves", "detail": f"{decision['actor']} · {decision['channel']}"},
                 {"time": resume["time"], "what": "Resume → revalidate", "detail": f"on {resume['runtime']}"},
                 {"time": resume["time"], "what": f"{resume['result']['state']} ({resume['result']['code']})", "detail": resume["result"]["detail"]}]
    t0 = dt.datetime.fromisoformat(req["time"].replace("Z", "+00:00"))
    td = dt.datetime.fromisoformat(decision["time"].replace("Z", "+00:00"))
    return {"schema": "hitl-story/v1", "scenario": "H5c", "title": c["title"], "source": f"{rel}/raw/scenarios/H5c/",
            "incident": shown.get("incident"), "request": {"proposal_id": req["proposal_id"], "created": req["time"], "shown": shown,
            "action_digest": req["record"]["action_digest"], "policy_decision_id": pol["record"]["policy_decision_id"],
            "expires_at": shown.get("expires")}, "approval_wait_minutes": round((td - t0).total_seconds() / 60, 2),
            "timeline": timeline, "revalidation": resume["result"].get("checks", []),
            "not_revalidated": ([{"what": "incident severity", "at_request": sev["from"], "at_approval": sev["to"],
                                  "note": "shown on the approval card; no revalidation check covers it"}] if sev and not any("severity" in x for x in checked) else []),
            "outcome": {arm: {"code": sc[arm]["metrics"]["final_code"], "writes": sc[arm]["metrics"]["writes"],
                              "effects": [{k: e.get(k) for k in ("kind", "service", "environment", "from", "to", "changed", "by")} for e in sc[arm]["effects"] if e["kind"] == "rollback"]}
                        for arm in ARMS},
            "transitions": [t for t in c["transitions"] if t["proposal_id"] == req["proposal_id"]]}


def build(run_id: str) -> Path:
    fz = FZ.check()
    if not fz["ok"]:
        raise SystemExit("refusing to run: preregistered files changed after the freeze (record a deviation in proof/DEVIATIONS.md, "
                         f"then `hitl freeze`): {fz['changed_guarded']}")
    run = EVIDENCE / "runs" / run_id
    shutil.rmtree(run, ignore_errors=True)
    (run / "raw").mkdir(parents=True)
    started = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with tempfile.TemporaryDirectory(prefix="hitl-") as tmp:
        work = Path(tmp)
        outs = run_all(work / "scenarios", raw=run / "raw" / "scenarios")
        tests = run_suite(work / "suite", raw=run / "raw" / "tests")
        api = api_roundtrip(work)
    (run / "raw" / "api.json").write_text(json.dumps(api, indent=1, sort_keys=True))
    fx = run / "fixtures"
    fx.mkdir()
    for f in sorted((POC / "config").glob("*.yaml")):
        shutil.copy(f, fx / f.name)
    shutil.copy(POC / "hitl" / "enterprise.py", fx / "enterprise_scenario.py")
    pre = run / "prereg"
    pre.mkdir()
    for f in ("preregistration.toml", "experiments.toml", "FREEZE.json", "DEVIATIONS.md"):
        shutil.copy(POC / "proof" / f, pre / f)

    rep = test_report(tests, run_id)
    (run / "test-report.json").write_text(json.dumps(rep, indent=1, sort_keys=True, default=str))
    (run / "test-report.md").write_text(report_md(rep))
    rel = f"evidence/runs/{run_id}"
    table = {"arms": {arm: {"title": PREREG["arms"][arm]["title"], "summary": PREREG["arms"][arm]["summary"]} for arm in ARMS},
             "scenarios": [{"id": sid, "experiment": SCENARIOS[sid]["experiment"], "title": SCENARIOS[sid]["title"], "class": SCENARIOS[sid]["class"],
                            "arms": {arm: {"metrics": outs[(sid, arm)].metrics, "error": outs[(sid, arm)].error} for arm in ARMS}} for sid in SCENARIOS],
             "questions": QUESTIONS}

    F = Facts()
    scenario_facts(F, outs, run_id, rel)
    for arm in ARMS:
        table["arms"][arm]["global"] = {k.split(".")[-1]: F.value(k) for k in F.d if k.startswith(f"global.{arm}.")}
    (run / "experiments.json").write_text(json.dumps(table, indent=1, sort_keys=True, default=str))
    story = build_story(run, rel)
    (run / "story.json").write_text(json.dumps(story, indent=1, sort_keys=True, default=str))
    F.add("story.approval_wait_minutes", story["approval_wait_minutes"], source=f"{rel}/story.json#approval_wait_minutes",
          derivation="decision time − request time, H5c under arm C")
    for arm in ARMS:
        F.add(f"story.{arm}.final_code", story["outcome"][arm]["code"], source=f"{rel}/story.json#outcome.{arm}.code")
        F.add(f"story.{arm}.writes", story["outcome"][arm]["writes"], source=f"{rel}/story.json#outcome.{arm}.writes")
    F.add("story.failed_checks", sum(not x["ok"] for x in story["revalidation"]), source=f"{rel}/story.json#revalidation")
    F.add("story.checks", len(story["revalidation"]), source=f"{rel}/story.json#revalidation")
    F.add("story.not_revalidated", len(story["not_revalidated"]), source=f"{rel}/story.json#not_revalidated")
    for o in tests:
        src = f"{rel}/test-report.json#tests[id={o.id}]"
        rows = {"run": run_id, "ids": [o.id]}
        F.add(f"tests.{o.id}.assertions", len(o.assertions), source=src, rows=rows, derivation="number of assertions the test makes")
        F.add(f"tests.{o.id}.held", sum(a["held"] for a in o.assertions.values()) if o.error is None else 0, source=src, rows=rows,
              derivation="assertions whose observed value equals the expected value")
        for k, v in o.measured.items():
            F.add(f"tests.{o.id}.{k}", v, source=f"{src}.measured.{k}", rows=rows, derivation="observed in the systems of record during the test")
    F.add("tests.total", rep["total"], source=f"{rel}/test-report.json#total")
    F.add("tests.passed", rep["passed"], source=f"{rel}/test-report.json#passed")
    F.add("tests.failed", rep["failed"], source=f"{rel}/test-report.json#failed")
    F.add("tests.invariants", len(INVARIANTS), source=f"{rel}/test-report.json#invariants")
    F.add("api.calls", api["calls"], source=f"{rel}/raw/api.json#calls")
    F.add("api.calls_ok", api["calls_ok"], source=f"{rel}/raw/api.json#calls_ok")
    F.add("api.rollbacks", api["rollbacks"], source=f"{rel}/raw/api.json#rollbacks")
    F.add("design.arms", len(ARMS), source="proof/preregistration.toml#design.arms")
    F.add("design.experiments", len(EXPERIMENTS), source="proof/preregistration.toml#experiments")
    F.add("design.scenarios", len(SCENARIOS), source="proof/preregistration.toml#experiments.scenarios")
    F.add("design.scenario_runs", len(outs), source=f"{rel}/experiments.json", derivation="scenarios × arms actually run")
    F.add("design.request_ttl_min", PREREG["design"]["request_ttl_min"], source="proof/preregistration.toml#design.request_ttl_min")
    F.add("design.questions", len(QUESTIONS), source="hitl/scenarios.py QUESTIONS")
    F.add("design.global_assertions", len(PREREG["global"]), source="proof/preregistration.toml#global")
    F.add("run.id", run_id)

    exps, checks = proof.evaluate(_toml("experiments.toml"), F)
    spec = {c["id"]: (c, x.get("h")) for x in _toml("experiments.toml")["experiments"] for c in x.get("checks", [])}
    for c in checks:                                  # the readable label (H5-B01: H5, arm B, prediction 1) beside the contract id
        c["arm"], c["label"], c["h"] = spec[c["id"]][0].get("arm"), spec[c["id"]][0].get("label"), spec[c["id"]][1]
    F.add("checks.total", len(checks), source=f"{rel}/checks.jsonl")
    F.add("checks.pass", sum(c["status"] == "PASS" for c in checks), source=f"{rel}/checks.jsonl")
    F.add("checks.fail", sum(c["status"] == "FAIL" for c in checks), source=f"{rel}/checks.jsonl")
    F.add("checks.expected_failure", sum(c["status"] == "EXPECTED_FAILURE" for c in checks), source=f"{rel}/checks.jsonl")
    F.add("checks.not_supported", sum(c["finding"] == "NOT SUPPORTED" for c in checks), source=f"{rel}/checks.jsonl")
    claims, problems = proof.trace(_toml("claims.toml"), exps, checks)
    if problems:
        raise SystemExit("claim trace problems: " + "; ".join(problems))
    mt = _toml("manifest.toml")
    completed = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {
        "schema": proof.SCHEMA, "series": mt["article"]["series"], "article_id": mt["article"]["id"], "poc": mt["article"]["poc"], "run_id": run_id,
        "scenario": mt["article"]["scenario"], "source_commit": "unknown (not a git repository)", "runtime_mode": mt["run"]["runtime_mode"],
        "started_at": started, "completed_at": completed,
        "environment": {"os": platform.system(), "arch": platform.machine(), "python": platform.python_version(), "model_runtime": "none",
                        "model": "none (deterministic EvidenceReasoner and agent plan)", "model_version": "n/a", "temperature": "n/a",
                        "seed": "none: no randomness (fake clock, fixed identities, scripted human decisions)"},
        "benchmark": {"modes": [f"arm {a} · {PREREG['arms'][a]['title']}" for a in ARMS] + ["conformance suite (arm C)", "api-roundtrip"],
                      "approval_models": {a: PREREG["arms"][a]["title"] for a in ARMS}, "experiments": len(exps), "checks": len(checks),
                      "scenarios": len(SCENARIOS), "scenario_runs": len(outs), "conformance_tests": len(TESTS), "unit_tests": 5},
        "preregistration": {"frozen_at": fz["frozen_at"], "note": fz["note"], "guarded_sha256": fz["guarded_sha256"],
                            "scenario_fixture_sha256": fz["scenario_fixture_sha256"], "code_changed_since_freeze": fz["changed_code"],
                            "deviations": "prereg/DEVIATIONS.md"},
        "execution_profile": {"classes": [{"class": r["class"], "items": r["items"]} for r in mt["reality"]],
                              "groups": [{"name": "protocol experiments H1–H9 under arms A, B, C, and the global assertions",
                                          "experiments": [x["id"] for x in exps if str(x.get("h", "")).startswith(("H", "GA"))]},
                                         {"name": "conformance and HTTP", "experiments": [x["id"] for x in exps if x.get("h") in ("CS", "API")]}]},
        "entrypoints": mt["entrypoints"], "integrity": {"sha256sums": f"{rel}/SHA256SUMS"},
        "config_sha256": {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((POC / "config").glob("*.yaml"))},
        "policy_fixture_sha256": {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((POC / "config").glob("policy*.yaml"))},
        "scenario_fixture_sha256": FZ.fixture_sha(),
        "provenance": {"manifest_origin": "built by hitl/proofpack.py from proof/manifest.toml, proof/FREEZE.json and the run",
                       "fields": {"started_at": "recorded", "completed_at": "recorded", "environment": "recorded", "source_commit": "unknown",
                                  "benchmark": "recorded", "preregistration": "proof/FREEZE.json", "execution_profile": "frozen (proof/manifest.toml)"}},
    }
    res = proof.results(run_id, manifest, exps, checks, F, claims=claims, profile=manifest["execution_profile"],
                        paths={"experiments": f"{rel}/experiments.json", "story": f"{rel}/story.json", "test_report": f"{rel}/test-report.json", "raw": f"{rel}/raw/"})
    summ, summ_md = proof.summary(res, "T3 · Human-in-the-Loop · proof summary")
    (run / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (run / "results.json").write_text(json.dumps(res, indent=1, default=str))
    (run / "checks.jsonl").write_text(proof.checks_jsonl(checks))
    (run / "summary.json").write_text(json.dumps(summ, indent=1))
    (run / "summary.md").write_text(summ_md)
    (run / "facts.json").write_text(json.dumps(F.to_json(), indent=1, sort_keys=True, default=str))

    nc = EVIDENCE / "negative-control"
    nc.mkdir(parents=True, exist_ok=True)
    controls = [c for c in checks if c["kind"] == "control"]
    (nc / "results.json").write_text(json.dumps({
        "schema": proof.SCHEMA, "run_id": run_id,
        "safeguard_removed": ["arm A: digest binding, approver authentication and eligibility, expiry, single use and resume revalidation (approved = true)",
                              "arm B: resume revalidation (identity, delegation, policy, resource state, approver) and atomic consume"],
        "invariant": [g["metric"].replace("_", " ") + " = 0" for g in PREREG["global"]],
        "expected": "under arm A every control check breaks (EXPECTED_FAILURE); arm C holds every global assertion",
        "governed": {"arm": "C", **{g["metric"]: F.value(f"global.C.{g['metric']}") for g in PREREG["global"]}},
        "mutated": {arm: {g["metric"]: F.value(f"global.{arm}.{g['metric']}") for g in PREREG["global"]} for arm in ARMS if arm != "C"},
        "control_checks": {c["id"]: c["status"] for c in controls},
        "harness_completed": all(o.error is None for o in outs.values()),
        "result": "EXPECTED_FAILURE" if controls and all(c["status"] == "EXPECTED_FAILURE" for c in controls) else "FAIL"}, indent=1))

    files = sorted(p for p in run.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    (run / "SHA256SUMS").write_text(proof.sha256sums(files, run))
    return run


def promote(run_id: str, reason: str) -> Path:
    run = EVIDENCE / "runs" / run_id
    from hitl.verify import verify
    report = verify(run_id)
    if not report.verified:
        raise SystemExit("refusing to promote: the run does not verify")
    pub = EVIDENCE / "published.json"
    old = json.loads(pub.read_text()) if pub.exists() else None
    hist = old.get("history", []) if old else []
    if old and old["run_id"] != run_id:      # a rebuilt run re-promoted under its own id does not supersede itself
        hist = hist + [{"run_id": old["run_id"], "reason": old["reason"], "results_sha256": old["results_sha256"]}]
    pub.write_text(json.dumps({"schema": proof.SCHEMA, "article": "T3", "run_id": run_id, "reason": reason,
                               "manifest": f"evidence/runs/{run_id}/manifest.json", "results": f"evidence/runs/{run_id}/results.json",
                               "results_sha256": proof.sha256_file(run / "results.json"), "sha256sums": f"evidence/runs/{run_id}/SHA256SUMS",
                               "verification": "evidence/verification/verification.json", "history": hist}, indent=1))
    return pub
