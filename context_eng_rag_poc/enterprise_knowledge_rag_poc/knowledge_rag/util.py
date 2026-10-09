"""Small shared helpers: paths, YAML, hashing, the token estimate, time."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus"
CONFIG = ROOT / "config"
INDEX = ROOT / "index"


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text())


def config(name: str) -> dict:
    return load_yaml(CONFIG / name)


def sha256(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical(obj: Any) -> str:
    """Stable JSON: sorted keys, no whitespace drift. Used for hashes and byte-exact replay comparisons."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def est_tokens(text: str) -> int:
    """The context budget's unit: an ESTIMATE, ceil(UTF-8 bytes / 4). Not a model tokenizer. Live runs also record the
    model server's own prompt token counts, so the estimate can be compared with a real one."""
    return math.ceil(len(text.encode("utf-8")) / 4)


def slug(heading: str) -> str:
    """Section heading -> unit-id slug: lowercase, each run of non-alphanumerics -> '-', trimmed."""
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def ts(s: str | None) -> datetime | None:
    if s is None:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm(s: str) -> str:
    """Normalisation for quote matching: lowercase, typographic dashes/quotes/arrows to ASCII, whitespace collapsed."""
    s = s.lower()
    for a, b in (("→", "->"), ("–", "-"), ("—", "-"), ("‑", "-"), ("‐", "-"), ("‘", "'"),
                 ("’", "'"), ("“", '"'), ("”", '"'), (" ", " "), (" ", " ")):
        s = s.replace(a, b)
    s = re.sub(r"\s+", " ", s)
    return s.strip().strip('"').strip("'").strip()
