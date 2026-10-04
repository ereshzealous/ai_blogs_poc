"""Frozen inputs and model digests against the current evidence revision (./sprawl verify).

freeze.py --verify reads model digests from `ollama list`; this check asks the HTTP API instead (the same 12-hex id), so
it also works in a container or through ./sprawl's relay.  --strict fails when the digests cannot be checked.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

POC = Path(__file__).resolve().parents[1]
ROOT = POC.parent
EXP = ROOT / "experiment"
sys.path.insert(0, str(Path(__file__).parent))
from doctor import FAIL, OK, WARN, ollama_models  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ns = ap.parse_args()
    spec = importlib.util.spec_from_file_location("freeze", POC / "scripts" / "freeze.py")
    fz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fz)
    models = ollama_models()
    fz.ollama_digest = lambda name: (models or {}).get(name)
    rev = fz.current_revision()
    frozen = json.loads((ROOT / rev["freeze"]).read_text())
    now = fz.compute()
    drift = [k for k in sorted(frozen["hashes"]) if frozen["hashes"][k] != now["hashes"].get(k)]
    for k in drift:
        print(f"  {FAIL} {k}")
    print(f"  {OK if not drift else FAIL} {len(frozen['hashes']) - len(drift)}/{len(frozen['hashes'])} file hashes match evidence revision {rev['id']} ({rev.get('label', '')})")
    if rev["id"] != "r1":
        r1 = json.loads((EXP / "frozen-hashes.json").read_text())["hashes"]
        changed = sorted(k for k in set(r1) | set(frozen["hashes"]) if r1.get(k) != frozen["hashes"].get(k))
        undeclared = sorted(set(changed) - set(rev["changed_from_r1"]))
        v = rev.get("verification", {})
        print(f"  {OK if not undeclared else FAIL} differs from the blind-run freeze (r1) only in the declared {', '.join(changed)}"
              + (f"; recorded rows re-verified by replay: {v['reproduced']}/{v['rows']}" if v else ""))
        drift += undeclared
    if models is None:
        print(f"  {WARN} model digests not checked: Ollama unreachable ({'fails with --strict' if not ns.strict else 'strict'})")
        sys.exit(1 if drift or ns.strict else 0)
    mdrift = {m: (now["models"].get(m), d) for m, d in frozen["models"].items() if now["models"].get(m) != d}
    for m, (have, want) in mdrift.items():
        print(f"  {FAIL} model {m}: {have} (frozen {want})")
    if not mdrift:
        print(f"  {OK} model digests match: " + ", ".join(f"{m} {d}" for m, d in frozen["models"].items()))
    sys.exit(1 if drift or mdrift else 0)


if __name__ == "__main__":
    os.chdir(POC)
    main()
