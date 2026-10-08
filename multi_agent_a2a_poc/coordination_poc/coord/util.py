"""Small shared helpers: canonical JSON, digests, deterministic ids, paths and config loading."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent          # coordination_poc/
CONFIG = ROOT / "config"
FIXTURES = ROOT / "fixtures"


def canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def digest(obj: Any, n: int = 64) -> str:
    return hashlib.sha256(canon(obj).encode()).hexdigest()[:n]


def home() -> Path:
    """The session directory every process of one benchmark session shares (world.db, platform.db, traces, tapes)."""
    p = Path(os.environ.get("C1_HOME", ROOT / ".local" / "session"))
    p.mkdir(parents=True, exist_ok=True)
    return p


_ENV = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def load_config(name: str) -> dict[str, Any]:
    """Load config/<name>, expanding ${VAR:-default}."""
    text = (CONFIG / name).read_text()
    text = _ENV.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), text)
    return yaml.safe_load(text)


def hhmm(minute: int) -> str:
    day, m = divmod(minute, 1440)
    prefix = f"D{day:+d} " if day else ""
    return f"{prefix}{m // 60:02d}:{m % 60:02d}"
