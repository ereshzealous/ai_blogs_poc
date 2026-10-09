"""The proof pack's fact registry (pae-proof/v1): every fact a check in proof/experiments.toml compares, with its source.

    collect(run_id) -> (Facts, data)

  the run's facts.json                 every scenario, mutant, model-change and model-slice measure
  docs/derived-facts.json              tests, replay, run id, historical results of earlier packages
  raw evidence, recomputed here        duplicates from the provider ledgers, canary hits in every telemetry file,
                                       the preregistration hash check
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "recovery_poc"
sys.path.insert(0, str(ROOT / "vendor" / "kit5"))
sys.path.insert(0, str(POC))
from evidence_kit.facts import Facts  # noqa: E402  (5.2.0, vendor/kit5)

from recovery.common import prereg_check, scenarios, world_config  # noqa: E402


def collect(run_id: str) -> tuple[Facts, dict]:
    run = POC / "runs" / run_id
    base = f"recovery_poc/runs/{run_id}"
    F = Facts()
    for k, f in json.loads((run / "facts.json").read_text()).items():
        F.add(k, f["value"], source=f"{base}/facts.json ← {f['source']}", derivation=f.get("derivation"))
    dp = ROOT / "docs" / "derived-facts.json"
    for k, f in (json.loads(dp.read_text()).items() if dp.exists() else []):
        if k not in F:
            F.add(k, f["value"], source=f["source"], derivation=f.get("derivation"))

    # ---- recomputed from the raw ledgers: duplicates per runtime --------------------------------------------------------
    for arm in ("A0", "A1", "A2"):
        dups = []
        for s in scenarios():
            led = json.loads((run / "scenarios" / s["id"] / arm / "world" / "ledger.json").read_text())
            credits = max(Counter(c["charge_id"] for c in led["credits"]).values(), default=0)
            tickets = Counter(t["case_id"] for t in led["tickets"] if t["status"] == "OPEN")
            msgs = Counter(m["case_id"] for m in led["notifications"])
            if credits > 1 or max(tickets.values(), default=0) > 1 or max(msgs.values(), default=0) > 1:
                dups.append(s["id"])
        F.add(f"raw.{arm}.dup_scenarios", len(dups), source=f"{base}/scenarios/*/{arm}/world/ledger.json",
              derivation="scenarios whose provider ledgers hold more than one credit per charge, open ticket or message per case")

    # ---- canaries in every telemetry, event and journal file of the run ------------------------------------------------
    cfg = world_config()
    canaries = [cfg["provider_token"]] + [c["email"] for c in cfg["customers"]] + [c["card"] for c in cfg["customers"]] + \
               [c["card"].replace(" ", "") for c in cfg["customers"]]
    files = [p for p in run.rglob("*") if p.is_file() and (p.name in ("events.jsonl", "journal.json", "spans.jsonl"))]
    hits = sum(p.read_text().count(c) for p in files for c in canaries)
    F.add("raw.canary_hits", hits, source=f"{base}/**/{{events.jsonl,journal.json,telemetry/spans.jsonl}}",
          derivation=f"occurrences of {len(canaries)} planted values in {len(files)} files")
    F.add("raw.telemetry_files_scanned", len(files), source=f"{base}/**")
    F.add("raw.prereg_changed", len(prereg_check()), source="recovery_poc/experiments/FROZEN.sha256",
          derivation="frozen files whose sha256 differs from the freeze")
    data = {"manifest": json.loads((run / "manifest.json").read_text())}
    return F, data
