"""Freeze (and later verify) everything that defines the experiment, before the held-out run.

    uv run python -m s2_eval.freeze write      # experiments/FROZEN.sha256 + FROZEN.at, stamps the preregistration
    uv run python -m s2_eval.freeze check      # recompute and compare; non-zero exit on any unexplained difference
    uv run python -m s2_eval.freeze post-run D<n> <path>...   # record a post-run change (after DEVIATIONS.md says why)

Frozen: the system under test (knowledge_rag/), the measurement code (s2_eval/ except the post-hoc readers in POST_HOC),
the corpus, the cases, the ground truth, the verifier pairs, every config file, the index and its embedding tape, the
preregistration and the dependency lock. A post-run change never rewrites FROZEN.sha256: the file as it ran is kept
under experiments/as-run/<path> and must still hash to its frozen digest; `check` passes only if every difference is
explained that way.
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

from knowledge_rag.util import ROOT

EXP = ROOT / "experiments"
POST_HOC = {"analysis.py", "report.py", "freeze.py", "cli.py", "verify_evidence.py", "exploratory.py", "__init__.py"}
POST_RUN = EXP / "POST-RUN-CHANGES.sha256"
AS_RUN = EXP / "as-run"


def frozen_files() -> list[Path]:
    files = sorted((ROOT / "knowledge_rag").glob("*.py"))
    files += [p for p in sorted((ROOT / "s2_eval").glob("*.py")) if p.name not in POST_HOC]
    for d, pat in (("corpus", "*.yaml"), ("cases", "*.yaml"), ("groundtruth", "*.yaml"), ("config", "*.yaml")):
        files += sorted((ROOT / d).glob(pat))
    files += sorted(EXP.glob("verifier-pairs-*.yaml"))
    files += [ROOT / "index" / "units.jsonl", ROOT / "index" / "embeddings.jsonl", ROOT / "index" / "manifest.json",
              EXP / "preregistration.toml", ROOT / "pyproject.toml", ROOT / "uv.lock"]
    return [f for f in files if f.exists()]


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
        (EXP / "FROZEN.sha256").write_text("".join(f"{sha(p)}  {p.relative_to(ROOT)}\n" for p in frozen_files()))
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
    post = post_run_entries()
    now = {str(p.relative_to(ROOT)): sha(p) for p in frozen_files()}
    bad, explained = [], []
    for rel, h in frozen.items():
        cur = now.get(rel)
        if cur == h:
            continue
        if rel in post and post[rel][0] == cur and (AS_RUN / rel).exists() and sha(AS_RUN / rel) == h:
            explained.append(f"{rel} ({post[rel][1]})")
        else:
            bad.append(rel)
    new = sorted(set(now) - set(frozen))
    print(f"FROZEN {(EXP / 'FROZEN.at').read_text().strip()}: {len(frozen) - len(bad) - len(explained)} of {len(frozen)} files unchanged")
    for e in explained:
        print(f"  changed after the run, explained: {e}")
    for b in bad:
        print(f"  CHANGED: {b}")
    for n in new:
        print(f"  not frozen (added later): {n}")
    if bad:
        sys.exit("FROZEN CHECK FAILED")
    print("FROZEN CHECK OK")


if __name__ == "__main__":
    main()
