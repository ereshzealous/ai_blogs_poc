#!/usr/bin/env python3
"""Four test numbers that must never be substituted for one another.

    python3 tools/test_accounting.py            -> verification/test_accounting.{json,md}

Section 27 of the standardization brief: a reader who clones the repository today runs a different suite from the one
that ran with the recorded run, and both numbers are true. Reporting only the larger one would overstate the
evidence; reporting only the historical one would understate the repository. So all four are reported separately:

    DURING THE CITED RUN      the suite as it was when the run was recorded, from that run's own JUnit file
    CURRENT REPOSITORY SUITE  pytest now, in this working tree
    POST-RUN EVIDENCE TESTS   tests that read the finished run; they can only pass after it exists
    RUN VERIFIER              the integrity and recomputation checks in that run's verification.json
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
POC = HERE / "layered_architecture_poc"
OUT = HERE / "verification"


def published_run() -> Path:
    return POC / "runs" / (POC / "runs" / "PUBLISHED").read_text().strip()


def from_junit(path: Path) -> dict:
    if not path.exists():
        return {"available": False}
    cases = list(ET.parse(path).getroot().iter("testcase"))
    failed = sum(1 for c in cases if c.find("failure") is not None or c.find("error") is not None)
    skipped = sum(1 for c in cases if c.find("skipped") is not None)
    by_category: dict[str, int] = {}
    for case in cases:
        part = (case.get("classname") or "").split(".")
        category = part[1] if len(part) > 1 and part[0] == "tests" else "other"
        by_category[category] = by_category.get(category, 0) + 1
    return {"available": True, "cases": len(cases), "passed": len(cases) - failed - skipped,
            "failed": failed, "skipped": skipped, "by_category": dict(sorted(by_category.items()))}


def current_suite() -> dict:
    """Run the suite now, excluding the tests that need a local model."""
    junit = OUT / "current_suite.junit.xml"
    OUT.mkdir(exist_ok=True)
    proc = subprocess.run(["uv", "run", "pytest", "-m", "not model", "-q", "-p", "no:cacheprovider",
                           "--junitxml", str(junit)], cwd=POC, capture_output=True, text=True)
    result = from_junit(junit)
    result["returncode"] = proc.returncode
    # how many tests the exclusion left out, counted by collecting them on their own
    collected = subprocess.run(["uv", "run", "pytest", "-m", "model", "--collect-only", "-q", "-p", "no:cacheprovider"],
                               cwd=POC, capture_output=True, text=True).stdout
    # `pytest --collect-only -q` prints one "<file>: <n>" line per file
    result["model_tests_excluded"] = sum(int(m.group(1)) for m in re.finditer(r":\s*(\d+)\s*$", collected, re.M))
    return result


def post_run_tests() -> dict:
    """The evidence tests, which read the published run. They are meaningless before it exists."""
    junit = OUT / "post_run.junit.xml"
    proc = subprocess.run(["uv", "run", "pytest", "tests/evidence", "tests/architecture", "-q", "-p", "no:cacheprovider",
                           "--junitxml", str(junit)], cwd=POC, capture_output=True, text=True)
    result = from_junit(junit)
    result["returncode"] = proc.returncode
    return result


def verifier() -> dict:
    path = published_run() / "verification.json"
    if not path.exists():
        return {"available": False}
    data = json.loads(path.read_text())
    return {"available": True, "passed": data["passed"], "failed": data.get("failed", 0),
            "not_applicable": data.get("not_applicable", 0), "total": data["total"],
            "recomputed": data.get("recomputed", 0), "ok": data["ok"]}


def main() -> int:
    run = published_run()
    report = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cited_run": run.name,
        "during_the_cited_run": from_junit(run / "tests.junit.xml"),
        "current_repository_suite": current_suite(),
        "post_run_evidence_tests": post_run_tests(),
        "run_verifier": verifier(),
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "test_accounting.json").write_text(json.dumps(report, indent=1))

    during, now_, post, ver = (report["during_the_cited_run"], report["current_repository_suite"],
                               report["post_run_evidence_tests"], report["run_verifier"])
    lines = [
        "# Test accounting",
        "",
        f"Four numbers, reported separately so none can stand in for another. Cited run `{run.name}`; "
        f"generated {report['generated']}.",
        "",
        "| What | Passed | Failed | Skipped | Cases |",
        "|---|---|---|---|---|",
        f"| During the cited run | {during.get('passed')} | {during.get('failed')} | {during.get('skipped')} | {during.get('cases')} |",
        f"| Current repository suite | {now_.get('passed')} | {now_.get('failed')} | {now_.get('skipped')} | {now_.get('cases')} |",
        f"| Post-run evidence tests | {post.get('passed')} | {post.get('failed')} | {post.get('skipped')} | {post.get('cases')} |",
        f"| Run verifier | {ver.get('passed')} | {ver.get('failed')} | {ver.get('not_applicable')} (n/a) | {ver.get('total')} |",
        "",
        f"- The cited run's suite is read from `runs/{run.name}/tests.junit.xml`; it is historical and never rewritten.",
        f"- The current suite grew by {(now_.get('cases') or 0) - (during.get('cases') or 0)} case(s) since that run, "
        "mostly architecture and evidence tests added by the standardization pass. The article must cite the cited "
        "run's number where it describes the run.",
        f"- {now_.get('model_tests_excluded', 0)} test(s) need a local model and are excluded from the current count.",
        f"- The run verifier recomputed {ver.get('recomputed')} of its {ver.get('total')} checks from raw evidence.",
    ]
    (OUT / "test_accounting.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[4:]))
    return 0 if (now_.get("failed") == 0 and post.get("failed") == 0 and ver.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
