"""docs/derived-facts.json: facts the documents print that are not in the run's facts.json.  Computed, never typed.

    python3 tools/derive_facts.py [tests]        (tests: run the POC's pytest first and record the counts)

  hist.*     HISTORICAL results of earlier packages, read from their own recorded facts (never re-measured here)
  tests.*    the POC's unit and end-to-end tests (verification/pytest.junit.xml)
  proof.*    the pae-proof/v1 pack's counts (evidence/runs/<run>/results.json), once tools/proof_pack.py has written it
  replay.*   the replay record (evidence/runs/<run>/replay.json)
  run.id     the published run
"""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT.parent
POC = ROOT / "recovery_poc"
RUN = (POC / "runs" / "PUBLISHED").read_text().strip()
LIVE = "2026-10-07-live"         # the real-model end-to-end run (python -m recovery.run record-live)

HIST = [  # key, file (relative to the series root), fact key in that file, label
    ("hist.f2.e4_monolith", "f2_layer_architecture/layered_architecture_poc/runs/2026-09-28-recorded/facts.json", "headline.e4_duplicate_rollbacks.monolith"),
    ("hist.f2.e4_layered", "f2_layer_architecture/layered_architecture_poc/runs/2026-09-28-recorded/facts.json", "headline.e4_duplicate_rollbacks.layered"),
    ("hist.t5.e12a_mutations", "governance_for_ai_agents/observability_governance_poc/runs/2026-09-30-recorded/facts.json", "e12a_mutations"),
    ("hist.t5.e12b_mutations", "governance_for_ai_agents/observability_governance_poc/runs/2026-09-30-recorded/facts.json", "e12b_mutations"),
    ("hist.t5.e05b_mutations", "governance_for_ai_agents/observability_governance_poc/runs/2026-09-30-recorded/facts.json", "e05b_mutations"),
    ("hist.p1.r10_naive", "ai_architecture/docs/facts.json", "obs.R10.naive"),
]


def tests() -> dict:
    out = ROOT / "verification"
    out.mkdir(exist_ok=True)
    p = subprocess.run(["uv", "run", "--project", str(POC), "pytest", f"--junitxml={out / 'pytest.junit.xml'}", "-q"], cwd=POC, capture_output=True, text=True)
    (out / "pytest.txt").write_text(p.stdout[-4000:])
    return junit()


def junit() -> dict:
    x = ROOT / "verification" / "pytest.junit.xml"
    if not x.exists():
        return {}
    s = ET.parse(x).getroot()
    s = s if s.tag == "testsuite" else s.find("testsuite")
    total, fail, err, skip = (int(s.get(k, 0)) for k in ("tests", "failures", "errors", "skipped"))
    src = "verification/pytest.junit.xml"
    e2e = sum(1 for c in s.iter("testcase") if "test_scenarios" in c.get("classname", ""))
    return {"tests.total": {"value": total, "source": src}, "tests.passed": {"value": total - fail - err - skip, "source": src},
            "tests.e2e": {"value": e2e, "source": src, "derivation": "end-to-end tests through real worker processes (tests/test_scenarios.py)"},
            "tests.unit": {"value": total - e2e, "source": src}}


def main() -> None:
    out = {"run.id": {"value": RUN, "source": "recovery_poc/runs/PUBLISHED"}}
    prev = ROOT / "docs" / "derived-facts.json"
    old = json.loads(prev.read_text()) if prev.exists() else {}
    for key, f, fk in HIST:
        if (WS / f).exists():
            v = json.loads((WS / f).read_text())[fk]
            out[key] = {"value": v["value"], "source": f"../{f} → {fk}", "derivation": "HISTORICAL: an earlier package's recorded result, not re-measured"}
        elif key in old:            # a standalone copy of this chapter (the public repository): the earlier chapter is not
            out[key] = old[key]     # beside it, so the value derived from it in the author's workspace is kept as it was
        else:
            raise SystemExit(f"{f}: not found, and docs/derived-facts.json has no earlier value for {key}")
    out.update(tests() if "tests" in sys.argv[1:] else junit())
    pack = ROOT / "evidence" / "runs" / RUN
    if (pack / "results.json").exists():
        res = json.loads((pack / "results.json").read_text())
        c, fc = res["check_counts"], res["finding_counts"]
        src = f"evidence/runs/{RUN}/results.json"
        for k in ("experiments", "checks", "pass", "fail", "expected_failure"):
            out[f"proof.{k}"] = {"value": c[k], "source": src + " → check_counts"}
        out["proof.claims"] = {"value": len(res["claims"]), "source": src + " → claims"}
        out["proof.not_supported"] = {"value": fc.get("NOT SUPPORTED", 0), "source": src + " → finding_counts"}
    if (pack / "replay.json").exists():
        rp = json.loads((pack / "replay.json").read_text())
        src = f"evidence/runs/{RUN}/replay.json"
        out["replay.level"] = {"value": rp["replay_level"], "source": src}
        out["replay.files"] = {"value": rp["files"], "source": src}
        out["replay.identical"] = {"value": rp["classes"]["DETERMINISTIC_EQUIVALENT"], "source": src}
        out["replay.different"] = {"value": rp["classes"]["REGRESSION"] + rp["classes"]["METHODOLOGY_CHANGE"], "source": src}
    sys.path.insert(0, str(ROOT / "tools"))
    from proof_facts import collect                 # the raw recomputations (duplicates from ledgers, canaries, freeze)
    F, _ = collect(RUN)
    for k in ("raw.A0.dup_scenarios", "raw.A1.dup_scenarios", "raw.A2.dup_scenarios", "raw.canary_hits", "raw.telemetry_files_scanned", "raw.prereg_changed"):
        f = F.to_json()[k]
        out[k] = {"value": f["value"], "source": f["source"], "derivation": f.get("derivation")}
    if (pack / "results.json").exists():
        out["proof.limitation"] = {"value": json.loads((pack / "results.json").read_text())["finding_counts"].get("LIMITATION OBSERVED", 0),
                                   "source": f"evidence/runs/{RUN}/results.json → finding_counts"}
    live = POC / "runs" / LIVE
    if (live / "facts.json").exists():      # the real-model end-to-end run: its own facts, under live.*
        for k, f in json.loads((live / "facts.json").read_text()).items():
            out[f"live.{k}"] = {"value": f["value"], "source": f"recovery_poc/runs/{LIVE}/facts.json ← {f['source']}", "derivation": f.get("derivation")}
        lr = ROOT / "evidence" / "runs" / LIVE / "replay.json"
        if lr.exists():
            rp = json.loads(lr.read_text())
            out["live.replay.files"] = {"value": rp["files"], "source": f"evidence/runs/{LIVE}/replay.json"}
            out["live.replay.different"] = {"value": rp["classes"]["REGRESSION"], "source": f"evidence/runs/{LIVE}/replay.json"}
        out["live.run.id"] = {"value": LIVE, "source": f"recovery_poc/runs/{LIVE}"}
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "derived-facts.json").write_text(json.dumps(dict(sorted(out.items())), indent=1, ensure_ascii=False) + "\n")
    print(f"docs/derived-facts.json: {len(out)} facts")


if __name__ == "__main__":
    main()
