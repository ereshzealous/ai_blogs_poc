"""After a scenario: snapshot the world, export and verify the evidence, build ground truth, score the three layers.

Outputs in the scenario directory:
  world/after.json, world/external-transactions.json    the deployment API's own records (ground truth for side effects)
  evidence/audit-events.jsonl, evidence/verification.json
  truth.json            answers to Q1–Q13 from the systems of record and the scenario pins (never from the layers under test)
  reconstruction.json   each layer's answers, how it got them, and whether each is right
  result.json           the scenario's headline numbers
"""

from __future__ import annotations

import json
from pathlib import Path

from .common import jl
from .deploysvc import snapshot
from .evidence import load_rows, verify


def collect(sdir: Path, spec: dict, life: list[dict], wall_s: float) -> dict:
    from .investigate import investigate_all
    from .truth import truth

    after = snapshot(sdir)
    (sdir / "world" / "after.json").write_text(json.dumps({k: after[k] for k in ("deployments", "revisions")}, indent=1))
    (sdir / "world" / "external-transactions.json").write_text(json.dumps(after["requests"], indent=1))
    (sdir / "evidence").mkdir(exist_ok=True)
    rows = load_rows(sdir / "state" / "evidence.db") if (sdir / "state" / "evidence.db").exists() else []
    with open(sdir / "evidence" / "audit-events.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    anchors = jl(sdir / "witness" / "anchors.jsonl")
    ver = verify(rows, anchors)
    (sdir / "evidence" / "verification.json").write_text(json.dumps(ver, indent=1))
    t = truth(sdir, spec, after, rows)
    (sdir / "truth.json").write_text(json.dumps(t, indent=1))
    recon = investigate_all(sdir, spec, t)
    (sdir / "reconstruction.json").write_text(json.dumps(recon, indent=1))
    score = {layer: {"correct": sum(1 for q in r["answers"].values() if q["verdict"] == "CORRECT"),
                     "verdicts": {q: a["verdict"] for q, a in r["answers"].items()},
                     "sources": r["sources"], "key_joins": r["key_joins"], "heuristic_joins": r["heuristic_joins"]}
             for layer, r in recon.items()}
    target_procs = [p for p in life if p["role"] == "target"]
    res = {"scenario": spec["scenario"], "outcome": t["Q12"]["detail"]["recorded_outcome"], "mitigated": t["Q12"]["value"],
           "mutations": t["Q11"]["value"], "attempts": t["Q9"]["value"], "processes": len(target_procs),
           "sigkills": sum(1 for p in target_procs if p["signal"]), "evidence_intact": ver["intact"], "evidence_events": ver["events"],
           "score": score, "wall_s": wall_s}
    (sdir / "result.json").write_text(json.dumps(res, indent=1))
    return res
