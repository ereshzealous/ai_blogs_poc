"""Verify one run directory: complete, frozen inputs unchanged, summary reproducible from the run's own files.

    uv run python scripts/verify_evidence.py runs/<id>      -> runs/<id>/verification.json (exit 1 on any failure)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

POC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC / "scripts"))
from record_run import FROZEN, sha_file, sha_paths  # noqa: E402

VOLATILE = ("wall", "_s", "started", "finished", "ts")


def main(run_dir: Path) -> int:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    m = json.loads((run_dir / "manifest.json").read_text()) if (run_dir / "manifest.json").exists() else {}
    check("manifest exists", bool(m))
    check("experiment plan hash matches the plan on disk", m.get("hashes", {}).get("experiment_plan") == sha_file(POC / FROZEN["experiment_plan"]))
    revised = m.get("revised_hashes", {})
    drift = [k for k, v in FROZEN.items() if k != "experiment_plan" and sha_paths(v) not in (m.get("hashes", {}).get(k), revised.get(k))]
    check("frozen inputs unchanged since the run (or changed only by a declared evidence revision)", not drift, ", ".join(drift))
    if m.get("evidence_revisions"):
        check("declared revisions still match their files", all(sha_file(POC / f) == h for r in m["evidence_revisions"] for f, h in r["files"].items()))
    s = json.loads((run_dir / "summary.json").read_text()) if (run_dir / "summary.json").exists() else {}
    check("summary.json exists", bool(s))
    integ = s.get("integrity", {})
    check("every preregistered scenario ran", integ.get("scenarios_expected") == integ.get("scenarios_present"), str(integ.get("missing")))
    check("no replay tape misses", integ.get("tape_misses", 1) == 0)
    check("tests: zero failures", s.get("tests", {}).get("failed", 1) == 0, f"{s.get('tests', {}).get('passed')}/{s.get('tests', {}).get('total')}")
    missing = [d.name for d in sorted((run_dir / "scenarios").iterdir()) if not all((d / f).exists() for f in ("score.json", "phases_harness.jsonl", "raw/executions.jsonl", "tape/model_calls.jsonl"))]
    check("every scenario has score, process log, world ledger and model-call ledger", not missing, ", ".join(missing))
    for f in ("model_calls", "tool_calls", "workflow_events", "policy_events", "checkpoints", "traces", "backend_executions"):
        p = run_dir / "raw" / f"{f}.jsonl"
        check(f"raw/{f}.jsonl present and non-empty", p.exists() and p.stat().st_size > 0)
    check("E6 probe results present", (run_dir / "experiments" / "E6_probes.json").exists())
    for c in ("E2_model_swap", "E3_tool_v2", "E9_dry_run"):
        for arch in ("monolith", "layered"):
            check(f"diff for {c}-{arch}", (run_dir / "diffs" / f"{c}-{arch}.diff").exists())
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / run_dir.name
        shutil.copytree(run_dir, tmp, ignore=shutil.ignore_patterns("worktrees", "tape", "platform", "monolith", "*.db*"))
        subprocess.run([sys.executable, str(POC / "scripts" / "build_summary.py"), str(tmp)], check=True, capture_output=True, cwd=POC)
        again = json.loads((tmp / "summary.json").read_text())
    check("summary.json rebuilds identically from the run's files", again == s)
    # Integrity is not enough: recompute the published numbers from the raw evidence as well (scripts/recompute.py).
    from recompute import run_checks  # noqa: PLC0415

    recomputed = run_checks(run_dir)
    checks += recomputed
    ok = all(c["ok"] for c in checks if c["ok"] is not None)
    (run_dir / "verification.json").write_text(json.dumps({
        "run_id": run_dir.name, "ok": ok,
        "passed": sum(1 for c in checks if c["ok"] is True),
        "failed": sum(1 for c in checks if c["ok"] is False),
        "not_applicable": sum(1 for c in checks if c["ok"] is None),
        "recomputed": sum(1 for c in checks if c.get("recomputed")),
        "total": len(checks), "checks": checks}, indent=1))
    for c in checks:
        mark = "--   " if c["ok"] is None else ("PASS " if c["ok"] else "FAIL ")
        print(mark + c["check"] + (f"  [{c['detail']}]" if c["detail"] and not c["ok"] else ""))
    # count passes only: a check that does not apply is None, and summing None raises
    print(f"verification: {sum(1 for c in checks if c['ok'] is True)}/{len(checks)}"
          + (f", {sum(1 for c in checks if c['ok'] is None)} not applicable" if any(c["ok"] is None for c in checks) else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]).resolve()))
