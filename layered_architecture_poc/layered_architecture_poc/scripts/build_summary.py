"""Build runs/<id>/summary.json (the single source of truth for published numbers) and runs/<id>/facts.json.

    uv run python scripts/build_summary.py runs/<id>

Reads only files inside the run directory: scenarios/*/score.json, changes/*.json, experiments/E6_probes.json,
tests.json and manifest.json.  Writes experiments/E1..E9.json, raw/*.jsonl (all scenarios concatenated), summary.json
and facts.json (every scalar leaf of summary.json as a dotted key with its source).
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

import yaml

POC = Path(__file__).resolve().parents[1]


def med(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def agg(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        return {}
    return {
        "runs": len(runs),
        "runs_all_checks": sum(r["checks_passed"] == r["checks_total"] for r in runs),
        "checks_passed": sum(r["checks_passed"] for r in runs),
        "checks_total": sum(r["checks_total"] for r in runs),
        "check_pass_counts": {k: sum(r["checks"][k] for r in runs) for k in runs[0]["checks"]},
        "diagnosis_correct": sum(r["checks"]["diagnosis_names_release"] and r["checks"]["diagnosis_names_pool"] for r in runs),
        "rolled_back_to_rel_2030": sum(r["running_release"] == "rel-2030" for r in runs),
        "physical_rollbacks": [r["physical_rollbacks"] for r in runs],
        "physical_rollbacks_total": sum(r["physical_rollbacks"] for r in runs),
        "runs_with_duplicate_rollback": sum(r["physical_rollbacks"] > 1 for r in runs),
        "approval_before_write": sum(r["checks"]["approval_before_write"] for r in runs),
        "median_model_calls": med([r["model_calls"] for r in runs]),
        "median_tokens": med([r["tokens"] for r in runs]),
        "median_wall_s": med([r["wall_s_total"] for r in runs]),
        "structured_output_repairs": sum(r.get("structured_output_repairs", 0) for r in runs),
        "final_statuses": sorted({r["final_status"] or "none" for r in runs}),
    }


def main(run_dir: Path) -> None:
    plan = yaml.safe_load((POC / "experiments/preregistration/experiment_plan.yaml").read_text())
    manifest = json.loads((run_dir / "manifest.json").read_text())
    tests = json.loads((run_dir / "tests.json").read_text())
    sc = {p.parent.name: json.loads(p.read_text()) for p in sorted((run_dir / "scenarios").glob("*/score.json"))}
    changes = {p.stem: json.loads(p.read_text()) for p in sorted((run_dir / "changes").glob("*.json"))}
    probes = json.loads((run_dir / "experiments" / "E6_probes.json").read_text())

    def runs(exp: str, arch: str) -> list[dict[str, Any]]:
        return [v for v in sc.values() if v["exp"] == exp and v["arch"] == arch]

    def scope(change: str) -> dict[str, Any]:
        out = {}
        for arch in ("monolith", "layered"):
            c = changes.get(f"{change}-{arch}")
            if c:
                out[arch] = {k: c[k] for k in ("files_changed", "lines_added", "lines_removed", "test_files_changed", "concerns_touched", "concerns_touched_n",
                                               "concerns_by_file", "home_concern", "outside_expected", "spill_over_n", "review_surface_concerns", "review_surface_concerns_n",
                                               "review_surface_loc", "tests_after_change", "tests_returncode", "patch", "patch_sha256")}
                out[arch]["files"] = [f["path"] for f in c["files"]]
        return out

    E: dict[str, Any] = {}
    E["E1"] = {"monolith": agg(runs("E1", "monolith")), "layered": agg(runs("E1", "layered"))}
    E["E2"] = {"change": scope("E2_model_swap"), "model_b": plan["models"]["B"]["name"],
               "monolith": agg(runs("E2", "monolith")), "layered": agg(runs("E2", "layered"))}
    E["E3"] = {"change": scope("E3_tool_v2"), "monolith": agg(runs("E3", "monolith")), "layered": agg(runs("E3", "layered"))}
    for arch in ("monolith", "layered"):
        r3 = runs("E3", arch)
        E["E3"][arch]["v2_rollback_gated"] = all(r["checks"]["approval_before_write"] and r["physical_rollbacks"] >= 1 for r in r3) if r3 else None
    E["E4"] = {}
    for arch in ("monolith", "layered"):
        rs = runs("E4", arch)
        E["E4"][arch] = {**agg(rs), "client_rollback_attempts": [r["rollback_attempts_client"] for r in rs],
                         "backend_rollback_requests": [r["rollback_requests_backend"] for r in rs],
                         "backend_idempotent_replays": [r["backend_idempotent_replays"] for r in rs]}
    E["E5"] = {}
    for arch in ("monolith", "layered"):
        rs = runs("E5", arch)
        E["E5"][arch] = {**agg(rs), "sigkills": sum(r["sigkills"] for r in rs),
                         "model_calls_after_crash": [r["model_calls_after_crash"] for r in rs],
                         "tokens_after_crash": [r["tokens_after_crash"] for r in rs],
                         "median_tokens_after_crash": med([r["tokens_after_crash"] for r in rs]),
                         "median_model_calls_after_crash": med([r["model_calls_after_crash"] for r in rs]),
                         "median_tokens_before_crash": med([r["tokens_before_crash"] for r in rs]),
                         "median_wall_s_after_crash": med([r["wall_s_after_crash"] for r in rs]),
                         "backend_calls_after_crash_note": "see raw/backend_calls.jsonl",
                         "steps_rerun": [r.get("steps_rerun") for r in rs] if arch == "layered" else None,
                         "steps_completed_before_crash": [r.get("steps_completed_before_crash") for r in rs] if arch == "layered" else None,
                         "lease_takeovers": sum(r.get("lease_takeovers", 0) for r in rs) if arch == "layered" else None}
    m_pro = {p["id"]: p for p in probes["monolith"]}
    l_pro = {p["id"]: p for p in probes["layered"] if p["id"].startswith("P")}
    adv = {arch: runs("E6", arch) for arch in ("monolith", "layered")}
    E["E6"] = {"probes": [{"id": p["id"], "what": p["what"], "monolith": m_pro[p["id"]]["outcome"], "layered": l_pro[p["id"]]["outcome"],
                           "monolith_backend_executions": m_pro[p["id"]].get("backend_executions"), "layered_backend_executions": l_pro[p["id"]].get("backend_executions"),
                           "layered_decision": l_pro[p["id"]].get("detail")} for p in probes["probes"]],
               "adversarial": {arch: {"runs": len(rs), "restarts_executed": sum(r["physical_writes"]["restart_service"] for r in rs),
                                      "flushes_executed": sum(r["physical_writes"]["flush_sessions"] for r in rs),
                                      "approval_before_write": sum(r["checks"]["approval_before_write"] for r in rs),
                                      "physical_rollbacks": sum(r["physical_rollbacks"] for r in rs), "checks_passed": sum(r["checks_passed"] for r in rs),
                                      "checks_total": sum(r["checks_total"] for r in rs),
                                      "policy_effects": [e for r in rs for e in r.get("policy_effects", [])]} for arch, rs in adv.items()}}
    for arch in ("monolith", "layered"):
        E["E6"][f"{arch}_probes_executed_writes"] = sum(1 for p in E["E6"]["probes"] if p[arch] == "executed")
        E["E6"][f"{arch}_probes_blocked"] = sum(1 for p in E["E6"]["probes"] if p[arch] == "blocked")
        E["E6"][f"{arch}_probes_asked_human"] = sum(1 for p in E["E6"]["probes"] if p[arch] == "asked_human")
        E["E6"][f"{arch}_probes_not_expressible"] = sum(1 for p in E["E6"]["probes"] if p[arch] == "not_expressible")
    E["E7"] = {}
    for arch in ("monolith", "layered"):
        rs = runs("E7", arch)
        r = rs[0] if rs else {}
        survived = arch == "layered" and r.get("steps_completed_before_crash") is not None
        E["E7"][arch] = {**agg(rs), "model_calls_after_crash": r.get("model_calls_after_crash"), "tokens_after_crash": r.get("tokens_after_crash"),
                         "workflow_id_survives": survived, "completed_steps_survive": survived and bool(r.get("steps_completed_before_crash")) and not r.get("steps_rerun"),
                         "approval_state_survives": survived and r.get("final_status") == "COMPLETED",
                         "steps_completed_before_crash": r.get("steps_completed_before_crash"), "steps_rerun": r.get("steps_rerun")}
    E["E8"] = {}
    for arch in ("monolith", "layered"):
        rs = [v for v in sc.values() if v["arch"] == arch and v["exp"] in ("E1", "E5")]
        traces = [r["trace"] for r in rs]
        keys = list(traces[0]["present"]) if traces else []
        E["E8"][arch] = {"runs": len(rs), "elements": len(keys), "median_score": med([t["score"] for t in traces]),
                         "min_score": min((t["score"] for t in traces), default=None),
                         "present_in_all_runs": [k for k in keys if all(t["present"][k] for t in traces)],
                         "missing_in_any_run": [k for k in keys if not all(t["present"][k] for t in traces)]}
    l5 = [r["trace"] for r in runs("E5", "layered")]
    E["E8"]["layered"]["crash_runs_single_trace_across_processes"] = sum(1 for t in l5 if t["trace_ids"] == 1 and t["processes"] > 1)
    E["E8"]["layered"]["crash_runs"] = len(l5)
    E["E9"] = {"change": scope("E9_dry_run")}
    for arch in ("monolith", "layered"):
        rs = runs("E9", arch)
        E["E9"][arch] = {"runs": len(rs), "deploy_writes": sum(r["physical_writes"][t] for r in rs for t in ("rollback_release", "restart_service", "scale_service", "flush_sessions")),
                         "plan_names_rollback_to_rel_2030": sum(("rel-2030" in (r["report"] or "").replace("‑", "-")) for r in rs),
                         "final_statuses": sorted({r["final_status"] or "none" for r in rs}), "reports": [r["report"] for r in rs]}

    supp = {p.parent.name: json.loads(p.read_text()) for p in sorted((run_dir / "supplementary").glob("*/score.json"))}
    expected = [s["id"] for s in plan["scenarios"]]
    summary = {
        "run_id": manifest["run_id"], "mode": manifest["mode"], "replay_of": manifest.get("replay_of"),
        "plan_id": plan["plan_id"], "plan_sha256": manifest["hashes"]["experiment_plan"],
        "models": {k: v["name"] for k, v in plan["models"].items()},
        "integrity": {"scenarios_expected": len(expected), "scenarios_present": sum(1 for s in expected if s in sc),
                      "missing": [s for s in expected if s not in sc], "tape_misses": sum(v.get("tape_misses", 0) for v in sc.values()),
                      "sigkills": sum(v["sigkills"] for v in sc.values())},
        "tests": {k: tests[k] for k in ("total", "passed", "failed", "skipped", "require_local_models")} | {"by_category": tests["by_category"]},
        "experiments": E,
        "supplementary": {k: {f: v.get(f) for f in ("exp", "arch", "final_status", "checks_passed", "checks_total", "checks", "physical_rollbacks",
                                                    "model_calls", "tokens", "model_calls_after_crash", "tokens_after_crash", "sigkills", "report")}
                          for k, v in supp.items()},
        "revisions": [r["id"] for r in manifest.get("evidence_revisions", [])],
        "replay": (lambda r: {k: r[k] for k in ("replay_run", "identical", "model_calls_served_from_tape", "fresh_model_calls")} if r else None)(
            json.loads((run_dir / "replay_comparison.json").read_text()) if (run_dir / "replay_comparison.json").exists() else None),
    }
    summary["headline"] = {
        "e4_duplicate_rollbacks": {arch: E["E4"][arch].get("physical_rollbacks_total", 0) - E["E4"][arch].get("runs", 0) for arch in ("monolith", "layered")},
        "e4_physical_rollbacks_total": {arch: E["E4"][arch].get("physical_rollbacks_total") for arch in ("monolith", "layered")},
        "e5_physical_rollbacks_total": {arch: E["E5"][arch].get("physical_rollbacks_total") for arch in ("monolith", "layered")},
        "e5_median_tokens_after_crash": {arch: E["E5"][arch].get("median_tokens_after_crash") for arch in ("monolith", "layered")},
        "e3_concerns_touched": {arch: E["E3"]["change"].get(arch, {}).get("concerns_touched_n") for arch in ("monolith", "layered")},
        "e2_concerns_touched": {arch: E["E2"]["change"].get(arch, {}).get("concerns_touched_n") for arch in ("monolith", "layered")},
        "e9_files_changed": {arch: E["E9"]["change"].get(arch, {}).get("files_changed") for arch in ("monolith", "layered")},
        "spill_over": {c: {arch: E[c]["change"].get(arch, {}).get("spill_over_n") for arch in ("monolith", "layered")} for c in ("E2", "E3", "E9")},
        "review_surface": {c: {arch: E[c]["change"].get(arch, {}).get("review_surface_concerns_n") for arch in ("monolith", "layered")} for c in ("E2", "E3", "E9")},
        "e1_runs_all_checks": {arch: f"{E['E1'][arch].get('runs_all_checks')}/{E['E1'][arch].get('runs')}" for arch in ("monolith", "layered")},
        "e8_median_trace_score": {arch: f"{E['E8'][arch]['median_score']}/{E['E8'][arch]['elements']}" for arch in ("monolith", "layered")},
        "e6_probe_writes_executed": {arch: E["E6"][f"{arch}_probes_executed_writes"] for arch in ("monolith", "layered")},
        "tests": f"{tests['passed']}/{tests['total']}",
    }
    (run_dir / "experiments").mkdir(exist_ok=True)
    for k, v in E.items():
        (run_dir / "experiments" / f"{k}.json").write_text(json.dumps(v, indent=1, default=str))
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1, default=str))

    # raw/*.jsonl: every scenario's evidence, concatenated, each row tagged with its scenario
    names = {"model_calls": "model_calls", "tool_calls": "tool_calls", "workflow_events": "workflow_events", "policy_events": "policy_events",
             "checkpoints": "checkpoints", "traces": "traces", "executions": "backend_executions", "approvals": "approvals", "agent_log": "monolith_agent_log"}
    (run_dir / "raw").mkdir(exist_ok=True)
    for src, dst in names.items():
        with open(run_dir / "raw" / f"{dst}.jsonl", "w") as out:
            for sid in sorted(sc):
                f = run_dir / "scenarios" / sid / "raw" / f"{src}.jsonl"
                for line in (f.read_text().splitlines() if f.exists() else []):
                    out.write(json.dumps({"scenario": sid, **json.loads(line)}, default=str) + "\n")

    facts: dict[str, Any] = {}

    def walk(prefix: str, node: Any, src: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(f"{prefix}.{k}" if prefix else str(k), v, src)
        elif isinstance(node, list) and all(not isinstance(x, (dict, list)) for x in node):
            facts[prefix] = {"value": ", ".join(str(x) for x in node), "source": src}
        elif not isinstance(node, list):
            facts[prefix] = {"value": node, "source": src}

    walk("", {k: v for k, v in summary.items() if k != "experiments"}, "summary.json")
    walk("", E, "summary.json → experiments")
    walk("manifest", {k: manifest[k] for k in ("run_id", "started_utc", "finished_utc", "ollama_version", "python", "platform", "cpu", "memory_gb", "mcp_sdk", "harness_wall_s")}, "manifest.json")
    for k, v in manifest["hashes"].items():
        facts[f"hash.{k}"] = {"value": v[:12], "source": "manifest.json → hashes"}
    for k, v in manifest["models"].items():
        facts[f"model.{k}.digest"] = {"value": (v.get("digest") or "")[:12], "source": "manifest.json → models"}
    (run_dir / "facts.json").write_text(json.dumps(facts, indent=1, default=str))
    print(f"summary.json: {len(sc)} scenarios, {len(facts)} facts")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
