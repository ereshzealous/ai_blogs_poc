"""Re-run the published T4 proofs into a fresh copy of the POC and compare the result with the published run.

    python3 tools/verify_run.py              (make verify)
    python3 tools/verify_run.py --record     also writes evidence/runs/<run>/replay.json (the proof pack's replay record)

The published run directory is never written: the POC is copied to a temporary directory, the experiments run there with
the same run id, and the two run directories are compared file by file.  Exit status 1 on any difference.

One normalization, and only one: the operating system assigns process ids, so each scenario's raw runtime pids live in
scenarios/<id>/volatile.json, and that file is compared with its pid values masked (same labels, same number of
processes).  Every other file, transcripts included (they carry normalized labels such as rt-a/pid-1), must match byte
for byte.
"""

import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

POC = Path(__file__).resolve().parents[1] / "control_plane_poc"
RUN_ID = (POC / "runs" / "PUBLISHED").read_text().strip()


VOLATILE = "volatile.json"


def masked(path: Path) -> dict:
    """volatile.json with every raw pid replaced by a placeholder: the labels and the process count still have to match."""
    v = json.loads(path.read_text())
    v["runtime_pids"] = {label: "<pid>" for label in v["runtime_pids"]}
    return v


def same(a: Path, b: Path) -> bool:
    if a.name == VOLATILE:
        return masked(a) == masked(b)
    return filecmp.cmp(a, b, shallow=False)


def diff(a: Path, b: Path, rel: str = "") -> list[str]:
    c = filecmp.dircmp(a, b)
    out = [f"only in published: {rel}{n}" for n in c.left_only] + [f"only in rerun: {rel}{n}" for n in c.right_only]
    out += [f"differs: {rel}{n}" for n in c.common_files if not same(a / n, b / n)]
    for d in c.common_dirs:
        out += diff(a / d, b / d, f"{rel}{d}/")
    return out


def main() -> None:
    record = "--record" in sys.argv[1:]
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "poc"
        shutil.copytree(POC, copy, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "runs"))
        (copy / "runs").mkdir()
        subprocess.run(["uv", "run", "--quiet", "--project", str(copy), "acp", "experiments", "--run-id", RUN_ID], cwd=copy, check=True, capture_output=True)
        problems = diff(POC / "runs" / RUN_ID, copy / "runs" / RUN_ID)
    files = [f for f in (POC / "runs" / RUN_ID).rglob("*") if f.is_file() and "__pycache__" not in f.parts]
    vol = sum(1 for f in files if f.name == VOLATILE)
    if record:
        out = POC.parent / "evidence" / "runs" / RUN_ID / "replay.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "schema": "pae-proof/v1",
            "run_id": RUN_ID,
            "replay_level": "EXACT",
            "method": "every proof re-executed from source into a scratch copy of the POC with the same run id (tools/verify_run.py)",
            "normalization": f"{VOLATILE} only: raw process ids masked; labels and process counts must match",
            "files": len(files),
            "classes": {
                "DETERMINISTIC_EQUIVALENT": len(files) - vol - len(problems),
                "NONDETERMINISTIC": vol,
                "MODEL_OUTPUT_VARIATION": 0,
                "METHODOLOGY_CHANGE": 0,
                "REGRESSION": len(problems),
            },
            "differences": problems,
            "equivalent": not problems,
            "fresh_model_calls": 0,
        }
        out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print(
        f"verified: rerun of {RUN_ID} matches the published run: {len(files) - vol} files byte-identical, "
        f"{vol} {VOLATILE} files equal with raw process ids masked (the only normalization)"
    )


if __name__ == "__main__":
    main()
