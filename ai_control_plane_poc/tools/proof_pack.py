"""The standardized proof pack of a run (Proof Contract §5) and the only way the published run changes (§5 promote).

    uv run --project control_plane_poc python tools/proof_pack.py build <run> [--write]   (make pack)
    uv run --project control_plane_poc python tools/proof_pack.py promote <run> --reason "..."

build writes evidence/runs/<run>/{manifest.json, results.json, checks.jsonl, summary.json, summary.md,
negative-control/results.json, SHA256SUMS}. Without --write it recomputes the pack and compares it byte for byte with
the committed one. The raw evidence stays where the run wrote it (control_plane_poc/runs/<run>/) and is never rewritten;
SHA256SUMS covers it and the pack. promote refuses unless the run has its pack, an equivalent replay record and a
negative control that broke as intended; it keeps the previous published run in the history.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "control_plane_poc"
sys.path.insert(0, str(ROOT / "vendor" / "kit5"))
sys.path.insert(0, str(ROOT / "tools"))
from evidence_kit import proof  # noqa: E402  (5.2.0, vendor/kit5)
from ledger import rows as ledger_rows  # noqa: E402
from proof_facts import collect  # noqa: E402

EVIDENCE = ROOT / "evidence"
PACK = ("manifest.json", "results.json", "checks.jsonl", "ledger.jsonl", "summary.json", "summary.md", "negative-control/results.json")


def load(name: str) -> dict:
    return tomllib.loads((ROOT / "proof" / name).read_text())


def dump(obj) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True, default=str) + "\n"


def profile(m: dict, facts) -> dict:
    """The execution profile of proof/manifest.toml with its {{facts}} filled in from the run."""
    return {
        "classes": [
            {"class": r["class"], "meaning": r.get("meaning"), "items": [{k: facts.resolve(v) if k == "text" else v for k, v in i.items()} for i in r["items"]]}
            for r in m.get("reality", [])
        ],
        "groups": [{"group": g["group"], "rows": [[facts.resolve(c) if isinstance(c, str) else c for c in row] for row in g["rows"]]} for g in m.get("profile", [])],
    }


def negative_control(facts, checks: list[dict]) -> dict:
    """P11: the safeguard (the control plane) removed; the invariant it protects must break cleanly, not crash."""
    ctrl = [c for c in checks if c["experiment"] == "T4-R11" and c["kind"] == "control"]
    done = facts.value("p11.embedded.assertions_passed") == facts.value("p11.embedded.assertions_total")
    return {
        "schema": proof.SCHEMA,
        "experiment": "T4-R11",
        "scenarios": {"governed": "P11-C-control-plane", "mutated": "P11-E-embedded"},
        "safeguard_removed": "the control plane: each agent embeds its own governance (allowed tools, approval rule, model, credentials)",
        "invariant": "a governance change needs no agent edit and no redeploy, and applies at the running process's next decision",
        "expected": "the invariant breaks: edits and redeploys are needed, and the running process keeps the old rule until it is redeployed",
        "governed": {k: facts.value(f"p11.cp.{k}") for k in ("files_edited", "redeploys", "bundle_versions", "static_credential_literals")},
        "mutated": {
            k: facts.value(f"p11.embedded.{k}")
            for k in ("files_edited", "lines_changed", "redeploys", "restart_before_redeploy", "restart_after_redeploy", "static_credential_literals")
        },
        "checks": {c["id"]: c["status"] for c in ctrl},
        "observed": "property broken by design: " + "; ".join(f"{c['description'].removeprefix('Safeguard removed: ')} → {c['actual']}" for c in ctrl),
        "harness_completed": done,
        "test_assertions": f"{facts.value('p11.embedded.assertions_passed')}/{facts.value('p11.embedded.assertions_total')} passed",
        "result": "EXPECTED_FAILURE" if done and ctrl and all(c["status"] == "EXPECTED_FAILURE" for c in ctrl) else "FAIL",
    }


def pack(run_id: str) -> tuple[dict[str, str], list[str]]:
    facts, data = collect(run_id)
    experiments, checks = proof.evaluate(load("experiments.toml"), facts)
    claims, problems = proof.trace(load("claims.toml"), experiments, checks)
    m, rm = load("manifest.toml"), data["manifest"]
    prof = profile(m, facts)
    na = "unknown (not recorded: the run is deterministic and records logical ticks, not wall time)"
    manifest = {
        "schema": proof.SCHEMA,
        "series": m["article"]["series"],
        "article_id": m["article"]["id"],
        "poc": m["article"]["poc"],
        "run_id": run_id,
        "scenario": m["article"]["scenario"],
        "source_commit": "unknown (not a git repository); source_sha256 lists every POC source file's hash",
        "source_sha256": rm["source_sha256"],
        "config_sha256": rm["config_sha256"],
        "agents_code_sha256": rm["agents_code_sha256"],
        "runtime_mode": m["run"]["runtime_mode"],
        "started_at": na,
        "completed_at": na,
        "environment": {
            "os": "unknown (not recorded by the run)",
            "arch": "unknown (not recorded by the run)",
            "python": rm["python"],
            "model_runtime": "none: agents follow fixed plans; model endpoints are simulated",
            "model": "none",
            "model_version": "n/a",
            "temperature": "n/a",
            "seed": "n/a (deterministic: no randomness)",
        },
        "benchmark": {
            "modes": [{"key": "C", "name": "governed through the control plane"}, {"key": "E", "name": "governance embedded in each agent (negative control)"}],
            "experiments": len(data["roles"]),
            "scenarios": len(data["scenarios"]),
            "roles": {r["experiment"]: r["role"] for r in data["roles"]},
            "scenario_assertions": {"passed": facts.value("checks.passed"), "total": facts.value("checks.total")},
        },
        "execution_profile": prof,
        "entrypoints": m["entrypoints"],
        "replay": {"level": m["run"]["replay_level"], "contract": m["run"]["replay_contract"], "record": f"evidence/runs/{run_id}/replay.json"},
        "integrity": {"sha256sums": f"evidence/runs/{run_id}/SHA256SUMS", "raw": f"control_plane_poc/runs/{run_id}"},
        "provenance": {
            "manifest_origin": f"built by tools/proof_pack.py from control_plane_poc/runs/{run_id}/manifest.json (recorded by the run) and proof/manifest.toml (frozen words)",
            "fields": {
                "python": "recorded",
                "source_sha256": "recorded",
                "config_sha256": "recorded",
                "agents_code_sha256": "recorded",
                "benchmark": "recorded",
                "execution_profile": "frozen",
                "results": "reconstructed from the recorded facts and the raw state by tools/proof_facts.py",
                "started_at": "unknown",
                "source_commit": "unknown",
            },
        },
        "claim_problems": problems,
    }
    nc = negative_control(facts, checks)
    res = proof.results(
        run_id,
        manifest,
        experiments,
        checks,
        facts,
        claims=claims,
        tables={"roles": data["roles"]},
        profile=prof,
        paths={
            "raw": f"control_plane_poc/runs/{run_id}",
            "replay": f"evidence/runs/{run_id}/replay.json",
            "negative_control": f"evidence/runs/{run_id}/negative-control/results.json",
            "ledger": f"evidence/runs/{run_id}/ledger.jsonl",
            "lab": "results/lab-console.html",
        },
    )
    summ, summ_md = proof.summary(res, f"T4 · AI Control Plane · proof of run {run_id}")
    files = {
        "manifest.json": dump(manifest),
        "results.json": dump(res),
        "checks.jsonl": proof.checks_jsonl(checks),
        "ledger.jsonl": "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in ledger_rows(POC / "runs" / run_id)),
        "summary.json": dump(summ),
        "summary.md": summ_md,
        "negative-control/results.json": dump(nc),
    }
    return files, problems


def derived_facts(run_id: str, files: dict[str, str]) -> dict:
    """docs/derived-facts.json: the proof pack's counts and the recomputed raw-evidence facts, for the documents' {{facts}}."""
    facts, _ = collect(run_id)
    res = json.loads(files["results.json"])
    src = f"evidence/runs/{run_id}/results.json"
    c, fc = res["check_counts"], res["finding_counts"]
    out = {
        "proof.experiments": {"value": c["experiments"], "source": src + " → check_counts"},
        "proof.checks": {"value": c["checks"], "source": src + " → check_counts"},
        "proof.pass": {"value": c["pass"], "source": src + " → check_counts"},
        "proof.fail": {"value": c["fail"], "source": src + " → check_counts"},
        "proof.limitation": {"value": fc.get("LIMITATION OBSERVED", 0), "source": src + " → finding_counts"},
        "proof.expected_failure": {"value": c["expected_failure"], "source": src + " → check_counts"},
        "proof.claims": {"value": len(res["claims"]), "source": src + " → claims"},
    }
    for k in ("SUPPORTED", "QUALIFIED", "NEGATIVE CONTROL", "NOT SUPPORTED", "ARGUED", "NOT TESTED"):
        out[f"proof.claims.{k.lower().replace(' ', '_')}"] = {"value": sum(cl.get("class") == k for cl in res["claims"]), "source": src + " → claims[].class"}
    for k, f in facts.d.items():
        if k.startswith(("raw.", "replay.")):
            out[k] = {"value": f["value"], "source": f["source"]}
    return dict(sorted(out.items()))


def raw_files(run_id: str) -> list[Path]:
    return [p for p in (POC / "runs" / run_id).rglob("*") if p.is_file() and "__pycache__" not in p.parts]


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
        listing = proof.sha256sums([out / k for k in files] + [out / "replay.json"] + raw, ROOT)
        (out / "SHA256SUMS").write_text(listing)
        print(f"wrote evidence/runs/{run_id}/ ({len(files)} files; SHA256SUMS over {len(files) + 1 + len(raw)} files, the raw run included)")
        (ROOT / "docs" / "derived-facts.json").write_text(json.dumps(derived_facts(run_id, files), indent=1, ensure_ascii=False) + "\n")
        print("wrote docs/derived-facts.json (proof counts, raw-evidence and replay facts for the documents)")
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
    pub = EVIDENCE / "published.json"
    old = json.loads(pub.read_text()) if pub.exists() else None
    first = {
        "run_id": "2026-09-30-recorded",
        "reason": "first edition's run, before the proof pack: P2 did not yet record runtime process labels and request hashes, and P12 had no "
        "own-scope attempt; its raw evidence is kept unchanged in control_plane_poc/runs/2026-09-30-recorded/",
        "results_sha256": None,
    }
    history = [{"run_id": old["run_id"], "reason": old["reason"], "results_sha256": old["results_sha256"]}] + old["history"] if old else [first]
    if old and old["run_id"] == run_id:
        history = old["history"]
    doc = {
        "schema": proof.SCHEMA,
        "article": "T4",
        "run_id": run_id,
        "reason": reason,
        "promoted_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "manifest": f"evidence/runs/{run_id}/manifest.json",
        "results": f"evidence/runs/{run_id}/results.json",
        "results_sha256": proof.sha256_file(out / "results.json"),
        "sha256sums": f"evidence/runs/{run_id}/SHA256SUMS",
        "replay": f"evidence/runs/{run_id}/replay.json",
        "negative_control": f"evidence/runs/{run_id}/negative-control/results.json",
        "verification": "evidence/verification/verification.json",
        "lab": "results/lab-console.html",
        "history": history,
    }
    pub.write_text(json.dumps(doc, indent=1) + "\n")
    (POC / "runs" / "PUBLISHED").write_text(run_id + "\n")
    print(f"published run: {run_id} (control_plane_poc/runs/PUBLISHED and evidence/published.json)")


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
