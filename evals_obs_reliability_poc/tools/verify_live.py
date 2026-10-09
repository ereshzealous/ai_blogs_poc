"""Replay the real-model end-to-end run from its tapes in a scratch copy of the POC, and compare it with the recorded run.

    python3 tools/verify_live.py [--record]        (make replay-live)  -> evidence/runs/<live run>/replay.json

No model is called: the gateway returns each recorded answer and refuses any call whose prompt differs from the recorded one.
Excluded from the byte comparison: */volatile/* (wall times, pids, model latency), manifest.json (the recording session) and
RUN-NOTES.md (the human notes written after the recording), as in tools/verify_run.py.
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
LIVE = "2026-10-07-live"


def files(d: Path) -> dict[str, Path]:
    return {p.relative_to(d).as_posix(): p for p in d.rglob("*")
            if p.is_file() and "volatile" not in p.parts and p.name not in ("manifest.json", "RUN-NOTES.md")}


def main() -> None:
    pub = POC / "runs" / LIVE
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "poc"
        shutil.copytree(POC, copy, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "runs", "var"))
        (copy / "runs").mkdir()
        subprocess.run(["uv", "run", "--quiet", "--project", str(copy), "python", "-m", "recovery.run", "replay-live", "--run-id", LIVE,
                        "--source", str(pub)], cwd=copy, check=True, capture_output=True)
        a, b = files(pub), files(copy / "runs" / LIVE)
        problems = [f"only in recorded: {k}" for k in sorted(set(a) - set(b))] + [f"only in replay: {k}" for k in sorted(set(b) - set(a))]
        problems += [f"differs: {k}" for k in sorted(set(a) & set(b)) if not filecmp.cmp(a[k], b[k], shallow=False)]
    if "--record" in sys.argv:
        out = ROOT / "evidence" / "runs" / LIVE / "replay.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"schema": "pae-proof/v1", "run_id": LIVE, "replay_level": "EXACT", "files": len(a),
                                   "method": "every run re-executed from source with the model answers read from the recorded tapes (tools/verify_live.py)",
                                   "classes": {"DETERMINISTIC_EQUIVALENT": len(a) - len(problems), "REGRESSION": len(problems)},
                                   "differences": problems, "equivalent": not problems, "fresh_model_calls": 0}, indent=1, sort_keys=True) + "\n")
    if problems:
        print("\n".join(problems[:30]))
        sys.exit(1)
    print(f"verified: the real-model run {LIVE} replays from its tapes: {len(a)} files byte-identical, 0 model calls")


if __name__ == "__main__":
    main()
