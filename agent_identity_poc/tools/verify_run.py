"""Re-run the published T1 experiments into a fresh copy of the POC and compare the result with the published run.

    python3 tools/verify_run.py      (make verify)

The published run directory is never written: the POC is copied to a temporary directory, the experiments run there with
the same run id, and the two run directories are compared file by file.  Exit status 1 on any difference.  recorded.json
(when the run was recorded, under which freeze) is the one file that is expected to differ.
"""

import filecmp
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

POC = Path(__file__).resolve().parents[1] / "agent_identity_poc"
RUN_ID = (POC / "runs" / "PUBLISHED").read_text().strip()


def diff(a: Path, b: Path) -> list[str]:
    c = filecmp.dircmp(a, b)
    out = [f"only in published: {n}" for n in c.left_only] + [f"only in rerun: {n}" for n in c.right_only]
    out += [f"differs: {n}" for n in c.common_files if n != "recorded.json" and not filecmp.cmp(a / n, b / n, shallow=False)]
    for d in c.common_dirs:
        out += diff(a / d, b / d)
    return out


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "poc"
        shutil.copytree(POC, copy, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "runs"))
        (copy / "runs").mkdir()
        subprocess.run(["uv", "run", "--quiet", "--project", str(copy), "aid", "experiments", "--run-id", RUN_ID],
                       cwd=copy, check=True, capture_output=True)
        problems = diff(POC / "runs" / RUN_ID, copy / "runs" / RUN_ID)
    n = len(list((POC / "runs" / RUN_ID).iterdir()))
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print(f"verified: rerun of {RUN_ID} is byte-identical to the published run ({n} files)")


if __name__ == "__main__":
    main()
