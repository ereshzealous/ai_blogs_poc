"""Reports are generated from recorded files alone: no model, no MCP server."""

from __future__ import annotations

import json
from pathlib import Path

from agent_platform.channels import html_report
from experiments import report

PUBLISHED = "2026-09-16"
RUN = Path(__file__).resolve().parents[1] / "runs" / PUBLISHED


def test_run_report_covers_every_recorded_stage(tmp_path):
    html_path = report.build(PUBLISHED, report_dir=tmp_path)
    page = html_path.read_text()
    for heading in ("At a glance", "Tests and layer contracts", "The platform, run by run", "Crash, checkpoint, resume",
                    "Timeouts and a lost write", "The monolith, same incident", "Requirement changes, twice each",
                    "Memory, knowledge and context", "Where the numbers come from"):
        assert heading in page
    assert str(Path.home()) not in page
    assert "<title>INC-4917 Run Report · 2026-09-16</title>" in page
    results = json.loads((tmp_path / "results.json").read_text())
    assert results["crash"]["backend_rollbacks"] == 1
    assert results["faults"]["rollback"]["backend_executions"] == 1
    assert results["monolith"]["lost_response_rollbacks"] == 2
    assert "## Platform runs" in (tmp_path / "summary.md").read_text()


def test_workflow_page_shows_the_whole_record():
    rec = json.loads(next((RUN / "workflow").glob("*/run1/record.json")).read_text())
    page = html_report.workflow_page(rec, "test")
    assert page.startswith("<!doctype html>")
    assert rec["workflow_id"] in page
    assert "Approval before the write" in page and "Trace tree" in page
    bare = html_report.page("t", "e", "h", "s", "", "<p>x</p>", bare=True)
    assert "<!doctype" not in bare and "<body>" not in bare and "<title>t</title>" in bare


def test_scrub_keeps_json_valid():
    home = str(Path.home())
    raw = json.dumps({"error": f'File "{home}/x/y.py", line 3\n  File "/private/tmp/run-1/z.py"', "path": "/var/folders/ab/T/q"})
    clean = html_report.scrub(raw)
    assert json.loads(clean) == {"error": 'File "~/x/y.py", line 3\n  File "<tmp>"', "path": "<tmp>"}
