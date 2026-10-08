"""Freeze the preregistration, the corpus and the configs BEFORE the recorded run; refuse a run that changed them.

    uv run redteam freeze --note "…"    -> proof/FREEZE.json
Code is hashed for the record (a change is listed in the manifest, not refused); the preregistration, corpus and config
are guarded (a change stops the run until it is logged in proof/DEVIATIONS.md and re-frozen).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

POC = Path(__file__).resolve().parents[1]
FROZEN = POC / "proof" / "FREEZE.json"
GUARDED = ["proof/preregistration.toml", "corpus/scenarios.yaml",
           "config/principals.yaml", "config/capabilities.yaml", "config/registry.yaml",
           "config/policy.yaml", "config/egress.yaml", "config/guard.yaml"]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def snapshot() -> dict:
    guarded = {f: _sha(POC / f) for f in GUARDED if (POC / f).exists()}
    code = {f"redteam/{p.name}": _sha(p) for p in sorted((POC / "redteam").glob("*.py"))}
    return {"guarded": guarded, "code": code}


def freeze(note: str) -> Path:
    snap = snapshot()
    old = json.loads(FROZEN.read_text()) if FROZEN.exists() else None
    hist = (old.get("history", []) + [{k: old[k] for k in ("frozen_at", "note", "guarded")}]) if old else []
    FROZEN.parent.mkdir(exist_ok=True)
    FROZEN.write_text(json.dumps({"schema": "t6-freeze/v1",
                                  "frozen_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                  "note": note, **snap, "history": hist}, indent=1, sort_keys=True))
    return FROZEN


def check() -> dict:
    if not FROZEN.exists():
        return {"ok": False, "frozen_at": None, "changed_guarded": ["proof/FREEZE.json missing: run `redteam freeze` first"], "changed_code": []}
    f, now = json.loads(FROZEN.read_text()), snapshot()
    cg = sorted(k for k in set(f["guarded"]) | set(now["guarded"]) if f["guarded"].get(k) != now["guarded"].get(k))
    cc = sorted(k for k in set(f["code"]) | set(now["code"]) if f["code"].get(k) != now["code"].get(k))
    return {"ok": not cg, "frozen_at": f["frozen_at"], "note": f["note"], "changed_guarded": cg, "changed_code": cc}
