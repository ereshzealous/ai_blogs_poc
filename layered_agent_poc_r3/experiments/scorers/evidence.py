"""Collect the raw evidence of one scenario directory and score it the same way for both architectures.

Sources, in order of authority:
  world.db            what physically happened in the systems of record (executions, idempotent replays, final state)
  tape/model_calls    every model call that was served, with its process id and token counts
  phases.jsonl        what each process reported, plus the harness's record of exit codes (phases_harness.jsonl)
  platform.db, traces (layered)  /  agent.log.jsonl, monolith_approvals.jsonl (monolith)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from layered_platform.evals.checks import evaluate
from simulated_enterprise.world import World

WRITE_TOOLS = ("rollback_release", "restart_service", "scale_service", "flush_sessions")


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def _table(db: Path, sql: str) -> list[dict[str, Any]]:
    if not db.exists():
        return []
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql).fetchall()]
    finally:
        con.close()


def collect(d: Path, arch: str) -> dict[str, Any]:
    """Raw evidence rows for one scenario, as plain lists (written to raw/*.jsonl by the harness)."""
    w = World(d / "world.db")
    raw: dict[str, Any] = {
        "executions": w.executions(),
        "backend_calls": w.calls(),
        "model_calls": jsonl(d / "tape" / "model_calls.jsonl"),
        "phases": jsonl(d / "phases.jsonl"),
        "processes": jsonl(d / "phases_harness.jsonl"),
    }
    if arch == "layered":
        db = d / "platform" / "platform.db"
        raw["workflow_events"] = _table(db, "SELECT * FROM workflow_events ORDER BY seq")
        raw["checkpoints"] = _table(db, "SELECT workflow_id, seq, step, next_step, status, state_sha, pid, ts FROM checkpoints ORDER BY workflow_id, seq")
        raw["policy_events"] = _table(db, "SELECT * FROM policy_events ORDER BY seq")
        raw["tool_calls"] = _table(db, "SELECT * FROM tool_calls ORDER BY seq")
        raw["approvals"] = _table(db, "SELECT * FROM approvals ORDER BY created")
        raw["operations"] = _table(db, "SELECT * FROM operations ORDER BY created")
        raw["model_usage"] = _table(db, "SELECT * FROM model_usage ORDER BY seq")
        raw["traces"] = [s for f in sorted((d / "platform" / "traces").glob("*.jsonl")) for s in jsonl(f)]
    else:
        log = jsonl(d / "monolith" / "agent.log.jsonl")
        raw["agent_log"] = log
        raw["tool_calls"] = [e for e in log if e["event"] == "tool_call"]
        raw["approvals"] = jsonl(d / "monolith_approvals.jsonl")
        raw["policy_events"] = [e for e in log if e["event"] == "approval"]
        raw["traces"] = log
    return raw


def score(d: Path, arch: str, raw: dict[str, Any], crash_point: str | None = None) -> dict[str, Any]:
    w = World(d / "world.db")
    phases = raw["phases"]
    final = phases[-1] if phases else {}
    report = final.get("report") or ""
    writes = [e for e in raw["executions"] if e["tool"] in WRITE_TOOLS]
    if arch == "layered":
        grants = [a["decided"] for a in raw["approvals"] if a["status"] == "APPROVED" and a["decided"]]
    else:
        grants = [a["ts"] for a in raw["approvals"] if a.get("approved")]
    approval_ok = all(any(g < e["wall"] for g in grants) for e in writes if e["args"].get("environment") == "production")
    checks = evaluate(report, w, approval_ok)
    procs = raw["processes"]
    killed = [p for p in procs if p.get("returncode") == -9]
    # model calls per process, in process order; "after the crash" = calls made by processes started after a SIGKILL
    pids = [p["pid"] for p in procs]
    calls_by_pid: dict[int, list[dict[str, Any]]] = {}
    for c in raw["model_calls"]:
        calls_by_pid.setdefault(c["pid"], []).append(c)
    first_kill = next((i for i, p in enumerate(procs) if p.get("returncode") == -9), None)
    after = [c for i, pid in enumerate(pids) if first_kill is not None and i > first_kill for c in calls_by_pid.get(pid, [])]
    before = [c for i, pid in enumerate(pids) if first_kill is None or i <= first_kill for c in calls_by_pid.get(pid, [])]
    rollback_tool_attempts = [t for t in raw["tool_calls"] if (t.get("tool") or t.get("capability", "")) in ("rollback_release", "rollback", "deploy.rollback")]
    tok = lambda cs: sum(c["prompt_tokens"] + c["completion_tokens"] for c in cs)  # noqa: E731
    out = {
        "arch": arch,
        "final_status": final.get("status"),
        "report": report,
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "physical_rollbacks": len(w.executions("rollback_release")),
        "physical_writes": {t: len(w.executions(t)) for t in WRITE_TOOLS + ("update_incident",)},
        "backend_idempotent_replays": w.replays("rollback_release"),
        "rollback_attempts_client": len(rollback_tool_attempts),
        "rollback_requests_backend": sum(1 for c in raw["backend_calls"] if c["tool"] == "rollback_release"),
        "running_release": w.running("checkout-api", "production"),
        "incident_status": w.incident_doc()["status"],
        "incident_notes": len(w.incident_doc()["notes"]),
        "healthy_at_end": w.healthy("checkout-api"),
        "processes": len(procs),
        "sigkills": len(killed),
        "model_calls": len(raw["model_calls"]),
        "tokens": tok(raw["model_calls"]),
        "model_calls_before_crash": len(before) if first_kill is not None else None,
        "tokens_before_crash": tok(before) if first_kill is not None else None,
        "model_calls_after_crash": len(after) if first_kill is not None else None,
        "tokens_after_crash": tok(after) if first_kill is not None else None,
        "tool_calls_client": len(raw["tool_calls"]),
        "backend_calls": len(raw["backend_calls"]),
        "wall_s_total": round(sum(p.get("wall_s", 0) for p in procs), 2),
        "wall_s_after_crash": round(sum(p.get("wall_s", 0) for i, p in enumerate(procs) if first_kill is not None and i > first_kill), 2) if first_kill is not None else None,
        "crash_point": crash_point,
    }
    if arch == "layered":
        cps = raw["checkpoints"]
        out["checkpoints"] = len(cps)
        out["checkpoint_steps"] = [c["step"] for c in cps]
        steps_started = [e for e in raw["workflow_events"] if e["kind"] == "step.started"]
        out["steps_started"] = [e["step"] for e in steps_started]
        seen, rerun = set(), []
        for e in steps_started:
            if e["step"] in seen:
                rerun.append(e["step"])
            seen.add(e["step"])
        out["steps_rerun"] = rerun
        kill_t = procs[first_kill]["started"] + procs[first_kill]["wall_s"] if first_kill is not None else None
        out["steps_completed_before_crash"] = [c["step"] for c in cps if c["ts"] <= kill_t] if kill_t else None
        out["operations"] = [{k: o[k] for k in ("capability", "state", "attempts")} for o in raw["operations"]]
        out["policy_effects"] = [f"{p['capability']}:{p['effect']}:{p['rule']}" for p in raw["policy_events"] if p["effect"] != "ALLOW"]
        wfs = _table(d / "platform" / "platform.db", "SELECT state FROM workflows")
        stats = json.loads(wfs[0]["state"]).get("agent_stats", {}) if wfs else {}
        out["structured_output_repairs"] = sum(v.get("repairs", 0) for v in stats.values())
        out["resumed_events"] = sum(1 for e in raw["workflow_events"] if e["kind"] == "run.resumed")
        out["lease_takeovers"] = sum(1 for e in raw["workflow_events"] if e["kind"] == "lease.taken_over")
    else:
        out["approval_prompts"] = len(raw["approvals"])
    return out
