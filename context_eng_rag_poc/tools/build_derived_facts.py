"""Derive docs/derived-facts.json from the published run's post-hoc outputs, never from typed numbers.

    python3 tools/build_derived_facts.py

Reads enterprise_knowledge_rag_poc/runs/<PUBLISHED>-exploratory/ (written by `python -m s2_eval.exploratory <run>` and
`... <run> --typography`): the assembler variants v2/v3 on experiment C's admitted pools and the typography re-score of the
recorded answers. Every key is prefixed `x.` so a reader of the editions can tell a post-hoc number from a preregistered one,
and every source names the file it came from. build_docs.py refuses a key defined both here and in facts.json.

It also reads the outputs of `make verify` in verification/ (tests, replay, freeze check, independent evidence check), so
the editions and the QA record quote those results as facts too: keys `tests.*`, `replay.*`, `frozen.*`, `evcheck.*`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POC = ROOT / "enterprise_knowledge_rag_poc"


def main() -> None:
    run = (POC / "runs" / "PUBLISHED").read_text().strip()
    xdir = POC / "runs" / f"{run}-exploratory"
    out: dict[str, dict] = {}

    def put(key: str, value, source: str) -> None:
        out[key] = {"value": value, "source": source}

    summ = xdir / "summary.json"
    if not summ.exists():
        sys.exit(f"missing {summ.relative_to(ROOT)}: run `uv run python -m s2_eval.exploratory {run}` first")
    s = json.loads(summ.read_text())
    src = f"runs/{run}-exploratory/summary.json (POST-HOC, EXPLORATORY)"
    for key, m in s["budgets"].items():
        budget, method = key.split(".", 1)
        v = method.replace("assembler-", "")
        for k in ("needed_covered", "qual_cases_ok", "cases_all_needed", "needed_in_pool", "qual_cases"):
            put(f"x.c.{budget}.{v}.{k}", m[k], src)

    typo = xdir / "d_rescore_typography.json"
    if not typo.exists():
        sys.exit(f"missing {typo.relative_to(ROOT)}: run `uv run python -m s2_eval.exploratory {run} --typography` first")
    t = json.loads(typo.read_text())
    src = f"runs/{run}-exploratory/d_rescore_typography.json (POST-HOC, EXPLORATORY)"
    prefix = {"d.jsonl": "d", "d_sensitivity.jsonl": "ds", "e_live.jsonl": "el"}
    for fname, body in t["files"].items():
        p = prefix[fname]
        for arm, m in body["arms"].items():
            for k, v in m.items():
                put(f"x.typo.{p}.{arm}.{k}", v, src)
        put(f"x.typo.{p}.changed_rows", len(body["changed_rows"]), src)

    import re
    import xml.etree.ElementTree as ET
    V = ROOT / "verification"
    junit = V / "pytest.junit.xml"
    if junit.exists():
        suite = ET.parse(junit).getroot().find("testsuite")
        src = "verification/pytest.junit.xml (make test)"
        total, bad = int(suite.get("tests")), int(suite.get("failures")) + int(suite.get("errors"))
        put("tests.total", total, src)
        put("tests.passed", total - bad - int(suite.get("skipped")), src)
        put("tests.failed", bad, src)
        files: dict[str, int] = {}
        for tc in suite.iter("testcase"):
            files[tc.get("classname").split(".")[-1]] = files.get(tc.get("classname").split(".")[-1], 0) + 1
        for f, n in files.items():
            put(f"tests.file.{f}", n, src)
        put("tests.files", len(files), src)
    rp = V / "replay-check.txt"
    if rp.exists():
        r = json.loads(rp.read_text())
        src = "verification/replay-check.txt (make replay)"
        put("replay.verdict", r["verdict"], src)
        put("replay.identical", len(r["identical"]), src)
        put("replay.different", len(r["different"]), src)
        put("replay.model_calls_from_tape", r["model_calls_from_tape"], src)
    fc = V / "frozen-check.txt"
    if fc.exists():
        m = re.search(r"(\d+) of (\d+) files unchanged", fc.read_text())
        put("frozen.unchanged", int(m.group(1)), "verification/frozen-check.txt (make freeze-check)")
        put("frozen.files", int(m.group(2)), "verification/frozen-check.txt (make freeze-check)")
    ev = V / "evidence-check.txt"
    if ev.exists():
        m = re.search(r"EVIDENCE CHECK: (\d+) pass, (\d+) fail, (\d+) skip", ev.read_text())
        src = "verification/evidence-check.txt (s2_eval.verify_evidence)"
        put("evcheck.pass", int(m.group(1)), src)
        put("evcheck.fail", int(m.group(2)), src)
        put("evcheck.total", int(m.group(1)) + int(m.group(2)) + int(m.group(3)), src)

    (ROOT / "docs" / "derived-facts.json").write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"{len(out)} derived facts -> docs/derived-facts.json")


if __name__ == "__main__":
    main()
