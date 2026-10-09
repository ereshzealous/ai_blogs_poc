"""One-time relocation of the runs made before the Proof Contract layout (pae-proof/v1). Moves, never edits.

    python3 tools/relocate_legacy.py            -> evidence/RELOCATION.json

Before the contract, run_proof.py wrote its own results.json and summary.* straight into evidence/runs/<run>/, the
replay went to a sibling run directory and the negative control to evidence/negative-control/. The contract's package
needs evidence/runs/<run>/{manifest.json, results.json, checks.jsonl, summary.*, SHA256SUMS}, so each legacy run's own
files move, byte for byte, into the layout every later run is written in:

    evidence/runs/<run>/raw/                      what run_proof.py wrote (and its terminal output)
    evidence/runs/<run>/replay/raw/               the second run that replays it
    evidence/runs/<run>/negative-control/raw/     the negative control made with the same source

Every file's SHA-256 is taken before the move and checked after it; the mapping is recorded in evidence/RELOCATION.json.
The script refuses to overwrite a destination and refuses to run twice.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "evidence"
RUNS = EV / "runs"
NC = EV / "negative-control"
# (source, destination), relative to evidence/; a directory moves with everything under it
MOVES = [
    ("runs/2026-09-30-proof-2/run-output.txt", "runs/2026-09-30-proof-2/raw/run-output.txt"),
    ("runs/2026-09-30-proof-2/replay-comparison.json", "runs/2026-09-30-proof-2/replay/replay-comparison.json"),
    ("runs/2026-09-30-proof-2", "runs/2026-09-30-proof-2/raw"),   # the remaining run_proof.py output
    ("runs/2026-09-30-proof-2-replay", "runs/2026-09-30-proof-2/replay/raw"),
    *[(f"negative-control/{f}", f"runs/2026-09-30-proof-2/negative-control/raw/{f}")
      for f in ("control.json", "mutation.diff", "results.json", "run-output.txt", "summary.json", "summary.md")],
    ("runs/2026-09-30-proof/run-output.txt", "runs/2026-09-30-proof/raw/run-output.txt"),
    ("runs/2026-09-30-proof/replay-comparison.json", "runs/2026-09-30-proof/replay/replay-comparison.json"),
    ("runs/2026-09-30-proof", "runs/2026-09-30-proof/raw"),
    ("runs/2026-09-30-proof-replay", "runs/2026-09-30-proof/replay/raw"),
    ("negative-control/superseded-2026-09-30", "runs/2026-09-30-proof/negative-control/raw"),
]
KEEP_AT_RUN_ROOT = {"previous-run-comparison.json"}   # a comparison between two published runs, not the run's own output


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def files(p: Path) -> list[Path]:
    return [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.is_file())


def main() -> int:
    log = EV / "RELOCATION.json"
    if log.exists():
        print("refused: evidence/RELOCATION.json exists; the legacy runs were already relocated")
        return 1
    before = {}
    for src, _ in MOVES:
        for f in files(EV / src):
            if f.name in KEEP_AT_RUN_ROOT and f.parent == EV / src:
                continue
            before[f.relative_to(EV).as_posix()] = sha(f)
    records = []
    for src, dst in MOVES:
        s, d = EV / src, EV / dst
        if not s.exists():
            raise SystemExit(f"missing source: evidence/{src}")
        if s.is_dir() and d.is_relative_to(s):            # move a directory into a child of itself: via a temporary name
            tmp = s.with_name(s.name + ".relocating")
            s.rename(tmp)
            d = tmp / Path(dst).relative_to(src)
            d.parent.mkdir(parents=True, exist_ok=True)
            moved = []
            for f in sorted(tmp.iterdir()):
                if f.name in ("raw", "replay", "negative-control") or f.name in KEEP_AT_RUN_ROOT:
                    continue
                target = d / f.name
                if target.exists():
                    raise SystemExit(f"refusing to overwrite evidence/{target.relative_to(EV)}")
                d.mkdir(parents=True, exist_ok=True)
                shutil.move(str(f), str(target))
                moved.append(f.name)
            tmp.rename(s)
            records += [{"from": f"{src}/{n}", "to": f"{dst}/{n}"} for n in moved]
            continue
        if d.exists():
            raise SystemExit(f"refusing to overwrite evidence/{dst}")
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s), str(d))
        records.append({"from": src, "to": dst})
    # every file found again under its new path, with the same hash
    after, missing, changed = {}, [], []
    for r in records:
        for f in files(EV / r["to"]):
            rel_new = f.relative_to(EV).as_posix()
            rel_old = r["from"] + rel_new[len(r["to"]):]
            after[rel_old] = (rel_new, sha(f))
    for old, h in before.items():
        if old not in after:
            missing.append(old)
        elif after[old][1] != h:
            changed.append(old)
    if missing or changed:
        raise SystemExit(f"relocation check failed: missing {missing[:5]}, changed {changed[:5]}")
    doc = {
        "schema": "pae-proof/v1 relocation",
        "relocated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "why": "the runs made before the Proof Contract layout wrote results.json and summary.* where the contract's package goes; "
               "their own files moved, unchanged, under raw/, replay/raw/ and negative-control/raw/ of the run they belong to",
        "files": len(before), "all_hashes_identical": True,
        "moves": records,
        "map": [{"from": o, "to": after[o][0], "sha256": h} for o, h in sorted(before.items())],
    }
    log.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"relocated {len(before)} files in {len(records)} moves; every SHA-256 identical -> evidence/RELOCATION.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
