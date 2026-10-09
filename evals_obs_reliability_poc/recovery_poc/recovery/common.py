"""Shared helpers: paths, frozen configuration, canonical JSON, deterministic identifiers."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any, Iterable

POC = Path(__file__).resolve().parents[1]
CONFIG = POC / "config"
EXPERIMENTS = POC / "experiments"
RUNS = POC / "runs"


def load_toml(path: Path | str) -> dict:
    p = Path(path)
    return tomllib.loads((p if p.is_absolute() else POC / p).read_text())


def canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256(data: str | bytes) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def det_id(prefix: str, *parts: Any, n: int = 8) -> str:
    """A deterministic identifier: the same run, step and attempt always get the same id (replay compares bytes)."""
    return f"{prefix}-{sha256('|'.join(str(p) for p in parts))[:n]}"


def hex_id(nbytes: int, *parts: Any) -> str:
    """W3C-shaped ids (trace id = 16 bytes, span id = 8 bytes), deterministic from their parts."""
    return sha256("|".join(str(p) for p in parts))[: nbytes * 2]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(canon(r) + "\n" for r in rows))


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(canon(row) + "\n")


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False, default=str) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def tools() -> dict:
    return load_toml("config/tools.toml")["tools"]


def matrix() -> dict:
    return load_toml("config/recovery-matrix.toml")


def world_config() -> dict:
    return load_toml("config/world.toml")


def scenarios() -> list[dict]:
    return load_toml("experiments/scenarios.toml")["scenarios"]


def prereg() -> dict:
    return load_toml("experiments/preregistration.toml")


FROZEN_FILES = ["config/tools.toml", "config/recovery-matrix.toml", "config/policy.toml", "config/world.toml",
                "experiments/preregistration.toml", "experiments/scenarios.toml", "experiments/model_slice/cases.jsonl",
                "experiments/model_slice/labels.jsonl", "experiments/model_slice/prompt.md"]


def prereg_check() -> list[str]:
    """Problems with the freeze: a frozen file whose hash differs from experiments/FROZEN.sha256."""
    want = {}
    for line in (EXPERIMENTS / "FROZEN.sha256").read_text().splitlines():
        h, _, f = line.partition("  ")
        want[f.strip()] = h
    out = []
    for f in FROZEN_FILES:
        got = sha256((POC / f).read_bytes())
        if want.get(f) != got:
            out.append(f"{f}: {got[:12]} != frozen {str(want.get(f))[:12]}")
    return out
