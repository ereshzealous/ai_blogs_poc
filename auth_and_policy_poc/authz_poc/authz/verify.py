"""Verify the recorded run and print one machine-readable summary.

    python3 -m authz.verify [--run runs/2026-09-29-recorded]

It checks, without trusting anything it did not just compute:
  invariants   the 14 named invariants, evaluated now against the code and policy
  tests        the whole suite (L1–L4), run twice: same results both times (deterministic)
  replay       the scenario re-run into a temporary directory; every output compared byte for byte with the run
  audit chain  every record of decisions.jsonl re-hashed from the file alone
and writes into the run directory: tests.json (every test and subtest), manifest.json (sha256 of every input) and
verification.json (the summary, then the detail). Exit status 1 if anything fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import tempfile
from pathlib import Path

from . import record_tests
from .invariants import check_all
from .run import RUN_ID, run as run_scenario
from .world import ROOT

INPUTS = ["scenario.toml", "config/*.toml", "authz/*.py", "tests/*.py"]
OUTPUTS = ["decisions.jsonl", "timeline.json", "timeline.md", "sweep.json", "sweep.md", "invariants.json", "expectations.json",
           "receipt.json", "transcript.txt", "facts.json"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def manifest(run_dir: Path) -> dict:
    files = sorted({p for pat in INPUTS for p in ROOT.glob(pat) if p.is_file()})
    policy = json.loads((run_dir / "facts.json").read_text())["policy_version"]
    return {"run": run_dir.name, "policy_version": policy, "python": platform.python_version(),
            "platform": f"{platform.system()} {platform.machine()}",
            "hashes": {str(p.relative_to(ROOT)): sha(p) for p in files}}


def chain(run_dir: Path) -> list[dict]:
    """Recompute every record's hash from decisions.jsonl alone, independently of the AuditLog class."""
    out, prev = [], "0" * 16
    for line in (run_dir / "decisions.jsonl").read_text().splitlines():
        r = json.loads(line)
        body = {k: v for k, v in r.items() if k != "hash"}
        h = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]
        out.append({"seq": r["seq"], "time": r["time"], "kind": r["kind"], "hash": r["hash"], "prev": r["prev"],
                    "prev_ok": r["prev"] == prev, "hash_ok": h == r["hash"]})
        prev = r["hash"]
    return out


def replay(run_dir: Path) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / run_dir.name  # same directory name, so facts.json's run_id matches too
        run_scenario(fresh)
        return [{"file": f, "same": (fresh / f).exists() and (run_dir / f).exists()
                 and (fresh / f).read_bytes() == (run_dir / f).read_bytes()} for f in OUTPUTS]


def verify(run_dir: Path) -> dict:
    invariants = check_all()
    tests = record_tests.record(run_dir)
    again = record_tests.run_suite()
    ch = chain(run_dir)
    files = replay(run_dir)
    inv_ok = sum(i["passed"] for i in invariants)
    replay_ok = all(f["same"] for f in files)
    chain_ok = all(c["prev_ok"] and c["hash_ok"] for c in ch)
    deterministic = replay_ok and tests["results"] == again["results"]
    summary = {
        "run": run_dir.name,
        "policy_version": json.loads((run_dir / "facts.json").read_text())["policy_version"],
        "invariants": {"total": len(invariants), "passed": inv_ok, "failed": len(invariants) - inv_ok},
        "tests": {layer: {"passed": v["passed"], "failed": v["failed"]} for layer, v in tests["layers"].items()},
        "integration": "PASS" if tests["layers"]["L3"]["failed"] == 0 else "FAIL",
        "replay": "PASS" if replay_ok else "FAIL",
        "audit_chain": "PASS" if chain_ok else "FAIL",
        "deterministic": deterministic,
    }
    summary["ok"] = (inv_ok == len(invariants) and tests["ok"] and replay_ok and chain_ok and deterministic)
    detail = {
        "invariants": [{"id": i["id"], "name": i["name"], "passed": i["passed"], "cases": len(i["cases"])} for i in invariants],
        "replay": files, "chain": ch,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest(run_dir), indent=2) + "\n")
    (run_dir / "verification.json").write_text(json.dumps({"summary": summary, **detail}, indent=2) + "\n")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=str(ROOT / "runs" / RUN_ID))
    summary = verify(Path(ap.parse_args().run))
    print(json.dumps(summary, indent=2))
    sys.exit(0 if summary["ok"] else 1)


if __name__ == "__main__":
    main()
