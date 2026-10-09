"""The negative control: the same proof, against a copy of the POC whose production policy no longer requires approval.

    uv run python negative_control.py --run RUN   -> evidence/runs/RUN/negative-control/raw/   (--out DIR: anywhere else)

The mutation (recorded as mutation.diff):
    config/policies/production.yaml   environments.production.agent_writes_need_approval: true -> false
                                      risk.tier_floor: {1: high, 2: medium} -> {1: medium, 2: low}
    config/tools/registry.yaml        release.execute_rollback risk: high -> medium
Together they make the checkout-api rollback a medium-risk production write that policy ALLOWs: it runs with no human
decision.  Nothing else changes: same agent, same tapes, same experiments, same checks.

The copy is made in a temporary directory; this POC is not modified.  The same run_proof.py runs there
(--run-id negative-control); its terminal output, results.json, summary.json and summary.md, the mutated run's whole raw
evidence (run/) and control.json (the verdict below) are written to the run's negative-control/raw/.

Exit 0 only if the control behaves as a negative control must: the proof exits 1, at least one check fails, and no
experiment stopped on an exception, so every failure is an explicit expected-vs-actual assertion.
"""

from __future__ import annotations

import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COPY = ("run_proof.py", "compare_runs.py", "negative_control.py", "pyproject.toml", "uv.lock", "src", "config", "scenarios", "tests")
RUN_ID = "negative-control"


def mutate(root: Path) -> list[tuple[str, str, str]]:
    """Apply the mutation in place; return (file, before, after) for each changed file."""
    edits = {
        "config/policies/production.yaml": [
            (r"(production:\s*\{allowed_operations: \[read, rollback\], agent_writes_need_approval: )true\}", r"\1false}"),
            (r"tier_floor: \{1: high, 2: medium\}", "tier_floor: {1: medium, 2: low}"),
        ],
        "config/tools/registry.yaml": [
            (r"(^  release\.execute_rollback:.*?risk: )high,", r"\1medium,"),
        ],
    }
    changed = []
    for rel, subs in edits.items():
        p = root / rel
        before = p.read_text()
        after = before
        for pat, rep in subs:
            after, n = re.subn(pat, rep, after, count=1, flags=re.M)
            if n != 1:
                raise SystemExit(f"mutation did not apply to {rel}: {pat}")
        p.write_text(after)
        changed.append((rel, before, after))
    return changed


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", help="the run this control belongs to: writes evidence/runs/<run>/negative-control/raw/")
    ap.add_argument("--out", type=Path, help="write here instead (a scratch control, never part of a run)")
    o = ap.parse_args()
    if not (o.run or o.out):
        raise SystemExit("name the run the control belongs to (--run) or a scratch directory (--out)")
    OUT = o.out.resolve() if o.out else ROOT / "evidence" / "runs" / o.run / "negative-control" / "raw"
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit(f"refusing to write into {OUT.name}/: it already holds a control (recorded evidence is never overwritten)")
    with tempfile.TemporaryDirectory(prefix="pap-negative-") as tmp:
        work = Path(tmp) / ROOT.name
        work.mkdir()
        for name in COPY:
            src = ROOT / name
            if src.is_dir():
                shutil.copytree(src, work / name, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store", ".pytest_cache"))
            else:
                shutil.copy2(src, work / name)
        changed = mutate(work)
        diff = "".join("".join(difflib.unified_diff(b.splitlines(True), a.splitlines(True), f"a/{rel}", f"b/{rel}")) for rel, b, a in changed)
        p = subprocess.run([sys.executable, "run_proof.py", "--run-id", RUN_ID], cwd=work, capture_output=True, text=True)
        run = work / "evidence" / "runs" / RUN_ID / "raw"
        OUT.mkdir(parents=True, exist_ok=True)
        shutil.copytree(run, OUT / "run")   # the mutated run's whole raw evidence, as it wrote it
        (OUT / "mutation.diff").write_text(diff)
        (OUT / "run-output.txt").write_text(p.stdout + p.stderr)
        for f in ("results.json", "summary.json", "summary.md"):
            shutil.copy2(run / f, OUT / f)
    res = json.loads((OUT / "results.json").read_text())
    failed = [c for e in res["experiments"] for c in e["checks"] if not c["passed"]] + [c for c in res["cross_checks"] if not c["passed"]]
    verdict = {
        "run_id": RUN_ID, "mutation": [rel for rel, _, _ in changed], "proof_exit_code": p.returncode,
        "experiments_failed": [e["id"] for e in res["experiments"] if e["status"] == "FAIL"],
        "checks_failed": len(failed), "checks": res["totals"]["checks"], "harness_exceptions": res["harness_exceptions"],
        "failed_by_experiment": {e["id"]: [c["id"] for c in e["checks"] if not c["passed"]] for e in res["experiments"] if e["status"] == "FAIL"},
        "source_sha256": res["environment"]["source_sha256"],
    }
    verdict["behaves_as_negative_control"] = p.returncode == 1 and bool(failed) and not res["harness_exceptions"]
    (OUT / "control.json").write_text(json.dumps(verdict, indent=1))
    print(json.dumps(verdict, indent=1))
    return 0 if verdict["behaves_as_negative_control"] else 1


if __name__ == "__main__":
    sys.exit(main())
