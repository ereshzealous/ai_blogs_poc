"""Small shared helpers: canonical JSON, hashing, collision-safe ids, paths."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

POC_ROOT = Path(__file__).resolve().parents[2]  # .../poc
REPO_ROOT = POC_ROOT.parent  # .../tool-sprawl-mcp
DATA_DIR = POC_ROOT / "data"
STATE_DIR = POC_ROOT / ".state"
EXPERIMENT_DIR = REPO_ROOT / "experiment"


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8 preserved.

    Used for every digest (approval binding, audit chain, frozen hashes) so the
    same logical value always hashes the same way.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_obj(obj: Any) -> str:
    return sha256_text(canonical_json(obj))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def new_id(prefix: str) -> str:
    """Collision-safe id: wall-clock ms + pid + 48 random bits.

    Two runners started in the same second must never share a run directory.
    """
    return f"{prefix}-{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}-{secrets.token_hex(6)}"


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n")
    tmp.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text())


def append_jsonl(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(canonical_json(obj) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path: Path) -> list[Any]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
