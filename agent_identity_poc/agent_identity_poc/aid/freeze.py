"""Declared criteria and the freeze: the checks a run must evaluate are declared in proof/preregistration.toml and hashed,
with every config file and the criteria code, before the final recorded run.

    uv run aid freeze --note "…"        -> proof/FREEZE.json
    (aid experiments refuses to run when a guarded file changed after the freeze, and when the checks it evaluates differ
     from the declared list)
"""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import inspect
import json
import tomllib
from pathlib import Path

POC = Path(__file__).resolve().parents[1]
FROZEN = POC / "proof" / "FREEZE.json"
PREREG = POC / "proof" / "preregistration.toml"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def criteria_sha() -> str:
    from aid import experiments
    return _sha((inspect.getsource(experiments.checks_for) + inspect.getsource(experiments.global_assertions)).encode())


def declared_checks_from_source() -> list[dict]:
    """The check list read statically from aid/experiments.py (no experiment is run)."""
    tree = ast.parse((POC / "aid" / "experiments.py").read_text())
    out: list[dict] = []
    for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("checks_for", "global_assertions")):
        lst = next(n for n in ast.walk(fn) if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in ("c", "g"))
        n: dict[str, int] = {}
        for t in lst.value.elts:
            vals = [e.value if isinstance(e, ast.Constant) else None for e in t.elts]
            if fn.name == "checks_for":
                e, arm, kind, text = vals[:4]
                n[e] = n.get(e, 0) + 1
                out.append({"id": f"{e}-{n[e]:02d}", "experiment": e, "arm": arm, "kind": kind, "check": text})
            else:
                gid, text = vals[:2]
                out.append({"id": gid, "experiment": "GA", "arm": "C" if gid not in ("G06", "G09") else ("AC" if gid == "G06" else "ABC"),
                            "kind": "invariant", "check": text})
    return out


def declared() -> list[dict]:
    return tomllib.loads(PREREG.read_text())["checks"]


def snapshot() -> dict:
    g = {"proof/preregistration.toml": _sha(PREREG.read_bytes())}
    g.update({f"config/{p.name}": _sha(p.read_bytes()) for p in sorted((POC / "config").glob("*.yaml"))})
    g["criteria (checks_for + global_assertions)"] = criteria_sha()
    return {"guarded": g, "code": {f"aid/{p.name}": _sha(p.read_bytes()) for p in sorted((POC / "aid").glob("*.py"))}}


def freeze(note: str) -> Path:
    snap = snapshot()
    old = json.loads(FROZEN.read_text()) if FROZEN.exists() else None
    hist = (old.get("history", []) + [{k: old[k] for k in ("frozen_at", "note", "guarded")}]) if old else []
    FROZEN.write_text(json.dumps({"schema": "aid-freeze/v1", "frozen_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                  "note": note, **snap, "history": hist}, indent=1, sort_keys=True))
    return FROZEN


def check() -> dict:
    if not FROZEN.exists():
        return {"ok": True, "frozen": False, "changed_guarded": [], "changed_code": []}
    f, now = json.loads(FROZEN.read_text()), snapshot()
    cg = sorted(k for k in set(f["guarded"]) | set(now["guarded"]) if f["guarded"].get(k) != now["guarded"].get(k))
    cc = sorted(k for k in set(f["code"]) | set(now["code"]) if f["code"].get(k) != now["code"].get(k))
    return {"ok": not cg, "frozen": True, "frozen_at": f["frozen_at"], "note": f["note"], "guarded": f["guarded"], "changed_guarded": cg,
            "changed_code": cc, "history": f.get("history", [])}
