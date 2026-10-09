"""The standardized proof pack of a run (Proof Contract §5) and the only way the published run changes (promote).

    uv run --project recovery_poc python tools/proof_pack.py build <run> [--write]      (make pack)
    uv run --project recovery_poc python tools/proof_pack.py promote <run> --reason "..."

build writes evidence/runs/<run>/{manifest.json, results.json, checks.jsonl, summary.json, summary.md,
negative-control/results.json, SHA256SUMS}; without --write it recomputes the pack and compares it byte for byte with the
committed one.  The raw evidence stays where the run wrote it (recovery_poc/runs/<run>/) and is never rewritten.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "recovery_poc"
sys.path.insert(0, str(ROOT / "vendor" / "kit5"))
sys.path.insert(0, str(ROOT / "tools"))
from evidence_kit import proof  # noqa: E402  (5.2.0, vendor/kit5)
from proof_facts import collect  # noqa: E402

EVIDENCE = ROOT / "evidence"
PACK = ("manifest.json", "results.json", "checks.jsonl", "summary.json", "summary.md", "negative-control/results.json")


def load(name: str) -> dict:
    return tomllib.loads((ROOT / "proof" / name).read_text())


def dump(obj) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True, default=str) + "\n"


def profile(m: dict, facts) -> dict:
    return {"classes": [{"class": r["class"], "meaning": r.get("meaning"),
                         "items": [{k: facts.resolve(v) if k == "text" else v for k, v in i.items()} for i in r["items"]]} for r in m.get("reality", [])],
            "groups": [{"group": g["group"], "rows": [[facts.resolve(c) if isinstance(c, str) else c for c in row] for row in g["rows"]]}
                       for g in m.get("profile", [])]}


def negative_control(facts, checks: list[dict]) -> dict:
    ctrl = [c for c in checks if c["experiment"] == "REL-R7" and c["kind"] == "control"]
    done = facts.value("nc.harness_completed") == facts.value("scenarios")
    return {"schema": proof.SCHEMA, "experiment": "REL-R7", "scenarios": {"governed": "A2 (classified)", "mutated": "A2 with mutant X1"},
            "safeguard_removed": "execution certainty: a timeout (C6) and an in-flight crash (C7) are treated as NOT_EXECUTED, so the runtime retries instead of reconciling",
            "invariant": "no external effect is committed twice (I1, I2)",
            "expected": "the invariant breaks wherever no idempotency key protects the write",
            "governed": {"dup_scenarios": facts.value("A2.dup_scenarios")},
            "mutated": {"dup_scenarios": facts.value("nc.dup_scenarios"), "dup_list": facts.value("nc.dup_list"),
                        "masked_by_key_in_S09": facts.value("mut.X1.S09.credits")},
            "checks": {c["id"]: c["status"] for c in ctrl},
            "observed": "; ".join(f"{c['description']} → {c['actual_value']}" for c in ctrl),
            "harness_completed": done, "test_assertions": f"{facts.value('nc.harness_completed')}/{facts.value('scenarios')} runs completed",
            "result": "EXPECTED_FAILURE" if done and ctrl and all(c["status"] == "EXPECTED_FAILURE" for c in ctrl) else "FAIL"}


def pack(run_id: str) -> tuple[dict[str, str], list[str]]:
    facts, data = collect(run_id)
    experiments, checks = proof.evaluate(load("experiments.toml"), facts)
    claims, problems = proof.trace(load("claims.toml"), experiments, checks)
    m, rm = load("manifest.toml"), data["manifest"]
    prof = profile(m, facts)
    models = rm.get("models", {})
    manifest = {
        "schema": proof.SCHEMA, "series": m["article"]["series"], "article_id": m["article"]["id"], "poc": m["article"]["poc"],
        "run_id": run_id, "scenario": m["article"]["scenario"],
        "source_commit": "unknown (not a git repository); source_sha256 lists every POC source file's hash",
        "source_sha256": rm["source_sha256"], "frozen_sha256": rm["frozen_sha256"], "runtime_mode": m["run"]["runtime_mode"],
        "started_at": "unknown (not recorded: deterministic runs record logical sequence numbers, wall times live in volatile/)",
        "completed_at": "unknown (not recorded)",
        "environment": {"os": rm.get("platform", "unknown"), "arch": rm.get("platform", "unknown").split(" ")[-1], "python": rm["python"],
                        "model_runtime": "Ollama (local) for the model slice; scripted models for the fault scenarios",
                        "model": ", ".join(models) or "none", "model_version": {k: v.get("digest") for k, v in models.items()},
                        "temperature": 0.3, "seed": "1, 2, 3 (slice); none needed for the deterministic scenarios"},
        "benchmark": {"modes": [{"key": "A0", "name": "naive: catch -> retry"}, {"key": "A1", "name": "idempotent retry"},
                                {"key": "A2", "name": "classified: evidence -> certainty -> recovery matrix"}],
                      "scenarios": len(rm["scenarios"]), "arms": rm["arms"], "mutants": rm["mutants"], "slice_cases": 16, "slice_seeds": 3},
        "execution_profile": prof, "entrypoints": m["entrypoints"],
        "replay": {"level": m["run"]["replay_level"], "contract": m["run"]["replay_contract"], "record": f"evidence/runs/{run_id}/replay.json"},
        "integrity": {"sha256sums": f"evidence/runs/{run_id}/SHA256SUMS", "raw": f"recovery_poc/runs/{run_id}"},
        "provenance": {"manifest_origin": f"built by tools/proof_pack.py from recovery_poc/runs/{run_id}/manifest.json (recorded) and proof/manifest.toml (frozen words)",
                       "fields": {"python": "recorded", "source_sha256": "recorded", "frozen_sha256": "recorded", "benchmark": "recorded",
                                  "execution_profile": "frozen", "results": "reconstructed from the recorded facts and the raw ledgers by tools/proof_facts.py",
                                  "started_at": "unknown", "source_commit": "unknown"}},
        "claim_problems": problems}
    nc = negative_control(facts, checks)
    res = proof.results(run_id, manifest, experiments, checks, facts, claims=claims, profile=prof,
                        paths={"raw": f"recovery_poc/runs/{run_id}", "replay": f"evidence/runs/{run_id}/replay.json",
                               "negative_control": f"evidence/runs/{run_id}/negative-control/results.json", "lab": "results/lab-console.html"})
    summ, summ_md = proof.summary(res, f"R1 + R2 · Evals, Observability & Reliability · proof of run {run_id}")
    files = {"manifest.json": dump(manifest), "results.json": dump(res), "checks.jsonl": proof.checks_jsonl(checks),
             "summary.json": dump(summ), "summary.md": summ_md, "negative-control/results.json": dump(nc)}
    return files, problems


LIVE = "2026-10-07-live"   # the real-model end-to-end run: its raw files and replay record are covered by the same SHA256SUMS


def raw_files(run_id: str) -> list[Path]:
    dirs = [POC / "runs" / run_id] + ([POC / "runs" / LIVE] if (POC / "runs" / LIVE).exists() else [])
    extra = [EVIDENCE / "runs" / LIVE / "replay.json"] if (EVIDENCE / "runs" / LIVE / "replay.json").exists() else []
    return [p for d in dirs for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts] + extra


def build(run_id: str, write: bool) -> bool:
    files, problems = pack(run_id)
    if problems:
        print("claim problems:\n  " + "\n  ".join(problems))
    out = EVIDENCE / "runs" / run_id
    if write:
        for k, v in files.items():
            (out / k).parent.mkdir(parents=True, exist_ok=True)
            (out / k).write_text(v)
        raw = raw_files(run_id)
        (out / "SHA256SUMS").write_text(proof.sha256sums([out / k for k in files] + [out / "replay.json"] + raw, ROOT))
        print(f"wrote evidence/runs/{run_id}/ ({len(files)} files; SHA256SUMS over {len(files) + 1 + len(raw)} files, the raw run included)")
        return not problems
    diffs = [k for k, v in files.items() if not (out / k).exists() or (out / k).read_text() != v]
    if diffs:
        print("recomputed pack differs from the committed one:", ", ".join(diffs))
        return False
    print(f"recomputed pack is byte-identical to evidence/runs/{run_id}/ ({len(files)} files)")
    return not problems


def promote(run_id: str, reason: str) -> None:
    out = EVIDENCE / "runs" / run_id
    problems = []
    if not (out / "results.json").exists():
        problems.append("no proof pack (build --write first)")
    rp = out / "replay.json"
    if not rp.exists() or not json.loads(rp.read_text())["equivalent"]:
        problems.append("no equivalent replay record (python3 tools/verify_run.py --record)")
    nc = out / "negative-control" / "results.json"
    if not nc.exists() or json.loads(nc.read_text())["result"] != "EXPECTED_FAILURE":
        problems.append("negative control missing or did not break as intended")
    if problems:
        raise SystemExit("refusing to promote: " + "; ".join(problems))
    doc = {"schema": proof.SCHEMA, "article": "R1", "run_id": run_id, "reason": reason,
           "promoted_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "manifest": f"evidence/runs/{run_id}/manifest.json", "results": f"evidence/runs/{run_id}/results.json",
           "results_sha256": proof.sha256_file(out / "results.json"), "sha256sums": f"evidence/runs/{run_id}/SHA256SUMS",
           "replay": f"evidence/runs/{run_id}/replay.json", "negative_control": f"evidence/runs/{run_id}/negative-control/results.json",
           "verification": "evidence/verification/verification.json", "lab": "results/lab-console.html", "history": []}
    (EVIDENCE / "published.json").write_text(json.dumps(doc, indent=1) + "\n")
    (POC / "runs" / "PUBLISHED").write_text(run_id + "\n")
    print(f"published run: {run_id}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "promote"])
    ap.add_argument("run")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--reason")
    o = ap.parse_args()
    if o.cmd == "build":
        sys.exit(0 if build(o.run, o.write) else 1)
    if not o.reason:
        raise SystemExit("promote needs --reason")
    promote(o.run, o.reason)


if __name__ == "__main__":
    main()
