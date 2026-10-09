"""s1: freeze, check, run (record | replay), report."""

from __future__ import annotations

import argparse
import json
import sys

from s1_experiments import freeze, report
from s1_experiments.scenario import ROOT


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="s1", description="S1 memory, context & state POC")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze", help="hash scenarios, policy, code and the preregistration into FROZEN.json")
    sub.add_parser("check", help="list frozen inputs that changed")
    r = sub.add_parser("run", help="run every experiment")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--record", metavar="RUN_ID", help="live Ollama, record all model traffic")
    g.add_argument("--replay", metavar="RUN_ID", help="replay a recorded run without a model server")
    r.add_argument("--allow-unfrozen", action="store_true", help="development only: run even if frozen inputs changed")
    rp = sub.add_parser("report", help="regenerate report.md from summary.json")
    rp.add_argument("run_id")
    a = ap.parse_args(argv)

    if a.cmd == "freeze":
        h = freeze.freeze()
        print(f"froze {len(h)} files · digest {freeze.digest(h)}")
    elif a.cmd == "check":
        changed = freeze.check()
        print("\n".join(changed) if changed else "unchanged")
        sys.exit(1 if changed else 0)
    elif a.cmd == "run":
        from s1_experiments.run import execute
        run_id, mode = (a.record, "record") if a.record else (a.replay, "replay")
        s = execute(run_id, mode, a.allow_unfrozen)
        out = ROOT / "runs" / run_id / ("replay" if mode == "replay" else "")
        (out / "report.md").write_text(report.render(s))
        print(f"\ninvariants {s['invariants_passed']}/{s['invariants_total']} · {out / 'summary.json'}")
        if mode == "replay":
            base = ROOT / "runs" / run_id
            skip = ("mode", "wall_seconds", "frozen_digest")
            rec = {k: v for k, v in json.loads((base / "summary.json").read_text()).items() if k not in skip}
            now = {k: v for k, v in json.loads(json.dumps(s, default=str)).items() if k not in skip}  # compare as JSON
            changed = freeze.definition_changes(json.loads((base / "hashes.json").read_text()))
            if changed:
                print("experiment-defining files changed since the recording:\n  " + "\n  ".join(changed))
            print("replay reproduces the recorded summary" if rec == now else "REPLAY DIFFERS from the recorded summary")
            sys.exit(0 if rec == now and not changed else 1)
    elif a.cmd == "report":
        s = json.loads((ROOT / "runs" / a.run_id / "summary.json").read_text())
        (ROOT / "runs" / a.run_id / "report.md").write_text(report.render(s))
