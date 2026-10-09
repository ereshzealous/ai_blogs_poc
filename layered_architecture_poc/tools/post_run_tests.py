"""Run the post-run evidence tests (tests/evidence) against the frozen published run and record the outcome.

    python3 tools/post_run_tests.py      -> verification/post_run_evidence_tests.{json,txt,junit.xml}

These four tests check the published run itself, so they skip at record time (the run does not exist yet) and are
run here, afterwards, without touching the run.
"""
import json
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "layered_architecture_poc"
OUT = ROOT / "verification"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    junit = OUT / "post_run_evidence_tests.junit.xml"
    p = subprocess.run(["uv", "run", "pytest", "tests/evidence", "-v", "-rA", f"--junitxml={junit}"], cwd=POC, capture_output=True, text=True)
    (OUT / "post_run_evidence_tests.txt").write_text(p.stdout + p.stderr)
    cases = []
    for tc in ET.parse(junit).getroot().iter("testcase"):
        status = "failed" if tc.find("failure") is not None or tc.find("error") is not None else "skipped" if tc.find("skipped") is not None else "passed"
        cases.append({"test": f"{tc.get('classname')}::{tc.get('name')}", "status": status})
    run = (POC / "runs" / "PUBLISHED").read_text().strip()
    out = {"run": run, "ran_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "total": len(cases),
           "passed": sum(c["status"] == "passed" for c in cases), "failed": sum(c["status"] == "failed" for c in cases),
           "skipped": sum(c["status"] == "skipped" for c in cases), "returncode": p.returncode, "tests": cases}
    (OUT / "post_run_evidence_tests.json").write_text(json.dumps(out, indent=1))
    print(f"{out['passed']}/{out['total']} passed, {out['failed']} failed, {out['skipped']} skipped")


if __name__ == "__main__":
    main()
