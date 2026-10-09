"""The proof pack's fact registry (pae-proof/v1): every fact a check in proof/experiments.toml compares, with its source.

    collect(run_id) -> (Facts, data)

  the run's facts.json                 every scenario's measures, aggregated from the run's raw files
  docs/derived-facts.json              tests, replay, proof counts
  recomputed here, from raw rows       work in system and running attempts swept from row intervals (cross-checks of the
                                       platform's own counters), the preregistration hash check, and comparison facts
                                       the checks need (proof.*)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "ops_poc"
sys.path.insert(0, str(ROOT / "vendor" / "kit5"))
sys.path.insert(0, str(POC))
from evidence_kit.facts import Facts  # noqa: E402  (5.2.0, vendor/kit5)

from agentops.common import prereg_check  # noqa: E402


def sweep(rows: list[dict], start: str) -> int:
    """Maximum overlap of [row[start], end_ms) intervals; at equal times an end is counted before a start."""
    ev = []
    for r in rows:
        if r.get(start) is None or r.get("end_ms") is None or r.get("admission_result") != "ADMITTED":
            continue
        ev.append((r[start], 1))
        ev.append((r["end_ms"], 0))
    cur = best = 0
    for _, kind in sorted(ev):
        cur += 1 if kind else -1
        best = max(best, cur)
    return best


def collect(run_id: str) -> tuple[Facts, dict]:
    run = POC / "runs" / run_id
    base = f"ops_poc/runs/{run_id}"
    F = Facts()
    facts = json.loads((run / "facts.json").read_text())
    for k, f in facts.items():
        F.add(k, f["value"], source=f"{base}/{f['source']}", derivation=f.get("derivation"))
    dp = ROOT / "docs" / "derived-facts.json"
    for k, f in (json.loads(dp.read_text()).items() if dp.exists() else []):
        if k not in F:
            F.add(k, f["value"], source=f["source"], derivation=f.get("derivation"))
    for scn, key, start in (("E1", "max_work_in_system", "arrival_ms"), ("E3", "max_active", "start_ms")):
        p = run / "scenarios" / scn / "controlled" / "rows.jsonl"
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        F.add(f"raw.{scn.lower()}.controlled.{key}", sweep(rows, start), source=f"{base}/scenarios/{scn}/controlled/rows.jsonl",
              derivation=f"maximum overlap of [{start}, end_ms) over admitted attempts, recomputed from the raw rows")
    v = lambda k: facts[k]["value"]  # noqa: E731
    F.add("proof.e5.success_gap_pp", round(v("e5.routed.success_pct") - v("e5.all-large.success_pct"), 1),
          source=f"{base}/facts.json", derivation="routed success % - all-large success %")
    F.add("proof.e9.blocked_set", ", ".join(v("e9.blocked")), source=f"{base}/facts.json")
    F.add("proof.e9.passed_set", ", ".join(v("e9.passed")), source=f"{base}/facts.json")
    F.add("raw.prereg_changed", len(prereg_check()), source="ops_poc/experiments/FROZEN.sha256",
          derivation="frozen files whose sha256 differs from the freeze")
    return F, {"manifest": json.loads((run / "manifest.json").read_text())}
