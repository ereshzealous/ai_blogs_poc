"""freeze.json: the sha256 of every input a run depended on, written when the run starts.

    uv run python -m experiments.freeze --run-id 2026-09-17-recorded --check   # re-hash now and report drift

A published number is only reproducible if the inputs behind it are identified. The freeze records the plan, the
configuration, the prompts, the policy and the code that produced the run, so a later reader can tell whether the
tree they are holding is the tree that was measured. It is a record, not a lock: nothing stops you editing a file,
but `--check` and the verifier will say that you did.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"

# What a run's numbers depend on. Globs are relative to the POC root; order does not matter.
INPUTS = [
    "config/*.yaml",
    "agent_platform/**/*.py",
    "mock_enterprise/**/*.py",
    "monolith/*.py",
    "experiments/*.py",
    "experiments/change_scope/*.py",
    "experiments/change_scope/patches/*.patch",
    "plans/*.yaml",
    "traffic/*.py",
    "agent_platform/knowledge/runbooks/*.md",
    ".importlinter",
    "pyproject.toml",
    "uv.lock",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def files() -> list[Path]:
    out: set[Path] = set()
    for pattern in INPUTS:
        out.update(p for p in ROOT.glob(pattern) if p.is_file() and "__pycache__" not in p.parts)
    return sorted(out)


def git_commit() -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None  # the POC is published inside another repository, or git is unavailable


def build(plan: dict[str, Any] | None = None, retrospective: bool = False) -> dict[str, Any]:
    hashes = {str(p.relative_to(ROOT)): sha256(p) for p in files()}
    digest = hashlib.sha256("".join(f"{k}:{v}" for k, v in sorted(hashes.items())).encode()).hexdigest()
    return {
        "frozen_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # a freeze written after the run records today's tree, not the tree that produced the numbers
        "retrospective": retrospective,
        "python": sys.version.split()[0],
        "git_commit": git_commit(),
        "plan": plan,
        "inputs": INPUTS,
        "files": len(hashes),
        "digest": digest,
        "sha256": hashes,
    }


def write(base: Path, plan: dict[str, Any] | None = None, retrospective: bool = False) -> Path:
    out = base / "freeze.json"
    out.write_text(json.dumps(build(plan, retrospective), indent=2))
    return out


def check(base: Path) -> dict[str, Any]:
    """Compare the recorded hashes with the tree as it is now."""
    recorded = json.loads((base / "freeze.json").read_text())
    now = {str(p.relative_to(ROOT)): sha256(p) for p in files()}
    was = recorded["sha256"]
    changed = sorted(k for k in was.keys() & now.keys() if was[k] != now[k])
    return {
        "run_id": base.name, "frozen_at": recorded["frozen_at"], "digest_recorded": recorded["digest"],
        "digest_now": hashlib.sha256("".join(f"{k}:{v}" for k, v in sorted(now.items())).encode()).hexdigest(),
        "changed": changed, "added": sorted(now.keys() - was.keys()), "removed": sorted(was.keys() - now.keys()),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--check", action="store_true", help="re-hash the tree and report what changed since the run")
    a = ap.parse_args()
    base = RUNS / a.run_id
    if not base.is_dir():
        sys.exit(f"no run directory {base}")
    if a.check:
        if not (base / "freeze.json").exists():
            sys.exit(f"runs/{a.run_id} has no freeze.json: it was recorded before freezes existed")
        d = check(base)
        same = not (d["changed"] or d["added"] or d["removed"])
        print(f"[freeze] {a.run_id}: {'unchanged since the run' if same else 'the tree has moved since the run'}")
        for label in ("changed", "added", "removed"):
            for f in d[label][:20]:
                print(f"  {label:<8} {f}")
        sys.exit(0 if same else 1)
    meta = json.loads((base / "run.json").read_text()) if (base / "run.json").exists() else {}
    after = bool(meta.get("finished"))  # the run is over, so this freeze describes the tree as it is now
    out = write(base, meta.get("plan"), retrospective=after)
    d = json.loads(out.read_text())
    print(f"[freeze] {out.relative_to(ROOT)}: {d['files']} files, digest {d['digest'][:16]}"
          + (" (retrospective: written after the run)" if after else ""))


if __name__ == "__main__":
    main()
