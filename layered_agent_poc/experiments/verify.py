"""verification.json: recompute a run's published numbers from its raw records and say whether they agree.

    uv run python -m experiments.verify --run-id 2026-09-17-recorded

facts.json is built from each experiment's summary file. This checks those summaries against the rows underneath
them: the databases the mock enterprise wrote, the audit log the gateway wrote, the spans the telemetry layer wrote,
and the per-run records. A check that cannot run (because an experiment is not in the run) is reported as skipped,
never as passed. The exit code is 0 only when every check that ran passed.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


def load(path: Path) -> Any:
    return json.loads(path.read_text()) if path.exists() else None


def rows(db: Path, sql: str) -> list[tuple]:
    if not db.exists():
        return []
    con = sqlite3.connect(db)
    return con.execute(sql).fetchall()


class Checks:
    def __init__(self) -> None:
        self.results: list[dict[str, Any]] = []

    def add(self, name: str, ok: bool | None, detail: str, evidence: str) -> None:
        """ok True passed, False failed, None the run has nothing to check."""
        self.results.append({"check": name, "status": "skip" if ok is None else "pass" if ok else "fail",
                             "detail": detail, "evidence": evidence})

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [r for r in self.results if r["status"] == "fail"]


def verify(base: Path) -> dict[str, Any]:
    c = Checks()
    facts = load(base / "facts.json")
    if facts is None:
        raise SystemExit(f"runs/{base.name} has no facts.json: run `experiments.facts --run-id {base.name}` first")

    # --- the platform's own runs: every eval and token count recomputed from each record ---
    plat = facts.get("platform")
    if not plat:
        c.add("platform runs", None, "the workflow experiment is not in this run", "")
    else:
        bad = []
        for model, s in plat.items():
            recs = [load(p) for p in sorted((base / "workflow" / model.replace(":", "_")).glob("run*/record.json"))]
            if len(recs) != s["runs"]:
                bad.append(f"{model}: {len(recs)} record(s) on disk, summary says {s['runs']}")
            if sum(r["status"] == "COMPLETED" for r in recs) != s["completed"]:
                bad.append(f"{model}: completed count does not match the records")
            if sum(bool(r["eval"]["ok"]) for r in recs) != s["all_checks_passed"]:
                bad.append(f"{model}: all-checks count does not match the records")
            for r in recs:
                passed = sum(1 for x in r["eval"]["checks"] if x["passed"])
                if r["eval"]["ok"] != (passed == r["eval"]["total"]):
                    bad.append(f"{model} {r['workflow_id']}: eval.ok disagrees with its own checks")
        c.add("platform runs", not bad, "; ".join(bad) or f"{sum(s['runs'] for s in plat.values())} records match their summary",
              "workflow/*/run*/record.json")

        # every run that claims a rollback has one execution in that run's own enterprise database
        bad = []
        for model in plat:
            for d in sorted((base / "workflow" / model.replace(":", "_")).glob("run*")):
                rec = load(d / "record.json")
                if rec is None:
                    continue
                n = len(rows(d / "enterprise.db", "SELECT 1 FROM executions WHERE tool='source_control.rollback_release'"))
                if n != rec["world"]["rollback_executions"]:
                    bad.append(f"{d.name}: database has {n}, record says {rec['world']['rollback_executions']}")
                if rec["status"] == "COMPLETED" and n != 1:
                    bad.append(f"{d.name}: completed with {n} rollback executions")
        c.add("writes land once", not bad, "; ".join(bad) or "each completed run executed exactly one rollback",
              "workflow/*/run*/enterprise.db · executions")

        # approvals: the digest the gateway verified is the digest a human decided on
        bad = []
        for model in plat:
            for d in sorted((base / "workflow" / model.replace(":", "_")).glob("run*")):
                rec = load(d / "record.json")
                if not rec or not (rec["view"].get("approval") or {}).get("id"):
                    continue
                ap = rec["view"]["approval"]
                verified = [a for a in rec["audit"] if a["event"] == "approval.verified"]
                if not verified:
                    bad.append(f"{d.name}: no approval.verified in the audit log")
                elif any(a.get("digest") != ap["digest"] for a in verified):
                    bad.append(f"{d.name}: the verified digest is not the approved digest")
                executed = [a for a in rec["audit"] if a["event"] == "invocation.executed"
                            and a.get("tool_id") == "source_control.rollback_release"]
                if executed and ap["status"] != "APPROVED":
                    bad.append(f"{d.name}: the rollback executed with approval status {ap['status']}")
        c.add("approval binds the write", not bad, "; ".join(bad) or "every rollback ran under its own approved digest",
              "workflow/*/run*/record.json · audit")

    # --- faults: the lost response is replayed, not executed twice ---
    f = facts.get("faults")
    if not f:
        c.add("lost write response", None, "the faults experiment is not in this run", "")
    else:
        ex = len(rows(base / "faults" / "enterprise.db", "SELECT 1 FROM executions WHERE tool='source_control.rollback_release'"))
        rp = len(rows(base / "faults" / "enterprise.db", "SELECT 1 FROM replays"))
        ok = ex == f["rollback"]["backend_executions"] and rp >= f["rollback"]["backend_replays"]
        c.add("lost write response", ok,
              f"database: {ex} execution(s), {rp} replay(s); summary: {f['rollback']['backend_executions']} and {f['rollback']['backend_replays']}",
              "faults/enterprise.db · executions, replays")

    # --- crash: one physical rollback across every process, and the spans survived ---
    cr = facts.get("crash")
    if not cr:
        c.add("crash and resume", None, "the crash experiment is not in this run", "")
    else:
        ex = len(rows(base / "crash" / "enterprise.db", "SELECT 1 FROM executions WHERE tool='source_control.rollback_release'"))
        pids = rows(base / "crash" / "platform.db", "SELECT DISTINCT pid FROM workflow_events WHERE workflow_id=(SELECT id FROM workflows LIMIT 1)")
        status = rows(base / "crash" / "platform.db", "SELECT status FROM workflows LIMIT 1")
        ok = ex == cr["backend_rollbacks"] == 1 and len(pids) == cr["processes"] and status and status[0][0] == cr["final_status"]
        c.add("crash and resume", ok,
              f"database: {ex} rollback(s) from {len(pids)} process(es), workflow {status[0][0] if status else '?'}; "
              f"summary: {cr['backend_rollbacks']}, {cr['processes']}, {cr['final_status']}",
              "crash/enterprise.db · crash/platform.db")
        # the resumed processes have to join the trace the killed process started, not start their own
        spans = [json.loads(line) for p in (base / "crash" / "otel" / "traces").glob("*.jsonl")
                 for line in p.read_text().splitlines() if line.strip()]
        roots = {s["trace_id"] for s in spans if s["name"].startswith("invoke_workflow")}
        incident = sorted(roots)[0] if len(roots) == 1 else None
        mine = [s for s in spans if s["trace_id"] == incident]
        pids = {s.get("pid") for s in mine}
        c.add("one trace across the kills", bool(incident) and len(pids) == cr["processes"],
              f"{len(roots)} workflow trace(s); "
              + (f"{len(mine)} spans from {len(pids)} process(es), and the run used {cr['processes']}" if incident
                 else "no single trace covers the workflow"),
              "crash/otel/traces/*.jsonl")

    # --- monolith: the baseline's repeated write is in its own database ---
    m = facts.get("monolith")
    if not m:
        c.add("monolith baseline", None, "the monolith experiment is not in this run", "")
    elif m["lost_response_rollbacks"] is None:
        c.add("monolith baseline", None, "this plan did not run the monolith's lost response", "")
    else:
        ex = len(rows(base / "monolith" / "lost-response" / "enterprise.db",
                      "SELECT 1 FROM executions WHERE tool='source_control.rollback_release'"))
        c.add("monolith baseline", ex == m["lost_response_rollbacks"],
              f"database: {ex} rollback(s); summary: {m['lost_response_rollbacks']}",
              "monolith/lost-response/enterprise.db")

    # --- tests: the counts come from the JUnit files the run kept ---
    t = facts.get("tests")
    if not t:
        c.add("test counts", None, "the tests experiment is not in this run", "")
    else:
        import xml.etree.ElementTree as ET

        counted = 0
        for x in sorted((base / "tests").glob("*.xml")):
            cases = list(ET.parse(x).getroot().iter("testcase"))
            counted += sum(1 for c_ in cases if c_.find("failure") is None and c_.find("error") is None and c_.find("skipped") is None)
        c.add("test counts", counted == t["passed"], f"JUnit files: {counted} passed; summary: {t['passed']}",
              "tests/*.xml")

    # --- the plan's expectations, judged again from the files ---
    from experiments import plan as plans

    pl = plans.for_run(base, (facts.get("run") or {}).get("profile"))
    rows_ = plans.evaluate(base, pl)
    bad = [name for status, name, _ in rows_ if status == "fail"]
    c.add("plan expectations", not bad if rows_ else None, "; ".join(bad) or f"{len(rows_)} expectation(s) met",
          "plan.yaml · facts.json")

    # --- the freeze: how this tree compares with the one that ran. Drift is information, not a failed check:
    # the recorded evidence stays valid while the code moves on, and only a byte-identical tree can reproduce it.
    drift: dict[str, Any] | None = None
    if (base / "freeze.json").exists():
        from experiments import freeze

        d = freeze.check(base)
        moved = d["changed"] + d["added"] + d["removed"]
        recorded = json.loads((base / "freeze.json").read_text())
        drift = {"digest": d["digest_recorded"], "retrospective": recorded.get("retrospective", False),
                 "changed": d["changed"], "added": d["added"], "removed": d["removed"]}
        detail = "this tree is the tree that ran" if not moved else (
            f"{len(d['changed'])} changed, {len(d['added'])} added, {len(d['removed'])} removed since the freeze; "
            "the recorded evidence stands, but this tree would not reproduce it byte for byte")
        if recorded.get("retrospective"):
            detail += " (the freeze itself was written after the run)"
        c.add("tree against the freeze", None, detail, "freeze.json")
    else:
        c.add("tree against the freeze", None, "this run was recorded before freezes existed", "")

    # --- the published claims: each one's facts path, check, run file and test are where docs/claims.json says ---
    from experiments import claims as claims_mod

    problems = claims_mod.check(base, {r["check"]: r for r in c.results})[1]
    c.add("published claims carry their evidence", not problems,
          "; ".join(problems[:3]) or f"{len(json.loads(claims_mod.CLAIMS.read_text())['claims'])} claims resolved",
          "docs/claims.json")

    passed = sum(1 for r in c.results if r["status"] == "pass")
    skipped = sum(1 for r in c.results if r["status"] == "skip")
    return {
        "run_id": base.name,
        "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ok": not c.failed,
        "passed": passed, "failed": len(c.failed), "skipped": skipped,
        "freeze": drift,
        "checks": c.results,
    }


def write(base: Path) -> dict[str, Any]:
    result = verify(base)
    (base / "verification.json").write_text(json.dumps(result, indent=2))
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--check", action="store_true", help="report only; do not rewrite verification.json")
    a = ap.parse_args()
    base = RUNS / a.run_id
    if not base.is_dir():
        sys.exit(f"no run directory {base}")
    result = verify(base) if a.check else write(base)
    mark = {"pass": "ok  ", "fail": "FAIL", "skip": "--  "}
    for r in result["checks"]:
        print(f"  {mark[r['status']]} {r['check']:<32} {r['detail']}")
    where = f"runs/{base.name}" if a.check else f"runs/{base.name}/verification.json"
    print(f"[verify] {where}: {result['passed']} passed, {result['failed']} failed, "
          f"{result['skipped']} not applicable")
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
