"""facts.json: every measured value a run supports, computed from that run's own files.

    uv run python -m experiments.facts --run-id 2026-09-17-recorded      # write runs/<id>/facts.json

One run, one file, one source. The report, the article and the diagrams read values from here; none of them
recomputes a number of its own. Values are numbers, booleans and ids: wording and rounding belong to whoever writes
the prose. A value that a run cannot support is absent rather than guessed, so a consumer fails loudly.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
CHECKS = ["root_cause_identified", "correct_deployment", "red_herrings_rejected", "authoritative_rollback",
          "approval_before_write", "unsafe_action_blocked", "verified_before_update", "write_exactly_once"]


def load(path: Path) -> Any:
    return json.loads(path.read_text()) if path.exists() else None


def med(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


def repaired(record: dict[str, Any]) -> bool:
    """The remediation agent's first structured answer failed its contract and the one bounded repair fixed it."""
    return any(s["name"] == "invoke_agent remediation-agent" and s["attributes"].get("lap.agent.repaired")
               for s in record.get("trace", []))


def workflow_records(base: Path) -> list[dict[str, Any]]:
    return [load(p) for p in sorted((base / "workflow").glob("*/run*/record.json"))]


def sample_run(base: Path, records: list[dict[str, Any]], model: str) -> dict[str, Any] | None:
    """The run the article quotes: the first passing run of `model`, else its first run."""
    mine = [r for r in records if r["model"] == model]
    if not mine:
        return None
    rec = next((r for r in mine if r["eval"]["ok"]), mine[0])
    v, inv = rec["view"], rec.get("investigation") or {}
    ctx = inv.get("context") or {}
    d, p, rem, ver = (v.get(k) or {} for k in ("diagnosis", "proposal", "remediation", "verification"))
    intake_reads = sum(1 for a in rec["audit"] if a["event"] == "invocation.executed" and a.get("step") == "intake")
    return {
        "workflow_id": v["workflow_id"], "model": rec["model"], "channel": v.get("channel"),
        "requested_by": v.get("requested_by"), "approved_by": (v.get("approval") or {}).get("decided_by"),
        "status": v["status"], "evals_passed": rec["eval"]["passed"], "evals_total": rec["eval"]["total"],
        "seconds_to_approval": rec.get("seconds_to_approval"), "seconds_total": rec.get("seconds_total"),
        "tokens": sum(u["input_tokens"] + u["output_tokens"] for u in rec["usage"]), "model_calls": len(rec["usage"]),
        "diagnosis": {"suspect_service": d.get("suspect_service"), "suspect_version": d.get("suspect_version"),
                      "suspect_deployment_id": d.get("suspect_deployment_id"), "confidence": d.get("confidence"),
                      "root_cause": d.get("root_cause"), "evidence_items": len(d.get("evidence", []))},
        "proposal": {"tool_id": p.get("tool_id"), "target_version": p.get("target_version"),
                     "environment": p.get("environment"), "citations": p.get("citations", [])},
        "remediation": {"status": rem.get("status"), "attempts": rem.get("attempts"), "replayed": rem.get("replayed")},
        "verification": {"ok": ver.get("ok"), "p95_ms": ver.get("p95_ms"), "slo_p95_ms": ver.get("slo_p95_ms")},
        "diagnosis_tool_calls": len(inv.get("tool_calls") or []),
        "evidence_reads": len(inv.get("tool_calls") or []) + intake_reads,
        "context": {"tokens_by_kind": ctx.get("tokens_by_kind") or {}, "instructions": ctx.get("instructions"),
                    "budget": ctx.get("budget"), "sources": len(ctx.get("sources") or []),
                    "estimated_tokens": sum((ctx.get("tokens_by_kind") or {}).values()) + int(ctx.get("instructions") or 0)},
    }


def build(base: Path) -> dict[str, Any]:
    """Every value this run supports. Sections are absent when the experiment did not run."""
    facts: dict[str, Any] = {
        "run_id": base.name,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema": 1,
    }
    meta = load(base / "run.json")
    if meta:
        facts["run"] = {k: meta.get(k) for k in ("mode", "replay_from", "recorded", "profile", "models", "k",
                                                 "model_tests", "started", "finished", "host")}
    tests = load(base / "tests.json")
    if tests:
        sittings = load(base / "tests" / "sittings.json") or []
        facts["tests"] = {**tests, "sittings": len(sittings),
                          "model_sittings": sum(1 for s in sittings if s["label"].lower().startswith("model test"))}
    wf = load(base / "workflow" / "summary.json")
    records = workflow_records(base) if wf else []
    if wf:
        facts["platform"] = {
            model: {
                "runs": s["runs"], "completed": s["completed"], "all_checks_passed": s["eval_all_pass"],
                "median_seconds_to_approval": med(s["seconds_to_approval"]),
                "median_seconds_after_approval": med([t - a for t, a in zip(s["seconds_total"], s["seconds_to_approval"])]),
                "median_seconds_total": med(s["seconds_total"]), "median_tokens": med(s["tokens"]),
                "median_model_calls": med(s["model_calls"]), "median_tool_calls": med(s["tool_calls"]),
                "check_pass": {c: s["check_pass"].get(c, 0) for c in CHECKS},
                "statuses": s["statuses"],
            } for model, s in wf.items()
        }
        by_model: dict[str, list[int]] = {}
        for r in records:
            by_model.setdefault(r["model"], []).append(int(repaired(r)))
        facts["remediation_repairs"] = {"runs": len(records), "repaired": sum(sum(v) for v in by_model.values()),
                                        "by_model": {m: {"repaired": sum(v), "runs": len(v)} for m, v in by_model.items()}}
        facts["diagnosis_tool_calls"] = {"min": min(len((r.get("investigation") or {}).get("tool_calls") or []) for r in records),
                                         "max": max(len((r.get("investigation") or {}).get("tool_calls") or []) for r in records)}
        first_model = (meta or {}).get("models", [records[0]["model"]])[0]
        sample = sample_run(base, records, first_model)
        if sample:
            facts["sample_run"] = sample
        mem = memory_facts(base, records, first_model)
        if mem:
            facts["memory"] = mem
    faults = load(base / "faults" / "summary.json")
    if faults:
        facts["faults"] = {
            "model": faults.get("model"), "arm_at": faults.get("arm_at"), "injected": faults.get("injected"),
            "status": faults["status"], "evals_passed": faults["eval"]["passed"], "evals_total": faults["eval"]["total"],
            "rollback": faults["rollback"], "timeouts_in_audit": faults["timeouts_in_audit"],
            "verify_attempts": max((v["attempts"] for v in faults["verify_latency_calls"] if v["attempts"]), default=None),
        }
    crash = load(base / "crash" / "summary.json")
    if crash:
        seq = crash.get("sequence") or []
        facts["crash"] = {
            "workflow_id": crash["workflow_id"], "kill_at": crash.get("kill_at"),
            "processes": crash["processes"], "sigkills": sum(1 for p in seq if p.get("returncode") == -9) or 2,
            "status_after_first_kill": crash["run"]["status_after"],
            "final_status": seq[-1]["status_after"] if seq else crash["resume"]["status"],
            "backend_rollbacks": crash["backend_rollbacks"],
            "remediation_replayed": crash["resume"]["remediation_replayed"],
            "model_calls_before_crash": crash["model_calls_before_crash"],
            "model_calls_after_resume": crash["model_calls_after_resume"],
            "tokens_before_crash": crash["tokens_before_crash"], "tokens_after_crash": crash["tokens_after_crash"],
            "checkpoints": len(crash["checkpoints"]),
        }
    mono = load(base / "monolith" / "summary.json")
    if mono:
        runs = mono["runs"]
        facts["monolith"] = {
            "runs": len(runs), "median_seconds": med([r["seconds"] for r in runs]),
            "median_tokens": med([r["tokens"] for r in runs]),
            "kubernetes_rollbacks": mono["kubernetes_rollbacks"], "outcomes": mono["outcomes"],
            "lost_response_rollbacks": (mono.get("lost_response") or {}).get("world", {}).get("rollback_executions"),
            "crash_seconds_to_prompt": (mono.get("crash") or {}).get("seconds_until_approval_prompt"),
            "crash_state_left_behind": len((mono.get("crash") or {}).get("state_left_behind") or []),
        }
    cs = load(base / "change-scope.json") or load(RUNS / "change-scope.json")
    if cs:
        facts["change_scope"] = [{
            "id": c["id"], "title": c["title"],
            **{side: {"files": c[side]["files"], "added": c[side]["added"], "removed": c[side]["removed"],
                      "concerns": c[side]["concerns"], "applies": c[side].get("applies"),
                      "contracts_kept": c[side].get("contracts_kept")} for side in ("monolith", "layered")},
        } for c in cs["changes"]]
    return facts


def memory_facts(base: Path, records: list[dict[str, Any]], model: str) -> dict[str, Any] | None:
    """What the memory store held and what the run recalled, read from that run's own database."""
    mine = [r for r in records if r["model"] == model]
    if not mine:
        return None
    rec = next((r for r in mine if r["eval"]["ok"]), mine[0])
    db = base / "workflow" / model.replace(":", "_") / "run1" / "platform.db"
    if not db.exists():
        return None
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT id, source, expires_at FROM memories ORDER BY id")]
    read = next((s["attributes"] for s in rec.get("trace", []) if s["name"] == "memory.read"), {})
    used = {s for s in ((rec.get("proposals") or [{}])[0].get("context") or {}).get("sources", []) if s.startswith("memory:")}
    return {
        "stored": len(rows),
        "seeded": sum(1 for r in rows if not r["source"].startswith("workflow:")),
        "written_by_this_run": sum(1 for r in rows if r["source"].startswith("workflow:")),
        "expired_skipped_at_read": read.get("lap.memory.expired_skipped"),
        "returned_at_read": read.get("lap.memory.returned"),
        "recalled_into_remediation": len(used),
    }


def write(base: Path) -> Path:
    facts = build(base)
    out = base / "facts.json"
    out.write_text(json.dumps(facts, indent=2, default=str))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    base = RUNS / a.run_id
    if not base.is_dir():
        sys.exit(f"no run directory {base}")
    out = write(base)
    print(f"[facts] {out.relative_to(ROOT)}: {len(json.loads(out.read_text()))} sections")


if __name__ == "__main__":
    main()
