"""lineage: the T5 POC command line.

    lineage run record [--run-id ID] [--only a,b]     every scenario, live model, tapes recorded (needs Ollama + qwen3:8b)
    lineage run replay <run-id>                        every scenario again, model answers from that run's tapes (no model)
    lineage run smoke [--only a,b]                     into runs/_smoke, tapes from the published run (no model)
    lineage drift record|replay --run-id <run-id>      the D1 drift probe
    lineage verify-evidence [run-id] [scenario]        recompute every hash chain and check it against the witness anchors
    lineage inspect <scenario> [run-id]                the target execution, event by event, and what each layer could answer
    lineage demo                                       the flagship scenario (lost response) from the published run's tape
"""

from __future__ import annotations

import json
import subprocess
import sys

from .common import POC, jl
from .evidence import verify

RUNS = POC / "runs"


def published() -> str:
    return (RUNS / "PUBLISHED").read_text().strip()


def verify_evidence(run: str, only: str | None) -> int:
    bad = 0
    for s in sorted((RUNS / run / "scenarios").iterdir()):
        if only and s.name != only:
            continue
        v = verify(jl(s / "evidence" / "audit-events.jsonl"), jl(s / "witness" / "anchors.jsonl"))
        bad += not v["intact"]
        print(f"{s.name:30s} events={v['events']:3d} anchors={v['anchors']} chain={'ok' if v['chain_ok'] else 'BROKEN'} "
              f"anchors={'ok' if v['anchors_ok'] else 'MISMATCH'} {v['first_problem'] or ''}")
    return 1 if bad else 0


def inspect(scenario: str, run: str) -> None:
    from .aggregate import summarize, target_events_all
    s = RUNS / run / "scenarios" / scenario
    rows = target_events_all(s)
    t0 = rows[0]["occurred_at"]
    print(f"{scenario} · run {run} · execution {rows[0]['execution_id']} · trace {rows[0]['trace_id']}\n")
    for r in rows:
        print(f"  {r['occurred_at'][11:23]}  {r['event_type']:20s} {r['attempt_id'] or r['action_id'] or '':16s} {summarize(r)}")
    rec = json.loads((s / "reconstruction.json").read_text())
    print(f"\n  first event {t0}; verdicts per layer (✓ correct, ~ partial, - not recorded, X wrong):")
    mark = {"CORRECT": "✓", "INCOMPLETE": "~", "UNANSWERABLE": "-", "WRONG": "X", "AMBIGUOUS": "?"}
    print("        " + " ".join(f"{q:>4s}" for q in rec["L0"]["answers"]))
    for L in ("L0", "L1", "L2"):
        print(f"  {L}    " + " ".join(f"{mark[a['verdict']]:>4s}" for a in rec[L]["answers"].values()))


def main() -> None:
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd, rest = a[0], a[1:]
    if cmd == "run":
        sys.exit(subprocess.call([sys.executable, "-m", "lineage.run", *rest], cwd=POC))
    if cmd == "drift":
        sys.exit(subprocess.call([sys.executable, "-m", "lineage.drift", *rest], cwd=POC))
    if cmd == "verify-evidence":
        sys.exit(verify_evidence(rest[0] if rest else published(), rest[1] if len(rest) > 1 else None))
    if cmd == "inspect":
        inspect(rest[0], rest[1] if len(rest) > 1 else published())
        return
    if cmd == "demo":
        rc = subprocess.call([sys.executable, "-m", "lineage.run", "smoke", "--only", "e12a-lost-response"], cwd=POC)
        if rc == 0:
            inspect("e12a-lost-response", "_smoke")
        sys.exit(rc)
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
