"""Preregistration freeze: hash the pass criteria and fixtures BEFORE the first run; refuse a run that changed them.

    uv run hitl freeze --note "…"        -> proof/FREEZE.json
    (hitl proof calls check() first and stops if a guarded file changed after the freeze)

Guarded (a change stops the run until it is recorded in proof/DEVIATIONS.md and re-frozen): the preregistration, the
generated checks, every config file (identities, policy v7 and v8, capabilities) and the scenario fixture (the simulated
systems' starting data).  Code is hashed too, for the record: a change is listed in the run manifest, not refused.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from hitl.base import canonical
from hitl.enterprise import SCENARIO

POC = Path(__file__).resolve().parents[1]
FROZEN = POC / "proof" / "FREEZE.json"
GUARDED = ["proof/preregistration.toml", "proof/experiments.toml"]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def fixture_sha() -> str:
    data = {**SCENARIO, "deployments": {f"{s}/{e}": v for (s, e), v in SCENARIO["deployments"].items()}}
    return hashlib.sha256(canonical(data).encode()).hexdigest()


def snapshot() -> dict:
    guarded = {f: _sha(POC / f) for f in GUARDED}
    guarded.update({f"config/{p.name}": _sha(p) for p in sorted((POC / "config").glob("*.yaml"))})
    return {"guarded": guarded, "scenario_fixture_sha256": fixture_sha(),
            "code": {f"hitl/{p.name}": _sha(p) for p in sorted((POC / "hitl").glob("*.py"))}}


def freeze(note: str) -> Path:
    """A re-freeze keeps every earlier freeze in `history`, so the first, pre-run freeze is never lost."""
    snap = snapshot()
    old = json.loads(FROZEN.read_text()) if FROZEN.exists() else None
    hist = (old.get("history", []) + [{k: old[k] for k in ("frozen_at", "note", "guarded")}]) if old else []
    FROZEN.write_text(json.dumps({"schema": "hitl-freeze/v1", "frozen_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                  "note": note, **snap, "history": hist}, indent=1, sort_keys=True))
    return FROZEN


def check() -> dict:
    """{ok, frozen_at, changed_guarded, changed_code}: ok is False when any guarded file differs from the freeze."""
    if not FROZEN.exists():
        return {"ok": False, "frozen_at": None, "changed_guarded": ["proof/FREEZE.json missing: run `hitl freeze` first"], "changed_code": []}
    f, now = json.loads(FROZEN.read_text()), snapshot()
    cg = sorted(k for k in set(f["guarded"]) | set(now["guarded"]) if f["guarded"].get(k) != now["guarded"].get(k))
    if f["scenario_fixture_sha256"] != now["scenario_fixture_sha256"]:
        cg.append("scenario fixture (hitl/enterprise.py SCENARIO)")
    cc = sorted(k for k in set(f["code"]) | set(now["code"]) if f["code"].get(k) != now["code"].get(k))
    return {"ok": not cg, "frozen_at": f["frozen_at"], "note": f["note"], "changed_guarded": cg, "changed_code": cc,
            "guarded_sha256": f["guarded"], "scenario_fixture_sha256": f["scenario_fixture_sha256"]}
