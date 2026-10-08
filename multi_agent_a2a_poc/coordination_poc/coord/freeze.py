"""Freeze (and later verify) everything that defines the experiment, before the blind run.

    python -m coord.freeze write      # writes experiments/FROZEN.sha256 and FROZEN.at, stamps the preregistration
    python -m coord.freeze check      # recomputes and compares; non-zero exit on any unexplained difference
    python -m coord.freeze post-run D<n> <path>...   # record a post-run change (after DEVIATIONS.md says why)

Frozen: all code of the system under test and its scorer (coord/*.py except the post-hoc readers listed in POST_HOC), config (config/*.yaml), fixtures and runbooks, ground truth, the preregistration and
the pinned dependency lock.  After the freeze, a change to any of these is a deviation and goes to DEVIATIONS.md.

A post-run change (a fix made after the recorded runs) never rewrites FROZEN.sha256.  The file as it ran is kept under
experiments/as-run/<path> and must still hash to its frozen digest; the changed file's digest is listed in
experiments/POST-RUN-CHANGES.sha256 with its deviation id.  `check` passes only if every difference is explained that way.
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

from coord.util import ROOT

EXP = ROOT / "experiments"


# Post-run tooling that reads recorded data and decides nothing about a run: not part of the system under test.
POST_HOC = {"analysis.py", "report.py", "verify_replay.py", "freeze.py"}


def frozen_files() -> list[Path]:
    code = [p for p in sorted((ROOT / "coord").glob("*.py")) if p.name not in POST_HOC]
    files = code + sorted((ROOT / "config").glob("*.yaml")) + sorted((ROOT / "fixtures").glob("*.yaml"))
    files += [ROOT / "groundtruth" / "labels.yaml", EXP / "preregistration.toml", ROOT / "pyproject.toml", ROOT / "uv.lock"]
    return files


def digest_lines() -> list[str]:
    return [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT)}" for p in frozen_files()]


POST_RUN = EXP / "POST-RUN-CHANGES.sha256"   # "<sha256>  <path>  <deviation>"
AS_RUN = EXP / "as-run"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def post_run_entries() -> dict[str, tuple[str, str]]:
    if not POST_RUN.exists():
        return {}
    out = {}
    for line in POST_RUN.read_text().splitlines():
        h, path, dev = line.split("  ")
        out[path] = (h, dev)
    return out


def main() -> None:
    cmd = (sys.argv[1:] or ["check"])[0]
    if cmd == "write":
        at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        pre = EXP / "preregistration.toml"
        pre.write_text(pre.read_text().replace('frozen = "SET-AT-FREEZE"', f'frozen = "{at}"'))
        (EXP / "FROZEN.sha256").write_text("\n".join(digest_lines()) + "\n")
        (EXP / "FROZEN.at").write_text(at + "\n")
        print(f"frozen {len(frozen_files())} files at {at}")
        return
    frozen = {path: h for h, path in (line.split("  ", 1) for line in (EXP / "FROZEN.sha256").read_text().splitlines())}
    if cmd == "post-run":
        dev, paths = sys.argv[2], sys.argv[3:]
        entries = post_run_entries()
        for rel in paths:
            kept = AS_RUN / rel
            if not kept.exists() or sha(kept) != frozen[rel]:
                sys.exit(f"{rel}: experiments/as-run/{rel} must exist and hash to the frozen digest")
            entries[rel] = (sha(ROOT / rel), dev)
        POST_RUN.write_text("".join(f"{h}  {rel}  {d}\n" for rel, (h, d) in sorted(entries.items())))
        print(f"recorded {len(paths)} post-run change(s) under {dev}")
        return
    got = {str(p.relative_to(ROOT)): sha(p) for p in frozen_files()}
    post = post_run_entries()
    bad, explained = [], []
    for rel in sorted(set(frozen) | set(got)):
        if frozen.get(rel) == got.get(rel):
            continue
        h_dev = post.get(rel)
        kept = AS_RUN / rel
        if h_dev and got.get(rel) == h_dev[0] and kept.exists() and sha(kept) == frozen.get(rel):
            explained.append(f"  {rel}: post-run change {h_dev[1]} (as run: experiments/as-run/{rel}, matches the frozen digest)")
        else:
            bad.append(f"  {rel}: frozen {frozen.get(rel, '-')[:12]}, now {got.get(rel, '-')[:12]}")
    if bad:
        print("FROZEN CHECK FAILED", *bad, sep="\n")
        sys.exit(1)
    print(f"FROZEN CHECK OK ({len(got)} files, frozen at {(EXP / 'FROZEN.at').read_text().strip()}; "
          f"{len(got) - len(explained)} unchanged, {len(explained)} changed after the run and recorded in DEVIATIONS.md)", *explained, sep="\n")


if __name__ == "__main__":
    main()
