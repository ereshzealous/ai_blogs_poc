"""Configuration and the deterministic clock.  Every id and timestamp in a run derives from these, so a run is
reproducible byte for byte."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config"
T0 = 1790690520.0            # 2026-09-29 14:02:00 UTC, the moment the alert fires (the F3 scenario)
MIN = 60.0


def load(name: str) -> dict[str, Any]:
    return yaml.safe_load((CONFIG / name).read_text())


def digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def short_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}-" + hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12]


class Clock:
    """Simulated time: starts at the alert and only moves when something advances it."""

    def __init__(self, start: float = T0):
        self.t = start

    def now(self) -> float:
        return self.t

    def advance(self, seconds: float) -> float:
        self.t += seconds
        return self.t
