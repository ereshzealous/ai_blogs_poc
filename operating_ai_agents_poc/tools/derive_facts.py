"""docs/derived-facts.json: facts the documents print that are not in the run's facts.json. Computed, never typed.

    python3 tools/derive_facts.py [tests]        (tests: run the POC's pytest first and record the counts)

  tests.*    the POC's tests (verification/pytest.junit.xml): ten scenario tests, the unit tests
  proof.*    the pae-proof/v1 pack's counts (evidence/runs/<run>/results.json), once tools/proof_pack.py has written it
  replay.*   the replay record (evidence/runs/<run>/replay.json)
  sources.*  the research file (research/sources.md)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "ops_poc"
RUN = (POC / "runs" / "PUBLISHED").read_text().strip()


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
    scen = [c for c in s.iter("testcase") if "test_scenarios" in c.get("classname", "")]
    scen_pass = sum(1 for c in scen if not list(c))
    return {"tests.total": {"value": total, "source": src}, "tests.passed": {"value": total - fail - err - skip, "source": src},
            "tests.scenarios": {"value": len(scen), "source": src, "derivation": "tests/test_scenarios.py: one per claim"},
            "tests.scenarios_passed": {"value": scen_pass, "source": src},
            "tests.unit": {"value": total - len(scen), "source": src}}


def main() -> None:
    out = {}
    out.update(tests() if "tests" in sys.argv[1:] else junit())
    pack = ROOT / "evidence" / "runs" / RUN
    if (pack / "results.json").exists():
        res = json.loads((pack / "results.json").read_text())
        c, fc = res["check_counts"], res["finding_counts"]
        src = f"evidence/runs/{RUN}/results.json"
        for k in ("experiments", "checks", "pass", "fail", "expected_failure"):
            out[f"proof.{k}"] = {"value": c[k], "source": src + " → check_counts"}
        out["proof.claims"] = {"value": len(res["claims"]), "source": src + " → claims"}
        out["proof.limitation"] = {"value": fc.get("LIMITATION OBSERVED", 0), "source": src + " → finding_counts"}
        out["proof.not_supported"] = {"value": fc.get("NOT SUPPORTED", 0), "source": src + " → finding_counts"}
        sup = [x for x in res["claims"] if x.get("class") in ("SUPPORTED", "QUALIFIED")]
        out["proof.claims_tested"] = {"value": len(sup), "source": src + " → claims", "derivation": "SUPPORTED + QUALIFIED"}
        out["proof.claims_qualified"] = {"value": sum(x.get("class") == "QUALIFIED" for x in res["claims"]), "source": src + " → claims"}
    if (pack / "replay.json").exists():
        rp = json.loads((pack / "replay.json").read_text())
        src = f"evidence/runs/{RUN}/replay.json"
        out["replay.level"] = {"value": rp["replay_level"], "source": src}
        out["replay.files"] = {"value": rp["files"], "source": src}
        out["replay.identical"] = {"value": rp["classes"]["DETERMINISTIC_EQUIVALENT"], "source": src}
        out["replay.different"] = {"value": rp["classes"]["REGRESSION"] + rp["classes"]["METHODOLOGY_CHANGE"], "source": src}
    sys.path.insert(0, str(ROOT / "tools"))
    from proof_facts import collect                 # facts the proof pack recomputes from the raw run (raw.*, proof.e5/e9.*)
    F, _ = collect(RUN)
    for k, f in F.to_json().items():
        if k.startswith(("raw.", "proof.e5.", "proof.e9.")):
            out[k] = {"value": f["value"], "source": f["source"], "derivation": f.get("derivation")}
    for ev in sorted((POC / "runs" / RUN / "scenarios" / "E9" / "evals").glob("*.json")):
        v = json.loads(ev.read_text())["task_success"]
        out[f"e9.{ev.stem}.task_success_pct"] = {"value": round(100 * v, 1), "source": f"ops_poc/runs/{RUN}/scenarios/E9/evals/{ev.name}",
                                                 "derivation": "task success on the offline suite, as a percentage"}
    sp = ROOT / "research" / "sources.md"
    if sp.exists():
        n = len(re.findall(r"^\*\*\[(\d+)\]\*\* ", sp.read_text(), re.M))
        out["sources.n"] = {"value": n, "source": "research/sources.md", "derivation": "numbered, verified sources"}
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "derived-facts.json").write_text(json.dumps(dict(sorted(out.items())), indent=1, ensure_ascii=False) + "\n")
    print(f"docs/derived-facts.json: {len(out)} facts")


if __name__ == "__main__":
    main()
