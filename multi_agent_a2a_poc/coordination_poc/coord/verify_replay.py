"""Compare a recorded run with its tape replay (no model): same decisions, same ledgers, same evaluation.

    python -m coord.bench matrix --run-id <run> --fixtures ... --archs ... --repeats N --tape replay
    python -m coord.verify_replay <run>

Compared per workflow: success and every conjunct, outcome, termination, root-cause category, the ordered list of
gateway calls (capability + canonical args + effect + outcome), executed writes, model calls and tokens, handoffs,
duplicate tool calls.  Wall-clock times, A2A task ids, pids and token ids are volatile by nature and not compared.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from coord.util import ROOT

KEYS_EVAL = ["success", "rc_ok", "evidence_ok", "remediation_ok", "prohibited_ok", "approval_ok", "outcome_ok", "category", "outcome",
             "executed_writes", "world_executions"]
KEYS_METRICS = ["llm_calls", "tokens_in", "tokens_out", "tool_calls", "duplicate_tool_calls", "handoffs", "termination", "state_conflicts"]


def calls(db: Path, wf: str) -> list[list]:
    con = sqlite3.connect(db)
    out = [list(r) for r in con.execute("SELECT capability, args, effect, outcome, evidence_ref, component FROM gateway_calls WHERE workflow_id=? ORDER BY seq", (wf,))]
    con.close()
    return out


def main(argv: list[str] | None = None) -> None:
    run = (argv or sys.argv[1:])[0]
    rd = ROOT / "runs" / run
    rec = {r["workflow_id"]: r for r in map(json.loads, (rd / "rows.jsonl").read_text().splitlines())}
    rep = {r["workflow_id"]: r for r in map(json.loads, (rd / "replay" / "rows.jsonl").read_text().splitlines())}
    diffs, checked = [], 0
    for wf, a in rec.items():
        b = rep.get(wf)
        if b is None:
            diffs.append(f"{wf}: missing in replay")
            continue
        checked += 1
        for k in KEYS_EVAL:
            if a["eval"][k] != b["eval"][k]:
                diffs.append(f"{wf}: eval.{k} {a['eval'][k]!r} != {b['eval'][k]!r}")
        for k in KEYS_METRICS:
            if a["metrics"][k] != b["metrics"][k]:
                diffs.append(f"{wf}: metrics.{k} {a['metrics'][k]!r} != {b['metrics'][k]!r}")
        if calls(rd / "session" / "platform.db", wf) != calls(rd / "replay" / "session" / "platform.db", wf):
            diffs.append(f"{wf}: gateway call sequence differs")
    report = {"run": run, "workflows_recorded": len(rec), "workflows_compared": checked, "differences": diffs,
              "verdict": "REPLAY IDENTICAL" if not diffs and checked == len(rec) else "REPLAY DIFFERS"}
    (rd / "replay" / "verification.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "differences"}), *diffs[:20], sep="\n")
    sys.exit(0 if report["verdict"] == "REPLAY IDENTICAL" else 1)


if __name__ == "__main__":
    main()
