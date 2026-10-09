"""Shared helpers: the declared configuration, deterministic draws, canonical JSON, hashes and the preregistration
freeze check."""

from __future__ import annotations

import hashlib
import json
import math
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

POC = Path(__file__).resolve().parents[1]
CONFIG = POC / "config"
EXPERIMENTS = POC / "experiments"
RUNS = POC / "runs"

# Files whose content the preregistration freezes (experiments/FROZEN.sha256).
FROZEN_FILES = ["experiments/preregistration.toml", "experiments/scenarios.toml", "experiments/fixtures/knowledge.json",
                "experiments/fixtures/eval_suite.json", "config/platform.toml", "config/models.toml", "config/tools.toml",
                "config/workflows.toml", "config/releases.toml"]


@lru_cache(maxsize=None)
def cfg(name: str) -> dict:
    return tomllib.loads((CONFIG / f"{name}.toml").read_text())


@lru_cache(maxsize=None)
def experiments(name: str) -> dict:
    return tomllib.loads((EXPERIMENTS / f"{name}.toml").read_text())


@lru_cache(maxsize=None)
def fixture(name: str) -> Any:
    return json.loads((EXPERIMENTS / "fixtures" / f"{name}.json").read_text())


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def dump(obj: Any) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def draw(*key: Any) -> float:
    """A deterministic uniform draw in [0, 1) from a key: the same key gives the same number on every machine."""
    h = hashlib.sha256("|".join(map(str, key)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def pick(weights: dict | list, *key: Any) -> Any:
    """A deterministic weighted choice. dict: {option: weight}; list: weights of options 1..n."""
    items = list(weights.items()) if isinstance(weights, dict) else [(i + 1, w) for i, w in enumerate(weights)]
    u, acc = draw(*key) * sum(w for _, w in items), 0.0
    for opt, w in items:
        acc += w
        if u < acc:
            return opt
    return items[-1][0]


def pct(sorted_vals: list[float], p: float) -> float:
    """Nearest-rank percentile (p in 0..100) of an ascending list; 0 for an empty list."""
    if not sorted_vals:
        return 0
    k = max(1, math.ceil(p / 100 * len(sorted_vals)))
    return sorted_vals[k - 1]


def r1(x: float) -> float:
    return round(float(x), 1)


def r2(x: float) -> float:
    return round(float(x), 2)


def source_sha256() -> dict[str, str]:
    return {p.relative_to(POC).as_posix(): sha256_file(p) for p in sorted((POC / "agentops").glob("*.py"))}


def frozen_sha256() -> dict[str, str]:
    return {f: sha256_file(POC / f) for f in FROZEN_FILES if (POC / f).exists()}


def prereg_check() -> list[str]:
    """Frozen files whose hash differs from experiments/FROZEN.sha256 (empty list: unchanged since the freeze)."""
    p = EXPERIMENTS / "FROZEN.sha256"
    if not p.exists():
        return ["experiments/FROZEN.sha256 missing (not frozen yet)"]
    want = dict(line.split("  ", 1)[::-1] for line in p.read_text().splitlines() if line.strip())
    have = frozen_sha256()
    return sorted(f for f in set(want) | set(have) if want.get(f) != have.get(f))


def freeze() -> None:
    lines = [f"{h}  {f}" for f, h in sorted(frozen_sha256().items())]
    (EXPERIMENTS / "FROZEN.sha256").write_text("\n".join(lines) + "\n")
