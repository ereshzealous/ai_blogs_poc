"""Package the published run as a clean evidence bundle and prove the bundle is still complete.

    python3 tools/build_evidence_bundle.py     -> dist/<run>-evidence.zip + dist/<run>-evidence.json

Included: everything in the run directory (manifest, environment, hashes, summary, facts, verification, replay comparison,
tests, raw/, experiments/, scenarios/ with their tapes and world databases, diffs/, config_snapshot/, supplementary/).
Excluded: packaging noise (__MACOSX, ._*, .DS_Store, __pycache__) and worktrees/, the throwaway git worktrees used to
apply the change patches; the patches themselves stay as diffs/*.diff, which is what the verifier checks.

The bundle is then extracted to a temporary directory and scripts/verify_evidence.py is run on the extracted copy.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "layered_architecture_poc"
NOISE = {"__MACOSX", "__pycache__", ".DS_Store"}


def keep(p: Path, run: Path) -> bool:
    parts = p.relative_to(run).parts
    return not (parts[0] == "worktrees" or any(x in NOISE or x.startswith("._") for x in parts))


def main() -> None:
    run = POC / "runs" / (POC / "runs" / "PUBLISHED").read_text().strip()
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    z = out / f"{run.name}-evidence.zip"
    files = sorted(p for p in run.rglob("*") if p.is_file() and keep(p, run))
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, f"{run.name}/{p.relative_to(run)}")
    with tempfile.TemporaryDirectory() as d:
        with zipfile.ZipFile(z) as zf:
            zf.extractall(d)
        copy = Path(d) / run.name
        p = subprocess.run(["uv", "run", "python", "scripts/verify_evidence.py", str(copy)], cwd=POC, capture_output=True, text=True)
        v = json.loads((copy / "verification.json").read_text())
    info = {"bundle": z.name, "run": run.name, "files": len(files), "bytes": z.stat().st_size,
            "sha256": hashlib.sha256(z.read_bytes()).hexdigest(), "excluded": sorted(NOISE) + ["._*", "worktrees/"],
            "verified_after_extraction": {"ok": v["ok"] and p.returncode == 0, "passed": v["passed"], "total": v["total"]}}
    (out / f"{run.name}-evidence.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info, indent=1))
    sys.exit(0 if info["verified_after_extraction"]["ok"] else 1)


if __name__ == "__main__":
    main()
