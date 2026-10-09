"""Publication baseline (Proof Contract v1 §9 step 5): what the capstone published before it adopted the contract.

    python3 tools/publication_baseline.py                  -> docs/proof-standardization/original-publication-baseline.{json,md}
    python3 tools/publication_baseline.py delta <run>      -> docs/proof-standardization/proof-refresh-delta.{json,md}

Captured once, before any article or proof edit, and never overwritten (the script refuses if the files exist). Every
value is read from the published run, the derived facts and the built pages; nothing is typed. The SHA-256 of each
published artifact pins exactly which files the baseline describes.
"""

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "production_agentic_ai_platform"
OUT = ROOT / "docs" / "proof-standardization"
ARTIFACTS = ["technical/production-agentic-ai-platform-final-reference-architecture.md",
             "technical/production-agentic-ai-platform-final-reference-architecture.html",
             "technical/production-agentic-ai-platform-final-reference-architecture.pdf",
             "medium/production-agentic-ai-platform-medium.md", "medium/production-agentic-ai-platform-medium.html",
             "medium/production-agentic-ai-platform-medium.pdf", "results/production-agentic-ai-platform-lab.html",
             "production_agentic_ai_platform/lab/index.html", "production_agentic_ai_platform/README.md", "README.md", "QA.md",
             "docs/facts.json", "docs/evidence-uses.json"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    j, m = OUT / "original-publication-baseline.json", OUT / "original-publication-baseline.md"
    if j.exists() or m.exists():
        print(f"refused: {j.relative_to(ROOT)} exists; the baseline is captured once and never overwritten")
        return 1
    runs = POC / "evidence" / "runs"
    run_id = (runs / "PUBLISHED").read_text().strip()
    run = runs / run_id
    res = json.loads((run / "results.json").read_text())
    rep = json.loads((run / "replay-comparison.json").read_text())
    prev = json.loads((run / "previous-run-comparison.json").read_text()) if (run / "previous-run-comparison.json").exists() else None
    neg = json.loads((POC / "evidence" / "negative-control" / "control.json").read_text())
    uses = json.loads((ROOT / "docs" / "evidence-uses.json").read_text())
    env, T, X = res["environment"], res["totals"], {e["id"]: e for e in res["experiments"]}
    kills = sum(1 for rc in X["R9"]["facts"]["returncodes"] if rc == -9) + sum(1 for k in ("lookup", "resend", "naive") if X["R10"]["facts"][k]["sigkill"] == -9)
    readme = (POC / "README.md").read_text()
    lab = (ROOT / "results" / "production-agentic-ai-platform-lab.html").read_text()
    byline = re.search(r"(Proof run|Published) (\d{4}-\d{2}-\d{2})", (ROOT / "medium" / "production-agentic-ai-platform-medium.html").read_text())
    base = {
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "purpose": "the capstone's published state before adopting the Production AI Engineering Proof Contract v1",
        "published_pointer": {"file": "production_agentic_ai_platform/evidence/runs/PUBLISHED", "run_id": run_id,
                              "note": "a plain-text pointer; the contract's evidence/published.json did not exist yet"},
        "previous_published_run": prev["run_a"] if prev else None,
        "headline": {"run_id": run_id, "finished_at": res["finished_at"], "experiments": T["experiments"],
                     "experiments_passed": T["experiments_passed"], "checks": T["checks"], "checks_passed": T["passed"],
                     "checks_failed": T["failed"], "unit_tests": res["unit_tests"]["total"], "unit_tests_passed": res["unit_tests"]["passed"],
                     "wall_clock_s": res["wall_clock_s"], "harness_exceptions": len(res.get("harness_exceptions", [])),
                     "mcp_transport": env["mcp_transport"], "mcp_sdk": env["mcp_sdk"], "checkpoint_store": env["checkpoint_store"],
                     "model_mode": env["model_mode"], "tracing": env["tracing"], "opentelemetry_sdk": env["opentelemetry_sdk"],
                     "crash_injection": env["crash_injection"], "sigkills_recorded_in_results": kills,
                     "policy_engine": env["policy_engine"], "python": env["python"], "platform": env["platform"],
                     "source_sha256": env.get("source_sha256"), "agent_code_sha256": env["agent_code_sha256"],
                     "evidence_counts": res["evidence_counts"]},
        "experiments": [{"id": e["id"], "title": e["title"], "checks": e["total"], "passed": e["passed"], "status": e["status"]} for e in res["experiments"]]
                       + [{"id": "X", "title": "Cross-cutting", "checks": len(res["cross_checks"]), "passed": sum(c["passed"] for c in res["cross_checks"]),
                           "status": "PASS" if all(c["passed"] for c in res["cross_checks"]) else "FAIL"}],
        "replay": {k: rep[k] for k in ("run_a", "run_b", "checks_compared", "checks_identical", "ids_compared", "ids_identical", "expected_to_differ")},
        "previous_run_comparison": ({k: prev[k] for k in ("run_a", "run_b", "checks_compared", "checks_identical", "checks_different", "ids_identical")}
                                    if prev else None),
        "negative_control": {k: neg[k] for k in ("proof_exit_code", "experiments_failed", "checks_failed", "checks", "harness_exceptions",
                                                 "behaves_as_negative_control")},
        "article_facts": {k: {"value": v["value"], "used_in": v["used_in"]} for k, v in sorted(uses.items())},
        "byline": byline.group(0) if byline else None,
        "readme_published_line": next((l for l in readme.splitlines() if l.startswith("**Published run:**")), None),
        "lab_run_id_matches": f">{run_id}<" in lab or f"`{run_id}`" in lab or run_id in lab,
        "artifacts": {a: sha(ROOT / a) for a in ARTIFACTS if (ROOT / a).exists()},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    j.write_text(json.dumps(base, indent=1, default=str) + "\n")
    h = base["headline"]
    md = ["# Original publication baseline", "",
          f"Captured {base['captured_at']} by `tools/publication_baseline.py`, before the capstone adopted the Production AI Engineering",
          "Proof Contract v1. It records what was published, read from the published run, the derived facts and the built pages.",
          "It is never regenerated; `proof-refresh-delta.md` compares any later published run with it.", "",
          "## Published run", "", "| Metric | Value |", "|---|---|"]
    md += [f"| {k.replace('_', ' ')} | {('`' + str(v) + '`') if k in ('run_id', 'source_sha256', 'agent_code_sha256') else v} |"
           for k, v in h.items() if k != "evidence_counts"]
    md += [f"| evidence records | {', '.join(f'{k} {v:,}' for k, v in h['evidence_counts'].items())} |",
           f"| published pointer | `{base['published_pointer']['file']}` (plain text; no `evidence/published.json`) |",
           f"| replaced run | `{base['previous_published_run']}` |", "",
           "## Experiments", "", "| Id | Title | Checks | Passed | Status |", "|---|---|---|---|---|"]
    md += [f"| {e['id']} | {e['title']} | {e['checks']} | {e['passed']} | {e['status']} |" for e in base["experiments"]]
    r = base["replay"]
    n = base["negative_control"]
    md += ["", "## Replay and negative control", "",
           f"- Replay `{r['run_a']}` vs `{r['run_b']}`: {r['checks_identical']}/{r['checks_compared']} checks and "
           f"{r['ids_identical']}/{r['ids_compared']} content-derived ids identical; expected to differ: {', '.join(r['expected_to_differ'])}.",
           f"- Negative control (approval requirement removed): proof exit {n['proof_exit_code']}, {n['checks_failed']} of {n['checks']} checks "
           f"failed in {', '.join(n['experiments_failed'])}, harness exceptions {len(n['harness_exceptions'])}.", "",
           "## Facts the articles printed", "", "| Fact | Value | Used in |", "|---|---|---|"]
    md += [f"| `{k}` | {json.dumps(v['value'])[:90]} | {', '.join(v['used_in'])} |" for k, v in base["article_facts"].items()]
    md += ["", f"Byline: {base['byline']}. README: {base['readme_published_line']}", "", "## Published artifacts (SHA-256)", "",
           "| File | SHA-256 |", "|---|---|"] + [f"| `{a}` | `{d}` |" for a, d in base["artifacts"].items()]
    m.write_text("\n".join(md) + "\n")
    print(f"baseline -> {j.relative_to(ROOT)}, {m.relative_to(ROOT)} ({len(base['article_facts'])} article facts, {len(base['artifacts'])} artifacts)")
    return 0


DELTA_REASONS = {
    "checks": "the contract counts proof checks: each harness assertion becomes one check evaluated by evidence_kit.proof from the recorded facts "
              "(obs.<check>), plus the negative control's checks (P1-R14); harness assertions are reported separately",
    "checks_passed": "in-experiment controls (R4 bypass, R8 relevance-only ranking, R10 fresh key per attempt, R12 guard missed) are control checks: "
                     "the safeguard's invariant breaks as intended, EXPECTED_FAILURE, not PASS",
    "expected_failures": "control checks: 5 in-experiment controls and 4 of the negative control's checks; a control that broke as intended",
    "experiments": "the negative control is an experiment of its own (P1-R14) under the contract",
    "sigkills": "recomputed from the raw events (processes that started and neither finished nor parked); results.json recorded 4 because R9's "
                "tampered-checkpoint kill was never written into its facts",
    "replay_level": "declared under the contract; the published comparison already showed identical checks and ids with volatile values differing",
    "published_pointer": "evidence/published.json (pae-proof/v1), written only by promote; the plain-text pointer is kept in step",
    "schema": "the Production AI Engineering Proof Contract v1, evidence-kit 5.2.0 vendored",
    "claims": "proof/claims.toml: every material claim mapped to experiments and checks, each verdict tested against the checks",
    "new_cases": "8 new cases from the standardization brief: R2 staging and environment layers, R4 trusted tool, wrong environment and a write "
                 "through the read path, R5 capabilities for another tool and another operation, R9 one human decision",
    "operation": "R5's new case found that the release server did not compare a capability's operation; capability.verify now does "
                 "(tests/test_units.py::test_capability_operation_must_match_the_call)",
}


def delta(run_id: str, note: str = "") -> int:
    """Every metric of the baseline against the run's proof pack: what changed, and why."""
    base = json.loads((OUT / "original-publication-baseline.json").read_text())
    run = POC / "evidence" / "runs" / run_id
    res = json.loads((run / "results.json").read_text())
    rawres = json.loads((run / "raw" / "results.json").read_text())
    F = {k: v["value"] for k, v in res["facts"].items()}
    c, h = res["check_counts"], base["headline"]
    pub = POC / "evidence" / "published.json"
    rows = [
        ("run_id", h["run_id"], run_id, "same run, standardized" if h["run_id"] == run_id else note or "a new run"),
        ("proof schema", "none", res["schema"], DELTA_REASONS["schema"]),
        ("published pointer", base["published_pointer"]["file"], "production_agentic_ai_platform/evidence/published.json", DELTA_REASONS["published_pointer"]),
        ("experiments", h["experiments"], c["experiments"], DELTA_REASONS["experiments"]),
        ("checks", h["checks"], c["checks"], DELTA_REASONS["checks"] + ("; " + DELTA_REASONS["new_cases"] if rawres["totals"]["checks"] != h["checks"] else "")),
        ("checks passed", h["checks_passed"], c["pass"], DELTA_REASONS["checks_passed"]),
        ("checks failed", h["checks_failed"], c["fail"], ""),
        ("expected failures (controls)", "not reported", c["expected_failure"], DELTA_REASONS["expected_failures"]),
        ("harness assertions", f"{h['checks_passed']}/{h['checks']}", f"{rawres['totals']['passed']}/{rawres['totals']['checks']}",
         "what run_proof.py itself records" + ("; " + DELTA_REASONS["new_cases"] if rawres["totals"]["checks"] != h["checks"] else "")),
        ("claims", "not mapped", len(res["claims"]), DELTA_REASONS["claims"]),
        ("unit tests", f"{h['unit_tests_passed']}/{h['unit_tests']}", f"{F['unit_tests_passed']}/{F['unit_tests']}",
         DELTA_REASONS["operation"] if F["unit_tests"] != h["unit_tests"] else ""),
        ("wall-clock seconds", h["wall_clock_s"], F["wall_clock_s"], "not a performance claim: varies between runs"),
        ("SIGKILLed processes", h["sigkills_recorded_in_results"], F["raw.sigkills"], DELTA_REASONS["sigkills"]),
        ("replay level", "not declared", F["replay.level"], DELTA_REASONS["replay_level"]),
        ("replay checks identical", f"{base['replay']['checks_identical']}/{base['replay']['checks_compared']}",
         f"{F['replay_checks_identical']}/{F['replay_checks_compared']}",
         "every harness check of the new run replayed identically" if F["replay_checks_compared"] != base["replay"]["checks_compared"] else ""),
        ("replay ids identical", f"{base['replay']['ids_identical']}/{base['replay']['ids_compared']}", f"{F['replay_ids_identical']}/{F['replay_ids_compared']}", ""),
        ("negative control: checks failed", f"{base['negative_control']['checks_failed']}/{base['negative_control']['checks']}",
         f"{F['neg_checks_failed']}/{F['neg_checks']}",
         "the new cases that depend on approval break too (R4: the trusted tool's REQUIRE_APPROVAL, a write through the read path; R9: one "
         "human decision); still 0 harness exceptions" if F["neg_checks_failed"] != base["negative_control"]["checks_failed"] else ""),
        ("negative control: harness exceptions", len(base["negative_control"]["harness_exceptions"]), F["neg_harness_exceptions"], ""),
        ("MCP", f"{h['mcp_transport']} · SDK {h['mcp_sdk']}", f"{F['env_mcp_transport']} · SDK {F['env_mcp_sdk']}", ""),
        ("checkpoints", h["checkpoint_store"], F["env_checkpoint_store"], ""),
        ("models", h["model_mode"], F["env_model_mode"], ""),
        ("tracing", f"{h['tracing']} {h['opentelemetry_sdk']}", f"{F['env_tracing']} {F['env_opentelemetry_sdk']}", ""),
        ("source SHA-256", h["source_sha256"], F.get("env_source_sha256"), "" if h["source_sha256"] == F.get("env_source_sha256") else note or "new source"),
    ]
    facts_rows = [(k, v["value"], F.get(k, "(not in the run)"), "" if F.get(k) == v["value"] else note or "re-measured")
                  for k, v in base["article_facts"].items()]
    changed = [r for r in rows + facts_rows if str(r[1]) != str(r[2])]
    doc = {"schema": "pae-proof/v1 proof-refresh-delta", "baseline": "docs/proof-standardization/original-publication-baseline.json",
           "baseline_run": h["run_id"], "published_run": run_id, "date": res["facts"]["run_date"]["value"], "note": note,
           "metrics": len(rows) + len(facts_rows), "changed": len(changed),
           "rows": [{"metric": m, "previous": a, "published": b, "changed": str(a) != str(b), "reason": r} for m, a, b, r in rows + facts_rows]}
    (OUT / "proof-refresh-delta.json").write_text(json.dumps(doc, indent=1, default=str) + "\n")
    md = ["# Proof refresh delta", "",
          f"The original publication baseline (`original-publication-baseline.json`, run `{h['run_id']}`) against the proof pack of run `{run_id}`. "
          f"{doc['metrics']} metrics; {doc['changed']} changed." + (f" {note}" if note else ""), "",
          "| Metric | Previous | New | Change | Reason |", "|---|---:|---:|---|---|"]
    md += [f"| {m} | {a} | {b} | {'changed' if str(a) != str(b) else 'same'} | {r} |" for m, a, b, r in rows]
    md += ["", "## Facts the articles print", "", "| Fact | Previous | New | Change | Reason |", "|---|---:|---:|---|---|"]
    md += [f"| `{m}` | {json.dumps(a)[:60]} | {json.dumps(b)[:60]} | {'changed' if str(a) != str(b) else 'same'} | {r} |" for m, a, b, r in facts_rows]
    (OUT / "proof-refresh-delta.md").write_text("\n".join(md) + "\n")
    print(f"delta -> docs/proof-standardization/proof-refresh-delta.{{json,md}}: {doc['metrics']} metrics, {doc['changed']} changed")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "delta":
        sys.exit(delta(sys.argv[2], " ".join(sys.argv[3:])))
    sys.exit(main())
