"""The standardized proof pack of a run (Proof Contract §5), and the only way the published run changes (promote).

    uv run python tools/proof_pack.py build <run> [--write]       (uv run pap proof [--run R] [--write])
    uv run python tools/proof_pack.py promote <run> --reason "..." --note "..."

build writes evidence/runs/<run>/{manifest.json, results.json, checks.jsonl, summary.json, summary.md,
negative-control/results.json, proof/*.toml (the definitions it was built with), SHA256SUMS}. Without --write it
recomputes the pack and compares it byte for byte with the shipped one. The raw evidence (raw/, replay/raw/,
negative-control/raw/) stays as the run wrote it; SHA256SUMS covers it and the pack.

promote refuses unless the run's pack is current, its replay is equivalent at the declared level, its negative control
broke as intended and completed, the run verifies, and the publication baseline and a proof-refresh delta naming the run
exist. The previous published run moves to the history; last run never wins.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor"))
sys.path.insert(0, str(ROOT / "tools"))
from evidence_kit import proof  # noqa: E402  (5.2.0, vendor/)
from proof_facts import RUNS, collect, read  # noqa: E402

PROOF = ROOT / "proof"
PUB = ROOT / "evidence" / "published.json"
DOCS = ROOT.parent / "docs" / "proof-standardization"   # the article repository's publication baseline and refresh deltas
KIT = (ROOT / "vendor" / "evidence_kit" / "VERSION").read_text().strip()
DEFS = ("manifest.toml", "experiments.toml", "claims.toml")


def dump(obj) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True, default=str) + "\n"


def definitions(run_id: str, source: str = "current") -> dict[str, str]:
    """The proof definitions a pack is built with: proof/ (current), or the copy shipped with the run (shipped)."""
    base = PROOF if source == "current" else RUNS / run_id / "proof"
    return {n: (base / n).read_text() for n in DEFS}


def profile(m: dict, facts) -> dict:
    return {
        "classes": [{"class": r["class"], "meaning": r.get("meaning"),
                     "items": [{k: facts.resolve(v) if k == "text" else v for k, v in i.items()} for i in r["items"]]} for r in m["reality"]],
        "groups": [{"group": g["group"], "rows": [[facts.resolve(c) if isinstance(c, str) else c for c in row] for row in g["rows"]]}
                   for g in m.get("profile", [])],
    }


def negative_control(run_id: str, facts, checks: list[dict]) -> dict:
    ctrl = [c for c in checks if c["experiment"] == "P1-R14"]
    v = lambda k: facts.value(k) if k in facts else None  # noqa: E731
    done = v("neg_harness_exceptions") == 0 and v("neg_checks") == v("total_checks")
    return {
        "schema": proof.SCHEMA, "run_id": run_id, "experiment": "P1-R14",
        "safeguard_removed": "the approval requirement for production agent writes: agent_writes_need_approval false, and the tier-1 risk floor and "
                             "the rollback's registry risk lowered from high to medium, so policy returns ALLOW (negative-control/raw/mutation.diff)",
        "invariant": "a high-risk production write executes only after a human approves the exact invocation",
        "expected": "the invariant breaks: policy returns ALLOW, the rollback executes before any human decision, the checks that depend on approval "
                    "fail as assertions, the proof exits non-zero, and every experiment still completes",
        "governed": {"policy_decision": v("obs.R1.policy").split(" · ")[0] if v("obs.R1.policy") else None, "parked": v("obs.R1.parked"),
                     "checks": v("total_checks"), "checks_failed": v("total_failed"), "harness_exceptions": v("harness.exceptions")},
        "mutated": {"policy_decision": v("negctl.policy_decision"), "parked": v("negctl.parked"), "unapproved_rollbacks": v("negctl.unapproved_rollbacks"),
                    "checks": v("neg_checks"), "checks_failed": v("neg_checks_failed"), "experiments_failed": v("neg_failed_experiments"),
                    "harness_exceptions": v("neg_harness_exceptions"), "proof_exit_code": v("negctl.proof_exit_code")},
        "checks": {c["id"]: c["status"] for c in ctrl},
        "observed": "; ".join(f"{c['description'].removeprefix('Control: ')} → {c['actual']}" for c in ctrl if c["kind"] == "control"),
        "harness_completed": bool(done),
        "raw": f"evidence/runs/{run_id}/negative-control/raw/",
        "result": "EXPECTED_FAILURE" if done and any(c["kind"] == "control" for c in ctrl)
                  and all(c["status"] == "EXPECTED_FAILURE" for c in ctrl if c["kind"] == "control")
                  and all(c["status"] == "PASS" for c in ctrl if c["kind"] != "control") else "FAIL",
    }


def pack(run_id: str, source: str = "current") -> tuple[dict[str, str], list[str]]:
    defs = definitions(run_id, source)
    m, xspec, cspec = (tomllib.loads(defs[n]) for n in DEFS)
    facts, data = collect(run_id)
    problems = [f"experiments.toml: {p}" for p in proof.validate_schema(xspec, proof.schema("experiments"))]
    problems += [f"claims.toml: {p}" for p in proof.validate_schema(cspec, proof.schema("claims"))]
    experiments, checks = proof.evaluate(xspec, facts)
    claims, tp = proof.trace(cspec, experiments, checks)
    problems += tp
    st = [c["status"] for c in checks]
    src = f"evidence/runs/{run_id}/results.json"
    facts.add("proof.experiments", len(experiments), source=src + " → check_counts.experiments")
    facts.add("proof.checks", len(checks), source=src + " → check_counts.checks")
    for s in proof.STATUSES:
        facts.add(f"proof.{s.lower()}", st.count(s), source=src + f" → check_counts.{s.lower()}")
    facts.add("proof.claims", len(claims), source=src + " → claims")
    facts.add("proof.kit", f"evidence-kit {KIT}", source="vendor/evidence_kit/VERSION")
    facts.add("proof.schema", proof.SCHEMA, source="vendor/evidence_kit/proof.py")
    facts.add("proof.replay_level", m["run"]["replay_level"], source="proof/manifest.toml → run.replay_level")
    prof = profile(m, facts)
    res_raw, env = data["res"], data["res"]["environment"]
    os_, _, arch = env["platform"].partition(" ")
    manifest = {
        "schema": proof.SCHEMA, "contract": proof.CONTRACT, "series": m["article"]["series"], "article_id": m["article"]["id"],
        "learning": m["article"]["learning"], "poc": m["article"]["poc"], "poc_depth": m["article"]["poc_depth"], "run_id": run_id,
        "scenario": m["article"]["scenario"],
        "source_commit": "unknown: the POC is not a git repository; source_sha256 identifies the source tree that ran",
        "source_sha256": env.get("source_sha256", "unknown: not recorded (runs before the source digest was added)"),
        "source_files": env.get("source_files"),
        "agent_code_sha256": env["agent_code_sha256"],
        "runtime_mode": m["run"]["runtime_mode"], "started_at": res_raw["started_at"], "completed_at": res_raw["finished_at"],
        "environment": {"os": os_, "arch": arch, "python": env["python"],
                        "model_runtime": "none: recorded providers replay scripted tapes (RecordedModelA/B)",
                        "model": "recorded-model-a, recorded-model-b (fallback)", "model_version": "the tapes in scenarios/inc_4917/tapes/, covered by source_sha256",
                        "temperature": "n/a (recorded output)", "seed": "n/a (deterministic: no sampling)",
                        "mcp_sdk": env["mcp_sdk"], "opentelemetry_sdk": env["opentelemetry_sdk"], "mcp_transport": env["mcp_transport"],
                        "checkpoint_store": env["checkpoint_store"], "crash_injection": env["crash_injection"]},
        "benchmark": {"modes": [{"key": "governed", "name": "the governed platform"},
                                {"key": "control", "name": "the same scenario without one safeguard: in-experiment controls (R4, R8, R10, R12) and the negative control (R14)"}],
                      "experiments": len(experiments), "harness_experiments": res_raw["totals"]["experiments"],
                      "harness_assertions": {"checks": res_raw["totals"]["checks"], "passed": res_raw["totals"]["passed"]},
                      "unit_tests": res_raw["unit_tests"]},
        "execution_profile": prof, "entrypoints": m["entrypoints"],
        "replay": {"level": m["run"]["replay_level"], "contract": m["run"]["replay_contract"], "record": f"evidence/runs/{run_id}/replay.json"},
        "integrity": {"sha256sums": f"evidence/runs/{run_id}/SHA256SUMS", "raw": f"evidence/runs/{run_id}/raw/", "proof_kit": f"evidence-kit {KIT}",
                      "note": "a checksum list, not a signature: it verifies the files, not who wrote them"},
        "provenance": {"manifest_origin": "built by tools/proof_pack.py from raw/results.json (recorded by the run) and proof/manifest.toml (authored)",
                       "fields": {"started_at": "recorded", "completed_at": "recorded", "environment": "recorded (os and arch split from the recorded platform)",
                                  "source_sha256": "recorded" if "source_sha256" in env else "unknown", "agent_code_sha256": "recorded",
                                  "benchmark": "recorded", "execution_profile": "authored (proof/manifest.toml), numbers from the run's facts",
                                  "results": "derived by tools/proof_facts.py and evidence_kit.proof from the recorded files",
                                  "source_commit": "unknown"}},
    }
    nc = negative_control(run_id, facts, checks)
    res = proof.results(run_id, manifest, experiments, checks, facts, claims=claims, profile=prof,
                        tables={"harness": {e["id"]: {"title": e["title"], "passed": e["passed"], "total": e["total"], "status": e["status"]}
                                            for e in res_raw["experiments"]}},
                        paths={"raw": f"evidence/runs/{run_id}/raw/", "replay": f"evidence/runs/{run_id}/replay.json",
                               "negative_control": f"evidence/runs/{run_id}/negative-control/results.json",
                               "published": "evidence/published.json", "lab": "lab/index.html", "readme": "README.md",
                               "verification": "evidence/verification/verification.json", "contract": "vendor/evidence_kit/proof_contract/PROOF_STANDARD.md"})
    problems += [f"results: {p}" for p in proof.validate_schema(res, proof.schema("results"))]
    problems += [f"manifest: {p}" for p in proof.validate_schema(manifest, proof.schema("manifest"))]
    problems += [f"negative control: {p}" for p in proof.validate_schema(nc, proof.schema("negative-control"))]
    summ, summ_md = proof.summary(res, f"P1 · Production Agentic AI Platform · proof of run `{run_id}`")
    files = {"manifest.json": dump(manifest), "results.json": dump(res), "checks.jsonl": proof.checks_jsonl(checks),
             "summary.json": dump(summ), "summary.md": summ_md, "negative-control/results.json": dump(nc),
             **{f"proof/{n}": t for n, t in defs.items()}}
    return files, problems


def covered(run_id: str) -> list[Path]:
    run = RUNS / run_id
    return sorted(p for p in run.rglob("*") if p.is_file() and p.name != "SHA256SUMS" and "__pycache__" not in p.parts and p.name != ".DS_Store")


def build(run_id: str, write: bool, source: str = "current") -> bool:
    files, problems = pack(run_id, source)
    for p in problems:
        print("  problem:", p)
    out = RUNS / run_id
    if write:
        for k, v in files.items():
            (out / k).parent.mkdir(parents=True, exist_ok=True)
            (out / k).write_text(v)
        paths = covered(run_id)
        (out / "SHA256SUMS").write_text(proof.sha256sums(paths, ROOT))
        print(f"wrote evidence/runs/{run_id}/ ({len(files)} pack files; SHA256SUMS over {len(paths)} files: the pack, raw/, replay, negative control)")
        return not problems
    diffs = [k for k, v in files.items() if not (out / k).exists() or (out / k).read_text() != v]
    if diffs:
        print("recomputed pack differs from the shipped one:", ", ".join(diffs))
        return False
    print(f"recomputed pack is byte-identical to evidence/runs/{run_id}/ ({len(files)} files)")
    return not problems


def promote(run_id: str, reason: str, note: str | None) -> None:
    run = RUNS / run_id
    old = read(PUB) if PUB.exists() else None
    problems = []
    if not build(run_id, write=False, source="shipped"):
        problems.append("no current proof pack (pap proof --run <run> --write)")
    rp = run / "replay.json"
    man = read(run / "manifest.json") if (run / "manifest.json").exists() else {}
    if not rp.exists() or not read(rp)["equivalent"] or read(rp)["replay_level"] != man.get("replay", {}).get("level"):
        problems.append("no replay record equivalent at the declared level (pap replay --run <run>)")
    nc = run / "negative-control" / "results.json"
    if not nc.exists() or read(nc)["result"] != "EXPECTED_FAILURE" or not read(nc)["harness_completed"]:
        problems.append("negative control missing, crashed, or did not break as intended")
    if not (DOCS / "original-publication-baseline.json").exists():
        problems.append("no publication baseline (docs/proof-standardization/original-publication-baseline.json)")
    delta = DOCS / "proof-refresh-delta.md"
    if not delta.exists() or run_id not in delta.read_text():
        problems.append("no proof-refresh delta naming this run (docs/proof-standardization/proof-refresh-delta.md)")
    if old and old["run_id"] != run_id and not note:
        problems.append("--note is required when the published run changes (what changed, and why)")
    v = subprocess.run([sys.executable, str(ROOT / "tools" / "verify_evidence.py"), "--run", run_id, "--no-write"], capture_output=True, text=True)
    if v.returncode != 0:
        problems.append("the run does not verify:\n" + v.stdout[-1500:])
    if problems:
        raise SystemExit("refusing to promote: " + "; ".join(problems))
    first = {"run_id": "2026-09-30-proof", "results_sha256": None,
             "reason": "first published run, before the proof pack and before the harness repair (7 of its negative control's 8 failing experiments "
                       "stopped on exceptions); replaced by 2026-09-30-proof-2; raw evidence relocated unchanged to evidence/runs/2026-09-30-proof/raw/"}
    if old:
        history = old["history"] if old["run_id"] == run_id else [{k: old.get(k) for k in ("run_id", "reason", "results_sha256", "note")}] + old["history"]
    else:
        history = [first]
    doc = {"schema": proof.SCHEMA, "article": "P1", "run_id": run_id, "reason": reason, "note": note,
           "promoted_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "manifest": f"evidence/runs/{run_id}/manifest.json", "results": f"evidence/runs/{run_id}/results.json",
           "results_sha256": proof.sha256_file(run / "results.json"), "sha256sums": f"evidence/runs/{run_id}/SHA256SUMS",
           "replay": f"evidence/runs/{run_id}/replay.json", "negative_control": f"evidence/runs/{run_id}/negative-control/results.json",
           "verification": "evidence/verification/verification.json", "lab": "lab/index.html", "history": history}
    probs = proof.validate_schema(doc, proof.schema("published"))
    if probs:
        raise SystemExit("published.json would not validate: " + "; ".join(probs))
    PUB.write_text(json.dumps(doc, indent=1) + "\n")
    (RUNS / "PUBLISHED").write_text(run_id + "\n")
    print(f"published run: {run_id} (evidence/published.json; evidence/runs/PUBLISHED kept in step)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "promote"])
    ap.add_argument("run")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--shipped", action="store_true", help="build with the definitions shipped with the run instead of proof/")
    ap.add_argument("--reason")
    ap.add_argument("--note")
    o = ap.parse_args()
    if o.cmd == "build":
        sys.exit(0 if build(o.run, o.write, "shipped" if o.shipped else "current") else 1)
    if not o.reason:
        raise SystemExit("promote needs --reason")
    promote(o.run, o.reason, o.note)


if __name__ == "__main__":
    main()
