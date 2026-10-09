"""Freeze: hash everything that defines the experiment. A recorded run refuses to start if anything changed since."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from s1_experiments.scenario import ROOT

FROZEN = ROOT / "FROZEN.json"
PATTERNS = ["scenarios/*.yaml", "src/governed_memory/policy/*.yaml", "src/governed_memory/**/*.py",
            "src/s1_experiments/*.py", "docs/EXPERIMENTS.md"]
# Presentation only (CLI wiring, report rendering, this file): cannot change a result, so a fix here does not
# invalidate a recorded run. Everything else above defines the experiment.
PRESENTATION = {"src/s1_experiments/cli.py", "src/s1_experiments/report.py", "src/s1_experiments/freeze.py"}


def current_hashes(include_presentation: bool = False) -> dict[str, str]:
    files = sorted({p for pat in PATTERNS for p in ROOT.glob(pat) if p.is_file()})
    h = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    return h if include_presentation else {k: v for k, v in h.items() if k not in PRESENTATION}


def definition_changes(recorded: dict[str, str]) -> list[str]:
    """Experiment-defining files whose hash differs from a recorded run's hashes.json."""
    now = current_hashes()
    rec = {k: v for k, v in recorded.items() if k not in PRESENTATION}
    return sorted(k for k in set(rec) | set(now) if rec.get(k) != now.get(k))


def freeze() -> dict[str, str]:
    h = current_hashes()
    FROZEN.write_text(json.dumps(h, indent=1) + "\n")
    return h


def check() -> list[str]:
    """Paths whose content differs from the frozen hashes (empty when unchanged)."""
    if not FROZEN.exists():
        return ["FROZEN.json missing: run `s1 freeze`"]
    frozen = {k: v for k, v in json.loads(FROZEN.read_text()).items() if k not in PRESENTATION}
    now = current_hashes()
    return sorted(k for k in set(frozen) | set(now) if frozen.get(k) != now.get(k))


def digest(h: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(h, sort_keys=True).encode()).hexdigest()[:16]
