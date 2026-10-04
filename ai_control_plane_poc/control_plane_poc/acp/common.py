"""Small shared helpers: canonical JSON, hashing, dotted paths, the POC's file layout.

Everything in the POC is deterministic: no wall clock, no randomness. Time is a logical tick passed in by the caller.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

POC = Path(__file__).resolve().parents[1]
CONFIG = POC / "config"
AGENTS_DIR = POC / "acp" / "agents"


def canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(data: str | bytes) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def digest(obj: Any) -> str:
    return sha256(canon(obj))


def sign(payload_sha: str) -> str:
    """HMAC over a bundle hash. The POC uses one local key; production would use an asymmetric signature."""
    key = (CONFIG / "signing.key").read_bytes()
    return hmac.new(key, payload_sha.encode(), hashlib.sha256).hexdigest()


def verify_signature(payload_sha: str, signature: str) -> bool:
    return hmac.compare_digest(sign(payload_sha), signature)


def get_path(d: dict, path: str, default: Any = None) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def set_path(d: dict, path: str, value: Any) -> dict:
    out = copy.deepcopy(d)
    cur = out
    parts = path.split(".")
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = copy.deepcopy(value)
    return out


def code_sha256(directory: Path = AGENTS_DIR) -> str:
    """One hash over every agent source file (name + bytes), the evidence that agent code did not change."""
    h = hashlib.sha256()
    for p in sorted(directory.glob("*.py")):
        h.update(p.name.encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n")


def read_json(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text()) if path.exists() else default


def append_chained(path: Path, record: dict) -> dict:
    """Append a hash-chained JSON line: every row carries the previous row's hash, so an edit breaks the chain."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = path.read_text().splitlines() if path.exists() else []
    prev = json.loads(rows[-1])["hash"] if rows else "0" * 64
    row = {"n": len(rows) + 1, "prev": prev, **record}
    row["hash"] = digest(row)
    with path.open("a") as f:
        f.write(canon(row) + "\n")
    return row


def verify_chain(path: Path) -> bool:
    prev = "0" * 64
    for line in path.read_text().splitlines() if path.exists() else []:
        row = json.loads(line)
        body = {k: v for k, v in row.items() if k != "hash"}
        if row["prev"] != prev or digest(body) != row["hash"]:
            return False
        prev = row["hash"]
    return True


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []
