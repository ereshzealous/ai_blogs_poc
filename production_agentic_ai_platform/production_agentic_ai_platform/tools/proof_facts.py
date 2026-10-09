"""The proof pack's fact registry (pae-proof/v1): every fact a check in proof/experiments.toml compares, every number the
articles, the README and the Lab print, with where it comes from.

    collect(run_id) -> (Facts, data)

Everything is read from the run's recorded files, never typed:

  raw/results.json             what run_proof.py recorded: each harness check's observed value (obs.<check>) and, where
                               the harness derived the expectation from evidence, that expectation (exp.<check>); the
                               environment; the per-experiment facts the articles print (r1_digest, r6_cap, …)
  raw/experiments/**           recomputed here, independently of the harness: production rollbacks in each
                               experiment's release-pipeline database, audit hash chains, SIGKILLed processes
  replay.json                  the replay comparison of this run (tools/replay_compare.py)
  negative-control/raw/        the same proof on a copy without the approval requirement (negative_control.py)

A value is scalar so a check compares exactly one thing: lists of plain values are joined with " · ", anything nested is
canonical JSON (scalar()). Run from the POC's environment: uv run python tools/proof_pack.py …
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor"))
sys.path.insert(0, str(ROOT / "src"))
from evidence_kit.facts import Facts  # noqa: E402  (evidence-kit 5.2.0, vendor/)

RUNS = ROOT / "evidence" / "runs"
# where the cross-run hygiene checks belong: each guards the property of the experiment it is placed in
CROSS = {"X.canary": "R8", "X.keys": "R5", "X.chains": "R13"}
CONTENT_IDS = [("R1", k) for k in ("workflow_id", "digest", "approval_id", "decision_id", "jti", "idempotency_key", "rollback_id",
                                    "policy_version", "bundle_version")] + [("R3", "approved_digest"), ("R3", "tampered_digest")]


def scalar(v: Any) -> Any:
    """One comparable value: numbers, strings, booleans and null as they are; a list of plain values joined with ' · '
    (empty: 'none'); anything nested as canonical JSON."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, list) and all(x is None or isinstance(x, (bool, int, float, str)) for x in v):
        return " · ".join("null" if x is None else str(x).lower() if isinstance(x, bool) else str(x) for x in v) if v else "none"
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def read(p: Path) -> Any:
    return json.loads(p.read_text())


def rows(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def harness_checks(res: dict) -> list[tuple[str, dict]]:
    """(experiment id, check) for every harness check, the cross-run checks under the experiment they belong to."""
    out = [(e["id"], c) for e in res["experiments"] for c in e["checks"]]
    return out + [(CROSS[c["id"]], c) for c in res.get("cross_checks", [])]


def rollbacks(db: Path) -> int:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute("SELECT COUNT(*) FROM rollbacks").fetchone()[0]
    finally:
        con.close()


def collect(run_id: str) -> tuple[Facts, dict]:
    run = RUNS / run_id
    raw = run / "raw"
    base = f"evidence/runs/{run_id}/raw"
    R = f"{base}/results.json"
    res = read(raw / "results.json")
    F = Facts()
    E = {e["id"]: e for e in res["experiments"]}
    FX = {k: e["facts"] for k, e in E.items()}

    # ---- the run ----------------------------------------------------------------------------------------------------
    F.add("run_id", res["run_id"], source=R + " → run_id")
    F.add("run_date", res["finished_at"][:10], source=R + " → finished_at")
    F.add("run.started_at", res["started_at"], source=R + " → started_at")
    F.add("run.finished_at", res["finished_at"], source=R + " → finished_at")
    F.add("wall_clock_s", res["wall_clock_s"], source=R + " → wall_clock_s", unit="s")
    for k in ("experiments", "experiments_passed", "checks", "passed", "failed"):
        F.add(f"total_{k}", res["totals"][k], source=R + f" → totals.{k}", derivation="harness assertions (run_proof.py), before the contract's evaluation")
    F.add("harness.exceptions", len(res.get("harness_exceptions", [])), source=R + " → harness_exceptions",
          derivation="experiments that stopped on an exception; recorded since the harness repair (absent before: 0)")
    F.add("unit_tests", res["unit_tests"]["total"], source=R + " → unit_tests.total")
    F.add("unit_tests_passed", res["unit_tests"]["passed"], source=R + " → unit_tests.passed")
    F.add("unit_tests_failed", res["unit_tests"]["failed"], source=R + " → unit_tests.failed")
    for k, v in res["environment"].items():
        F.add(f"env_{k}", v, source=R + f" → environment.{k}")
    for k, v in res["evidence_counts"].items():
        F.add(f"count_{k}", v, source=R + f" → evidence_counts.{k}")
    for eid, e in E.items():
        F.add(f"{eid}_checks", e["total"], source=R + f" → {eid}.total")
        F.add(f"{eid}_passed", e["passed"], source=R + f" → {eid}.passed")
        F.add(f"{eid}_status", e["status"], source=R + f" → {eid}.status")

    # ---- each harness check: what was observed, and an expectation the harness derived from evidence ----------------
    for eid, c in harness_checks(res):
        where = f"{eid}.checks[{c['id']}]" if not c["id"].startswith("X.") else f"cross_checks[{c['id']}]"
        F.add(f"obs.{c['id']}", scalar(c["actual"]), source=f"{R} → {where}.actual", derivation=c["claim"])
        F.add(f"exp.{c['id']}", scalar(c["expected"]), source=f"{R} → {where}.expected",
              derivation="the expectation the harness computed for this check (a constant, or a value read from the run's evidence)")

    # ---- the facts the articles print (the same ids as before the contract) -------------------------------------------
    f = FX["R1"]
    for k in ("workflow_id", "trace_id", "digest", "approval_id", "approver", "decision_id", "policy_version", "bundle_version", "jti", "cap_ttl_s",
              "idempotency_key", "rollback_id", "model", "model_calls", "tool_calls", "workflow_steps", "cost_units", "audit_events", "spans", "p95_after",
              "slo", "eval_passed", "eval_total", "agent_code_sha256", "bundle_digest"):
        v = f[k]
        F.add(f"r1_{k}", int(v) if isinstance(v, float) and v == int(v) else v, source=R + f" → R1.facts.{k}")
    F.add("r1_digest_short", f["digest"][:16], source=R + " → R1.facts.digest", derivation="first 16 hex characters")
    F.add("r1_agent_sha_short", f["agent_code_sha256"][:12], source=R + " → R1.facts.agent_code_sha256", derivation="first 12 hex characters")
    F.add("r1_offered", len(f["offered"]), source=R + " → R1.facts.offered")
    F.add("r1_exposed", len(f["mcp_exposed"]), source=R + " → R1.facts.mcp_exposed")
    F.add("r1_excluded", len(f["context_excluded"]), source=R + " → R1.facts.context_excluded")
    F.add("r1_selected", len(f["context_selected"]), source=R + " → R1.facts.context_selected")
    f = FX["R2"]
    for layer in ("user", "agent", "delegation", "workload", "environment"):
        F.add(f"r2_{'env' if layer == 'environment' else layer}_perms", f["layers"][layer], source=R + f" → R2.facts.layers.{layer}")
    F.add("r2_effective", len(f["effective"]), source=R + " → R2.facts.effective")
    F.add("r2_user_rollback", len(f["user_rollback"]), source=R + " → R2.facts.user_rollback")
    f = FX["R3"]
    F.add("r3_approved_digest", f["approved_digest"], source=R + " → R3.facts.approved_digest")
    F.add("r3_tampered_digest", f["tampered_digest"], source=R + " → R3.facts.tampered_digest")
    F.add("r3_approved_short", f["approved_digest"][:16], source=R + " → R3.facts.approved_digest")
    F.add("r3_tampered_short", f["tampered_digest"][:16], source=R + " → R3.facts.tampered_digest")
    F.add("r3_attacks", len(f["attacks"]), source=R + " → R3.facts.attacks")
    f = FX["R4"]
    F.add("r4_exposed", f["n_exposed"], source=R + " → R4.facts.n_exposed")
    F.add("r4_offered", len(f["offered"]), source=R + " → R4.facts.offered")
    f = FX["R5"]
    F.add("r5_cases", len(f["cases"]), source=R + " → R5.facts.cases")
    F.add("r5_denied", sum(1 for v in f["cases"].values() if v[0] == "DENIED"), source=R + " → R5.facts.cases", derivation="cases refused by the release server")
    F.add("r5_ttl", f["claims"]["exp"] - f["claims"]["iat"], source=R + " → R5.facts.claims", unit="s", derivation="exp − iat")
    f = FX["R6"]
    F.add("r6_limit", f["error"]["limit"], source=R + " → R6.facts.error.limit")
    F.add("r6_cap", f["error"]["cap"], source=R + " → R6.facts.error.cap")
    F.add("r6_model_calls", int(f["usage"]["model_call"]), source=R + " → R6.facts.usage.model_call")
    F.add("r6_tool_calls", int(f["usage"]["tool_call"]), source=R + " → R6.facts.usage.tool_call")
    F.add("r6_max_tool_calls", f["limits"]["max_tool_calls"], source=R + " → R6.facts.limits.max_tool_calls")
    F.add("r6_max_cost", f["limits"]["max_cost_units"], source=R + " → R6.facts.limits.max_cost_units")
    F.add("r6_max_steps", f["limits"]["max_workflow_steps"], source=R + " → R6.facts.limits.max_workflow_steps")
    F.add("r7_calls", len(FX["R7"]["routes"]), source=R + " → R7.facts.routes")
    F.add("r8_selected", len(FX["R8"]["selected"]), source=R + " → R8.facts.selected")
    F.add("r8_excluded", len(FX["R8"]["excluded"]), source=R + " → R8.facts.excluded")
    F.add("r9_processes", len(FX["R9"]["pids"]), source=R + " → R9.facts.pids")
    for m in ("lookup", "resend", "naive"):
        F.add(f"r10_{m}_rollbacks", FX["R10"][m]["rollbacks"], source=R + f" → R10.facts.{m}.rollbacks")
    F.add("r11_before", FX["R11"]["bundle_before"], source=R + " → R11.facts.bundle_before")
    F.add("r11_after", FX["R11"]["bundle_after"], source=R + " → R11.facts.bundle_after")
    f = FX["R13"]
    F.add("r13_questions", f["questions"], source=R + " → R13.facts.questions")
    F.add("r13_events", f["events"], source=R + " → R13.facts.events")
    F.add("r13_spans", f["spans"], source=R + " → R13.facts.spans")
    X = {c["id"]: c for c in res.get("cross_checks", [])}
    F.add("x_prompts", int(X["X.canary"]["detail"].split()[0]), source=R + " → cross_checks[X.canary].detail")
    F.add("x_files", int(X["X.keys"]["detail"].split()[0]), source=R + " → cross_checks[X.keys].detail")
    F.add("x_chains", int(X["X.chains"]["detail"].split()[0]), source=R + " → cross_checks[X.chains].detail")
    F.add("x_chain_events", int(X["X.chains"]["detail"].split()[2]), source=R + " → cross_checks[X.chains].detail")

    # ---- recomputed from the raw files, independently of the harness ------------------------------------------------
    exp_dir = raw / "experiments"
    dbs = sorted(exp_dir.rglob("world.db"))
    per = {}
    for db in dbs:
        per.setdefault(db.relative_to(exp_dir).parts[0], 0)
        per[db.relative_to(exp_dir).parts[0]] += rollbacks(db)
    for eid, n in sorted(per.items()):
        F.add(f"raw.rollbacks.{eid}", n, source=f"{base}/experiments/{eid}/**/world.db → rollbacks",
              derivation="rows in the simulated release pipeline's own rollbacks table, summed over the experiment's directories")
    chains = sorted(exp_dir.rglob("audit.jsonl"))
    from agentic_platform.observability import verify_chain  # the POC's own chain verification, run on the shipped files
    F.add("raw.audit_chains", len(chains), source=f"{base}/experiments/**/audit.jsonl")
    F.add("raw.audit_chains_verified", sum(verify_chain(p)[0] for p in chains), source=f"{base}/experiments/**/audit.jsonl",
          derivation="each event's hash recomputed from the previous one")
    killed = 0
    for ev in sorted(exp_dir.rglob("events.jsonl")):
        types = [r["event_type"] for r in rows(ev)]
        killed += types.count("process.started") - types.count("process.finished") - types.count("workflow.parked")
    F.add("raw.sigkills", killed, source=f"{base}/experiments/**/events.jsonl",
          derivation="processes that started and neither finished nor parked: each was SIGKILLed at its crash point")
    traces = {r["trace_id"] for r in rows(exp_dir / "R1" / "audit.jsonl")} | {s["trace_id"] for s in rows(exp_dir / "R1" / "trace.jsonl")}
    F.add("raw.r1_trace_ids", len(traces), source=f"{base}/experiments/R1/{{audit,trace}}.jsonl", derivation="distinct trace ids")

    # ---- replay and the negative control ----------------------------------------------------------------------------
    rp = run / "replay.json"
    replay = read(rp) if rp.exists() else None
    if replay:
        src = f"evidence/runs/{run_id}/replay.json"
        F.add("replay.level", replay["replay_level"], source=src)
        F.add("replay_run", replay["b"]["run"], source=src + " → b.run")
        F.add("replay.rows", replay["rows"], source=src)
        F.add("replay.equivalent", replay["equivalent"], source=src)
        for k, v in replay["classes"].items():
            F.add(f"replay.{k.lower()}", v, source=src + f" → classes.{k}")
        F.add("replay_checks_compared", replay["groups"]["checks"]["rows"], source=src + " → groups.checks")
        F.add("replay_checks_identical", replay["groups"]["checks"]["deterministic_equivalent"], source=src + " → groups.checks")
        F.add("replay_ids_compared", replay["groups"]["ids"]["rows"], source=src + " → groups.ids")
        F.add("replay_ids_identical", replay["groups"]["ids"]["deterministic_equivalent"], source=src + " → groups.ids")
    pp = run / "previous-run-comparison.json"
    if pp.exists():   # the published run this one replaced, against it (two formats: compare_runs.py before the contract, replay_compare.py after)
        prev, src = read(pp), f"evidence/runs/{run_id}/previous-run-comparison.json"
        if "groups" in prev:
            g = prev["groups"]
            F.add("prev_run", prev["a"]["run"], source=src + " → a.run")
            F.add("prev_checks_compared", g["checks"]["rows"], source=src + " → groups.checks.rows")
            F.add("prev_checks_identical", g["checks"]["identical"], source=src + " → groups.checks.identical")
            F.add("prev_checks_different", ", ".join(g["checks"]["different"]) or "none", source=src + " → groups.checks.different")
            F.add("prev_new_checks", len(g["checks"]["only_in_new"]), source=src + " → groups.checks.only_in_new")
            F.add("prev_ids_identical", g["ids"]["identical"], source=src + " → groups.ids.identical")
        else:
            F.add("prev_run", prev["run_a"], source=src + " → run_a")
            F.add("prev_checks_compared", prev["checks_compared"], source=src + " → checks_compared")
            F.add("prev_checks_identical", prev["checks_identical"], source=src + " → checks_identical")
            F.add("prev_checks_different", ", ".join(prev["checks_different"]) or "none", source=src + " → checks_different")
            F.add("prev_ids_identical", prev["ids_identical"], source=src + " → ids_identical")
    nraw = run / "negative-control" / "raw"
    if (nraw / "results.json").exists():
        nres, src = read(nraw / "results.json"), f"evidence/runs/{run_id}/negative-control/raw/results.json"
        nchk = {c["id"]: c for e in nres["experiments"] for c in e["checks"]} | {c["id"]: c for c in nres.get("cross_checks", [])}
        failed = [e for e in nres["experiments"] if e["status"] == "FAIL"]
        F.add("neg_checks", nres["totals"]["checks"], source=src + " → totals.checks")
        F.add("neg_checks_failed", nres["totals"]["failed"], source=src + " → totals.failed")
        F.add("neg_experiments_failed", len(failed), source=src + " → experiments[].status")
        F.add("neg_experiments_passed", nres["totals"]["experiments_passed"], source=src + " → totals.experiments_passed")
        F.add("neg_failed_experiments", ", ".join(e["id"] for e in failed), source=src + " → experiments[].status")
        exc = nres.get("harness_exceptions")
        F.add("neg_harness_exceptions", len(exc) if exc is not None else sum(c["id"].endswith(".completed") and "exception" in str(c["expected"])
                                                                               for c in nchk.values()),
              source=src + " → harness_exceptions", derivation="experiments that stopped on an exception instead of reporting")
        F.add("negctl.policy_decision", scalar(nchk["R1.policy"]["actual"]).split(" · ")[0] if "R1.policy" in nchk else "not reached",
              source=src + " → R1.checks[R1.policy].actual", derivation="the policy decision for the production rollback, with the safeguard removed")
        F.add("negctl.parked", nchk["R1.parked"]["actual"] if "R1.parked" in nchk else "not reached", source=src + " → R1.checks[R1.parked].actual")
        w = nchk.get("R1.world", {}).get("actual") or [None]
        appr = nchk.get("R1.approval", {}).get("actual") or [None, None, None]
        F.add("negctl.unapproved_rollbacks", (w[0] or 0) if appr[1] is None else 0, source=src + " → R1.checks[R1.world, R1.approval].actual",
              derivation="production rollbacks R1 executed with no approval validated")
        ctl = nraw / "control.json"
        if ctl.exists():
            c = read(ctl)
            F.add("negctl.proof_exit_code", c["proof_exit_code"], source=f"evidence/runs/{run_id}/negative-control/raw/control.json")
    return F, {"res": res, "replay": replay, "run": run}
