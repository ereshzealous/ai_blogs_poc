"""The standardized proof pack of a run (Proof Contract §5) and the only way the published run changes (promote).

    uv run --project ops_poc python tools/proof_pack.py build <run> [--write]      (make pack)
    uv run --project ops_poc python tools/proof_pack.py promote <run> --reason "..."

build writes evidence/runs/<run>/{manifest.json, results.json, checks.jsonl, summary.json, summary.md,
negative-control/results.json, SHA256SUMS} and results/claim-evidence.json; without --write it recomputes the pack and
compares it byte for byte with the committed one. The raw evidence stays where the run wrote it (ops_poc/runs/<run>/).
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "ops_poc"
sys.path.insert(0, str(ROOT / "vendor" / "kit5"))
sys.path.insert(0, str(ROOT / "tools"))
from evidence_kit import proof  # noqa: E402  (5.2.0, vendor/kit5)
from proof_facts import collect  # noqa: E402

EVIDENCE = ROOT / "evidence"


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
    ctrl = [c for c in checks if c["experiment"] == "OPS-NC" and c["kind"] == "control"]
    done = bool(facts.value("nc.harness_completed"))
    return {"schema": proof.SCHEMA, "experiment": "OPS-NC", "scenarios": {"governed": "E1 controlled (bounded admission)", "mutated": "E1 controlled with the admission bound removed"},
            "safeguard_removed": "admission: the work-in-system bound (slots + queue bound) and the capacity error",
            "invariant": "work in system <= slots + queue bound (OPS-E1-C01)",
            "expected": "work in system grows past the bound under the same surge",
            "governed": {"max_work_in_system": facts.value("e1.controlled.max_work_in_system")},
            "mutated": {"max_work_in_system": facts.value("nc.max_work_in_system"), "goodput_pct": facts.value("nc.goodput_pct")},
            "checks": {c["id"]: c["status"] for c in ctrl},
            "observed": "; ".join(f"{c['description']} → {c['actual_value']}" for c in ctrl),
            "harness_completed": done, "test_assertions": "every attempt of the mutated arm reached a recorded result" if done else "incomplete",
            "result": "EXPECTED_FAILURE" if done and ctrl and all(c["status"] == "EXPECTED_FAILURE" for c in ctrl) else "FAIL"}


def claim_evidence(claims: list[dict], experiments: list[dict], checks: list[dict]) -> dict:
    """results/claim-evidence.json: claim -> scenario -> mechanism -> evidence -> result, generated, never typed."""
    X = {x["id"]: x for x in experiments}
    C = {c["id"]: c for c in checks}
    out = []
    for cl in claims:
        xs = [X[x] for x in cl.get("experiments", [])]
        out.append({"claim": cl["id"], "class": cl.get("class"), "statement": cl["statement"],
                    "scenario": [{"id": x["id"], "title": x["title"], "setup": x.get("setup")} for x in xs],
                    "mechanism": [x.get("variable") for x in xs],
                    "evidence": [{"check": c, "description": C[c]["description"], "kind": C[c]["kind"], "fact": C[c]["fact"],
                                  "expected": C[c]["expected"], "observed": C[c]["actual_value"], "status": C[c]["status"],
                                  "finding": C[c]["finding"], "files": sorted({e["path"] for e in C[c]["evidence"]})}
                                 for c in cl.get("checks", []) + cl.get("bound_checks", [])],
                    "result": cl.get("class"), "rests_on": cl.get("rests_on", [])})
    return {"schema": "o1o2-claim-evidence/v1", "claims": out}


def pack(run_id: str) -> tuple[dict[str, str], list[str]]:
    facts, data = collect(run_id)
    experiments, checks = proof.evaluate(load("experiments.toml"), facts)
    claims, problems = proof.trace(load("claims.toml"), experiments, checks)
    m, rm = load("manifest.toml"), data["manifest"]
    prof = profile(m, facts)
    manifest = {
        "schema": proof.SCHEMA, "series": m["article"]["series"], "article_id": m["article"]["id"], "poc": m["article"]["poc"],
        "run_id": run_id, "scenario": m["article"]["scenario"],
        "source_commit": "unknown (not a git repository); source_sha256 lists every POC source file's hash",
        "source_sha256": rm["source_sha256"], "frozen_sha256": rm["frozen_sha256"], "runtime_mode": m["run"]["runtime_mode"],
        "started_at": "unknown (not recorded: a deterministic run records simulated time; wall times live in volatile/)",
        "completed_at": "unknown (not recorded)",
        "environment": {"os": rm.get("platform", "unknown"), "arch": rm.get("platform", "unknown").split(" ")[-1], "python": rm["python"],
                        "model_runtime": "none: scripted agents", "model": "none", "model_version": {}, "temperature": "n/a",
                        "seed": "4917 (every scenario), 1101 (E4 calibration sample)"},
        "benchmark": {"modes": [{"key": "naive", "name": "the uncontrolled platform"}, {"key": "controlled", "name": "the control under test"}],
                      "scenarios": len(rm["scenarios"]), "arms": rm["arms"], "units": rm["units"]},
        "execution_profile": prof, "entrypoints": m["entrypoints"],
        "replay": {"level": m["run"]["replay_level"], "contract": m["run"]["replay_contract"], "record": f"evidence/runs/{run_id}/replay.json"},
        "integrity": {"sha256sums": f"evidence/runs/{run_id}/SHA256SUMS", "raw": f"ops_poc/runs/{run_id}"},
        "provenance": {"manifest_origin": f"built by tools/proof_pack.py from ops_poc/runs/{run_id}/manifest.json (recorded) and proof/manifest.toml (frozen words)",
                       "fields": {"python": "recorded", "source_sha256": "recorded", "frozen_sha256": "recorded", "benchmark": "recorded",
                                  "execution_profile": "frozen", "results": "aggregated from the raw run files (agentops.run.aggregate) and recomputed in tools/proof_facts.py",
                                  "started_at": "unknown", "source_commit": "unknown"}},
        "claim_problems": problems}
    nc = negative_control(facts, checks)
    res = proof.results(run_id, manifest, experiments, checks, facts, claims=claims, profile=prof,
                        paths={"raw": f"ops_poc/runs/{run_id}", "replay": f"evidence/runs/{run_id}/replay.json",
                               "negative_control": f"evidence/runs/{run_id}/negative-control/results.json", "claim_evidence": "results/claim-evidence.json"})
    summ, summ_md = proof.summary(res, f"O1 + O2 · Operating AI Agents at Scale · proof of run {run_id}")
    files = {"manifest.json": dump(manifest), "results.json": dump(res), "checks.jsonl": proof.checks_jsonl(checks),
             "summary.json": dump(summ), "summary.md": summ_md, "negative-control/results.json": dump(nc)}
    files["../../../results/claim-evidence.json"] = dump(claim_evidence(claims, experiments, checks))
    return files, problems


def raw_files(run_id: str) -> list[Path]:
    d = POC / "runs" / run_id
    return [p for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts and "volatile" not in p.parts]


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
        listed = [out / k for k in files if not k.startswith("../")] + [out / "replay.json"]
        (out / "SHA256SUMS").write_text(proof.sha256sums([p for p in listed if p.exists()] + raw, ROOT))
        print(f"wrote evidence/runs/{run_id}/ ({len(files)} files; SHA256SUMS over {len(listed) + len(raw)} files, the raw run included)")
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
    pub, history = EVIDENCE / "published.json", []
    if pub.exists():  # a re-promote keeps every earlier promote, never erases it
        prev = json.loads(pub.read_text())
        history = prev.get("history", []) + [{k: prev[k] for k in ("run_id", "promoted_at", "results_sha256", "reason")}]
    doc = {"schema": proof.SCHEMA, "article": "O1", "run_id": run_id, "reason": reason,
           "promoted_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "manifest": f"evidence/runs/{run_id}/manifest.json", "results": f"evidence/runs/{run_id}/results.json",
           "results_sha256": proof.sha256_file(out / "results.json"), "sha256sums": f"evidence/runs/{run_id}/SHA256SUMS",
           "replay": f"evidence/runs/{run_id}/replay.json", "negative_control": f"evidence/runs/{run_id}/negative-control/results.json",
           "verification": "evidence/verification/verification.json", "claim_evidence": "results/claim-evidence.json", "history": history}
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
