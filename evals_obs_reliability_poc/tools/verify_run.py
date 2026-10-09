"""Re-run the published run into a fresh copy of the POC and compare it with the published files (Proof Contract §6).

    python3 tools/verify_run.py              (make replay)
    python3 tools/verify_run.py --record     also writes evidence/runs/<run>/replay.json

The published run directory is never written.  The POC is copied to a temporary directory (without runs/), every
deterministic experiment is re-executed there with the same run id (scenarios, mutants, the model change), the
real-model slice is re-scored from the published tape (no model is called), facts are aggregated, and the two run
directories are compared file by file.

Excluded from the byte comparison, and only these:
  */volatile/*            wall-clock durations and process ids
  model-slice/tape.jsonl, models.json, volatile.json   the recorded model traffic itself (copied, not regenerated)
  manifest.json           records the live flag and model digests of the recording session
  RUN-NOTES.md            the human notes written after the recording
"""

import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "recovery_poc"
RUN_ID = (POC / "runs" / "PUBLISHED").read_text().strip()
SKIP_NAMES = {"manifest.json", "RUN-NOTES.md"}
SLICE_INPUTS = {"tape.jsonl", "models.json", "volatile.json"}


def files(d: Path) -> dict[str, Path]:
    out = {}
    for p in d.rglob("*"):
        if not p.is_file() or "volatile" in p.parts or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(d).as_posix()
        if rel in SKIP_NAMES or (rel.startswith("model-slice/") and p.name in SLICE_INPUTS):
            continue
        out[rel] = p
    return out


def main() -> None:
    record = "--record" in sys.argv[1:]
    pub = POC / "runs" / RUN_ID
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "poc"
        shutil.copytree(POC, copy, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "runs", "var"))
        (copy / "runs").mkdir()
        (copy / "runs" / "PUBLISHED").write_text(RUN_ID + "\n")
        uv = ["uv", "run", "--quiet", "--project", str(copy), "python", "-m", "recovery.run"]
        subprocess.run(uv + ["record", "--run-id", RUN_ID], cwd=copy, check=True, capture_output=True)
        ms = copy / "runs" / RUN_ID / "model-slice"
        ms.mkdir(parents=True, exist_ok=True)
        for name in SLICE_INPUTS:
            shutil.copy(pub / "model-slice" / name, ms / name)
        subprocess.run(uv + ["score-slice", "--run-id", RUN_ID], cwd=copy, check=True, capture_output=True)
        a, b = files(pub), files(copy / "runs" / RUN_ID)
        problems = [f"only in published: {k}" for k in sorted(set(a) - set(b))] + [f"only in rerun: {k}" for k in sorted(set(b) - set(a))]
        problems += [f"differs: {k}" for k in sorted(set(a) & set(b)) if not filecmp.cmp(a[k], b[k], shallow=False)]
    total = sum(1 for p in pub.rglob("*") if p.is_file())
    vol = sum(1 for p in pub.rglob("*") if p.is_file() and "volatile" in p.parts)
    if record:
        out = ROOT / "evidence" / "runs" / RUN_ID / "replay.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        doc = {"schema": "pae-proof/v1", "run_id": RUN_ID, "replay_level": "EXACT",
               "method": "every deterministic experiment re-executed from source into a scratch copy of the POC with the same run id; "
                         "the real-model slice re-scored from the published tape (tools/verify_run.py)",
               "normalization": "none: volatile/ files (wall times, pids), the recorded model tape and the recording manifest are excluded, not normalized",
               "files": len(a), "files_in_run": total, "volatile_excluded": vol,
               "classes": {"DETERMINISTIC_EQUIVALENT": len(a) - len(problems), "NONDETERMINISTIC": vol, "MODEL_OUTPUT_VARIATION": 0,
                           "METHODOLOGY_CHANGE": 0, "REGRESSION": len(problems)},
               "differences": problems, "equivalent": not problems, "fresh_model_calls": 0}
        out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    if problems:
        print("\n".join(problems[:40]))
        sys.exit(1)
    print(f"verified: the rerun of {RUN_ID} matches the published run: {len(a)} files byte-identical "
          f"({vol} volatile files and the recorded model tape excluded); 0 model calls")


if __name__ == "__main__":
    main()
