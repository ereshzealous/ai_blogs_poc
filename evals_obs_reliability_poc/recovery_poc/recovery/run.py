"""The recorded run: every experiment of the preregistration, into runs/<run-id>/, then its facts.

    python -m recovery.run record --run-id 2026-10-07-recorded [--live]      (--live: the real-model slice via Ollama)
    python -m recovery.run aggregate --run-id <id>                            (facts.json + reports from the raw files)

Layout of a run:
    scenarios/<S>/<arm>/      one scenario x one runtime: world/ (ledger, access log), journal.json, events.jsonl,
                              telemetry/spans.jsonl, workers.json, eval.json, volatile/ (wall times, pids: never compared)
    mutants/<X>/<S>/          A2 with one preregistered mutation (H8; X1 is the negative control)
    model-change/             scripted-v1 vs scripted-v2: offline scores and gate (H9), and v2 through the runtime (S00)
    model-slice/              the real-model tape, its scores and the gate (H10, H11)
    facts.json  reports/  summary.md  manifest.json
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import modelslice
from .common import FROZEN_FILES, POC, RUNS, prereg, prereg_check, read_json, read_jsonl, scenarios, sha256, write_json, write_jsonl
from .evals import CHECKS, FAMILY, TITLE, evaluate
from .harness import run_one

ARMS = ["A0", "A1", "A2"]
MUTANTS = [m["id"] for m in prereg()["mutants"]]
TERMINAL = ("AUTHORIZATION_DENIED", "TOOL_REJECTED", "ARGUMENT_VALIDATION", "TOOL_SELECTION_INVALID")
JOBS = 8


def job(out: Path, sc: dict, arm: str, mutant: str | None = None, model_change: str | None = None, live: str | None = None) -> str:
    run_one(out, sc, arm, mutant=mutant, model_change=model_change, live=live)
    e = evaluate(out, sc, arm)
    write_json(out / "eval.json", e)
    return f"{sc['id']} {arm}{' ' + mutant if mutant else ''}{' ' + model_change if model_change else ''}"


def record(run_id: str, live: bool, only: str | None = None) -> Path:
    probs = prereg_check()
    if probs:
        raise SystemExit("preregistration changed since the freeze:\n  " + "\n  ".join(probs))
    run = RUNS / run_id
    if run.exists() and not only:
        raise SystemExit(f"{run} exists: a recorded run is never overwritten (pick a new run id)")
    run.mkdir(parents=True, exist_ok=True)
    sc = scenarios()
    tasks = []
    if only in (None, "scenarios"):
        tasks += [(run / "scenarios" / s["id"] / a, s, a, None, None) for s in sc for a in ARMS]
    if only in (None, "mutants"):
        tasks += [(run / "mutants" / m / s["id"], s, "A2", m, None) for m in MUTANTS for s in sc]
    if only in (None, "model-change"):
        s00 = next(s for s in sc if s["id"] == "S00")
        tasks += [(run / "model-change" / "runtime" / f"S00-{a}", s00, a, None, "scripted-v2") for a in ARMS]
    with ThreadPoolExecutor(JOBS) as ex:
        for i, label in enumerate(ex.map(lambda t: job(*t), tasks), 1):
            print(f"[{i}/{len(tasks)}] {label}", flush=True)
    if only in (None, "model-change"):
        rows = modelslice.scripted_tape("scripted-v1") + modelslice.scripted_tape("scripted-v2")
        write_jsonl(run / "model-change" / "tape.jsonl", rows)
        sc_ = modelslice.score(rows)
        write_json(run / "model-change" / "scores.json", sc_["metrics"])
        write_jsonl(run / "model-change" / "scored.jsonl", sc_["rows"])
        write_json(run / "model-change" / "gate.json", modelslice.gate(sc_["metrics"]))
    if live and only in (None, "model-slice"):
        p = prereg()["model_slice"]
        models = [p["baseline"], "llama3.1:latest"]      # DEVIATIONS.md D2: the local tag of the preregistered llama3.1:8b
        tape = modelslice.record_tape(run / "model-slice", models)
        score_slice(run)
    manifest(run, live)
    return run


# ---- the real-model end-to-end run ---------------------------------------------------------------------------------------
LIVE_JOBS = 3      # the local model server answers one request at a time; more workers only queue


def record_live(run_id: str, mode: str = "record", source: Path | None = None) -> Path:
    """Every scenario x runtime with a real model deciding (qwen3:8b; fallback llama3.1).  mode=replay re-runs it from a tape copy."""
    probs = prereg_check()
    if probs:
        raise SystemExit("preregistration changed since the freeze:\n  " + "\n  ".join(probs))
    run = RUNS / run_id
    if mode == "record" and run.exists():
        raise SystemExit(f"{run} exists: a recorded run is never overwritten")
    sc = scenarios()
    tasks = []
    for s in sc:
        for a in ARMS:
            out = run / "scenarios" / s["id"] / a
            if mode == "replay":
                out.mkdir(parents=True, exist_ok=True)
                src_tape = source / "scenarios" / s["id"] / a / "model-tape.jsonl"
                if src_tape.exists():                       # no tape: the run made no model call (S02 without a fallback)
                    shutil.copy(src_tape, out / "model-tape.jsonl")
            tasks.append((out, s, a, None, None, mode))
    with ThreadPoolExecutor(LIVE_JOBS) as ex:
        for i, label in enumerate(ex.map(lambda t: job(*t), tasks), 1):
            print(f"[{i}/{len(tasks)}] {label}", flush=True)
    from .runtime import LIVE_FALLBACK, LIVE_PRIMARY
    from .modelslice import model_digest
    write_json(run / "manifest.json", {"run_id": run_id, "kind": "real-model end-to-end", "python": platform.python_version(),
                                       "platform": f"{platform.system()} {platform.machine()}", "mode": mode,
                                       "source_sha256": {str(p.relative_to(POC)): sha256(p.read_bytes()) for p in sorted((POC / "recovery").glob("*.py"))},
                                       "models": {m: model_digest(m) for m in (LIVE_PRIMARY, LIVE_FALLBACK)} if mode == "record" else "see the recorded run",
                                       "temperature": 0.0, "seed": 1, "scenarios": [s["id"] for s in sc], "arms": ARMS})
    return run


def aggregate_live(run: Path) -> dict:
    """facts.json of the real-model run: the same per-runtime measures as the deterministic run, plus what the model did."""
    sc = {s["id"]: s for s in scenarios()}
    base = f"recovery_poc/runs/{run.name}"
    F: dict = {}

    def fact(k, v, src, note=None):
        F[k] = {"value": v, "source": src, **({"derivation": note} if note else {})}

    rows, tape = [], []
    for sid in sorted(sc):
        for arm in ARMS:
            d = run / "scenarios" / sid / arm
            rows.append({"scenario": sid, "arm": arm, "eval": read_json(d / "eval.json"), "events": read_jsonl(d / "events.jsonl"),
                         "ledger": read_json(d / "world" / "ledger.json")})
            tape += [dict(r, scenario=sid, arm=arm) for r in read_jsonl(d / "model-tape.jsonl")]
    dup = lambda r: r["eval"]["checks"]["I1"]["result"] == "FAIL" or r["eval"]["checks"]["I2"]["result"] == "FAIL"   # noqa: E731
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm]
        src = f"{base}/scenarios/*/{arm}/eval.json"
        dups = [r["scenario"] for r in rs if dup(r)]
        fact(f"{arm}.dup_scenarios", len(dups), src)
        fact(f"{arm}.dup_list", ", ".join(dups) or "none", src)
        fact(f"{arm}.outcome_correct", sum(r["eval"]["checks"]["OE1"]["result"] == "PASS" for r in rs), src)
        fact(f"{arm}.false_claims", sum(r["eval"]["checks"]["I9"]["result"] == "FAIL" for r in rs), src)
        fact(f"{arm}.invariant_failures", sum(r["eval"]["checks"][c]["result"] == "FAIL" for r in rs for c in CHECKS if FAMILY[c] == "invariant"), src)
        safety = ("I1", "I2", "I3", "I4", "I6", "I7", "I9", "I11")
        fact(f"{arm}.safety_failures", sum(r["eval"]["checks"][c]["result"] == "FAIL" for r in rs for c in safety), src,
             "FAIL results of the safety invariants I1 I2 I3 I4 I6 I7 I9 I11")
        fact(f"{arm}.escalations", sum(r["eval"]["answer"]["status"] == "REQUIRES_HUMAN" for r in rs), src)
        fact(f"{arm}.denied", sum(r["eval"]["answer"]["status"] == "DENIED" for r in rs), src)
        fact(f"{arm}.trace_split", sum(r["eval"]["checks"]["I8"]["result"] == "FAIL" for r in rs), src)
        wrong = sum(1 for r in rs for c in r["ledger"]["credits"] if not c["charge_id"].endswith("_b") or c["amount"] > 200)
        fact(f"{arm}.unsafe_credits", wrong, f"{base}/scenarios/*/{arm}/world/ledger.json",
             "committed credits on a charge that is not the duplicate, or above the agent's limit")
    a2 = [r for r in rows if r["arm"] == "A2"]
    match = [r["scenario"] for r in a2 if r["eval"]["checks"]["RE1"]["result"] == "PASS"]
    miss = [r["scenario"] for r in a2 if r["eval"]["checks"]["RE1"]["result"] != "PASS"]
    fact("A2.re1_pass", len(match), f"{base}/scenarios/*/A2/eval.json", "A2 decision sequences equal to the scripted-model oracle")
    fact("A2.re1_miss_list", ", ".join(miss) or "none", f"{base}/scenarios/*/A2/eval.json")
    fact("A2.oe1_miss_list", ", ".join(r["scenario"] for r in a2 if r["eval"]["checks"]["OE1"]["result"] != "PASS") or "none", f"{base}/scenarios/*/A2/eval.json")
    tsrc = f"{base}/scenarios/*/*/model-tape.jsonl"
    fact("model.calls", len(tape), tsrc, "real model calls across all runs")
    fact("model.primary_calls", sum(t["model"] == "qwen3:8b" for t in tape), tsrc)
    fact("model.fallback_calls", sum(t["model"] != "qwen3:8b" for t in tape), tsrc)
    fact("model.repair_calls", sum(t["repair"] for t in tape), tsrc)
    by_prompt: dict = {}
    for t in tape:
        by_prompt.setdefault((t["model"], t["prompt_sha"]), set()).add(t["content"])
    fact("model.distinct_prompts", len(by_prompt), tsrc)
    fact("model.prompts_with_varying_output", sum(len(v) > 1 for v in by_prompt.values()), tsrc,
         "distinct prompts that received more than one different answer (temperature 0, seed 1)")
    props = []
    for t in tape:
        try:
            props.append(json.loads(t["content"]).get("tool"))
        except Exception:
            props.append("unparseable")
    for tool in sorted({p for p in props if p}):
        fact(f"model.proposed.{tool}", props.count(tool), tsrc)
    fact("scenarios", len(sc), "recovery_poc/experiments/scenarios.toml")
    fact("runs", len(rows), f"{base}/scenarios/")
    write_json(run / "facts.json", dict(sorted(F.items())))
    table = [{"scenario": r["scenario"], "arm": r["arm"], "status": r["eval"]["answer"]["status"], "effects": r["eval"]["effects"],
              "decisions": r["eval"]["decisions"], "fails": [c for c in CHECKS if r["eval"]["checks"][c]["result"] == "FAIL"]} for r in rows]
    write_json(run / "reports" / "scenarios.json", table)
    L = [f"# Real-model end-to-end run {run.name}", "", f"{len(rows)} runs ({len(sc)} scenarios x {len(ARMS)} runtimes), qwen3:8b deciding, "
         f"{F['model.calls']['value']} model calls.", "", "| | A0 | A1 | A2 |", "|---|---|---|---|"]
    for k in ("dup_scenarios", "outcome_correct", "false_claims", "safety_failures", "unsafe_credits", "escalations", "denied", "trace_split"):
        L.append(f"| {k} | {F['A0.' + k]['value']} | {F['A1.' + k]['value']} | {F['A2.' + k]['value']} |")
    L += ["", f"A2 decisions equal to the scripted-model oracle: {F['A2.re1_pass']['value']} of {len(sc)} (differ: {F['A2.re1_miss_list']['value']})."]
    (run / "summary.md").write_text("\n".join(L) + "\n")
    return F


def reevaluate(run: Path) -> int:
    """Recompute every eval.json of a recorded run from its raw files (the evaluator is analysis, not the run)."""
    sc = {s["id"]: s for s in scenarios()}
    n = 0
    for e in sorted(run.glob("**/eval.json")):
        d = e.parent
        rel = d.relative_to(run).parts
        if rel[0] == "scenarios":
            sid, arm = rel[1], rel[2]
        elif rel[0] == "mutants":
            sid, arm = rel[2], "A2"
        else:                                            # model-change/runtime/S00-A2
            sid, arm = rel[-1].split("-")
        write_json(e, evaluate(d, sc[sid], arm))
        n += 1
    print(f"re-evaluated {n} runs")
    return n


def score_slice(run: Path) -> None:
    rows = read_jsonl(run / "model-slice" / "tape.jsonl")
    s = modelslice.score(rows)
    write_json(run / "model-slice" / "scores.json", s["metrics"])
    write_jsonl(run / "model-slice" / "scored.jsonl", s["rows"])
    write_json(run / "model-slice" / "gate.json", modelslice.gate(s["metrics"]))


def manifest(run: Path, live: bool) -> None:
    src = {str(p.relative_to(POC)): sha256(p.read_bytes()) for p in sorted((POC / "recovery").glob("*.py"))}
    write_json(run / "manifest.json", {
        "run_id": run.name, "python": platform.python_version(), "platform": f"{platform.system()} {platform.machine()}",
        "source_sha256": src, "frozen_sha256": {f: sha256((POC / f).read_bytes()) for f in FROZEN_FILES},
        "live_model_slice": live, "arms": ARMS, "mutants": MUTANTS, "scenarios": [s["id"] for s in scenarios()],
        "models": read_json(run / "model-slice" / "models.json") if (run / "model-slice" / "models.json").exists() else {},
    })


# ---- aggregate ------------------------------------------------------------------------------------------------------
def aggregate(run: Path) -> dict:
    sc = {s["id"]: s for s in scenarios()}
    F: dict = {}
    base = f"recovery_poc/runs/{run.name}"

    def fact(k, v, src, note=None):
        F[k] = {"value": v, "source": src, **({"derivation": note} if note else {})}

    rows = []
    for sid in sorted(sc):
        for arm in ARMS:
            d = run / "scenarios" / sid / arm
            e = read_json(d / "eval.json")
            ev = read_jsonl(d / "events.jsonl")
            acc = read_jsonl(d / "world" / "access.jsonl")
            w = read_json(d / "workers.json")
            rows.append({"scenario": sid, "arm": arm, "eval": e, "events": ev, "access": acc, "workers": w})
    by = {(r["scenario"], r["arm"]): r for r in rows}

    def dup(r):
        return r["eval"]["checks"]["I1"]["result"] == "FAIL" or r["eval"]["checks"]["I2"]["result"] == "FAIL"

    completed_oracle = [s for s in sc if sc[s]["status"] == "COMPLETED"]
    table = []
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm]
        src = f"{base}/scenarios/*/{arm}/eval.json"
        dups = [r["scenario"] for r in rs if dup(r)]
        fact(f"{arm}.dup_scenarios", len(dups), src, "scenarios where I1 or I2 failed (a duplicate business effect)")
        fact(f"{arm}.dup_list", ", ".join(dups) or "none", src)
        excess = sum(max(0, r["eval"]["effects"]["credits_total"] - sc[r["scenario"]]["effects"]["credits"]) +
                     max(0, r["eval"]["effects"]["tickets"] - sc[r["scenario"]]["effects"]["tickets"]) +
                     max(0, r["eval"]["effects"]["notifications"] - sc[r["scenario"]]["effects"]["notifications"]) for r in rs)
        fact(f"{arm}.excess_effects", excess, src, "committed effects above the oracle's, summed over scenarios")
        fact(f"{arm}.excess_credits", sum(max(0, r["eval"]["effects"]["credits_total"] - sc[r["scenario"]]["effects"]["credits"]) for r in rs), src)
        fc = [r["scenario"] for r in rs if r["eval"]["checks"]["I9"]["result"] == "FAIL"]
        fact(f"{arm}.false_claims", len(fc), src, "scenarios where I9 failed")
        fact(f"{arm}.false_claim_list", ", ".join(fc) or "none", src)
        comp = [r["scenario"] for r in rs if r["scenario"] in completed_oracle and r["eval"]["checks"]["OE1"]["result"] == "PASS"]
        fact(f"{arm}.completed", len(comp), src, "oracle-COMPLETED scenarios finished with the oracle's status and effects")
        fact(f"{arm}.outcome_correct", sum(r["eval"]["checks"]["OE1"]["result"] == "PASS" for r in rs), src, "OE1 PASS over all scenarios")
        fact(f"{arm}.escalations", sum(r["eval"]["answer"]["status"] == "REQUIRES_HUMAN" for r in rs), src)
        fact(f"{arm}.failed_runs", sum(r["eval"]["answer"]["status"] == "FAILED" for r in rs), src)
        fact(f"{arm}.trace_split", sum(r["eval"]["checks"]["I8"]["result"] == "FAIL" for r in rs), src, "runs whose spans were not one trace with linked resumes")
        fails = [e for r in rs for e in r["events"] if e["kind"] == "failure"]
        diag = [e for e in fails if e.get("failure_class") and e.get("execution_certainty")]
        fact(f"{arm}.failure_events", len(fails), f"{base}/scenarios/*/{arm}/events.jsonl")
        fact(f"{arm}.failures_diagnosed", len(diag), f"{base}/scenarios/*/{arm}/events.jsonl", "failure events with a class and a certainty")
        if arm == "A2":
            tr = sum(1 for r in rs for e in r["events"] if e["kind"] == "decision" and e["action"] == "RETRY" and e["failure_class"] in TERMINAL)
        else:
            tr = sum(1 for sid in ("S05", "S06", "S07", "S13") for e in by[(sid, arm)]["events"] if e["kind"] == "failure" and e.get("attempt", 1) > 1)
        fact(f"{arm}.terminal_retries", tr, src, "re-attempts after a refusal no retry can change (selection, arguments, policy, business rule)")
        writes = sum(1 for r in rs for a in r["access"] if a["target"].startswith("tool:") and a["target"] != "tool:lookup_charges")
        fact(f"{arm}.write_requests", writes, f"{base}/scenarios/*/{arm}/world/access.jsonl", "write requests that reached a provider")
        sq = sum(1 for r in rs for a in r["access"] if a["target"].startswith("status:"))
        fact(f"{arm}.status_queries", sq, f"{base}/scenarios/*/{arm}/world/access.jsonl", "reconciliation queries")
        workers = sum(len(r["workers"]) for r in rs)
        fact(f"{arm}.workers", workers, f"{base}/scenarios/*/{arm}/workers.json")
        fact(f"{arm}.sigkills", sum(1 for r in rs for x in r["workers"] if x["signal"] == "SIGKILL"), f"{base}/scenarios/*/{arm}/workers.json")
        fact(f"{arm}.failstops", sum(1 for r in rs for x in r["workers"] if x["exit"] == 75), f"{base}/scenarios/*/{arm}/workers.json")
        anomalies = [f"{r['scenario']}:{x['worker']}:{x['exit']}" for r in rs for x in r["workers"] if x["exit"] not in (0, -9, 75)]
        fact(f"{arm}.anomalies", len(anomalies), f"{base}/scenarios/*/{arm}/workers.json")
        for c in CHECKS:
            cnt = {k: sum(r["eval"]["checks"][c]["result"] == k for r in rs) for k in ("PASS", "FAIL", "NA")}
            fact(f"{arm}.{c}.pass", cnt["PASS"], src)
            fact(f"{arm}.{c}.fail", cnt["FAIL"], src)
            fact(f"{arm}.{c}.na", cnt["NA"], src)
        inv_fail = sum(r["eval"]["checks"][c]["result"] == "FAIL" for r in rs for c in CHECKS if FAMILY[c] == "invariant")
        fact(f"{arm}.invariant_failures", inv_fail, src, "FAIL results of I1–I12 over every scenario")
        fact(f"{arm}.eval_failures", sum(r["eval"]["checks"][c]["result"] == "FAIL" for r in rs for c in CHECKS), src)
        for r in rs:
            e, s = r["eval"], r["scenario"]
            k = f"{s}.{arm}"
            fact(f"{k}.credits", e["effects"]["credits_total"], f"{base}/scenarios/{s}/{arm}/world/ledger.json")
            fact(f"{k}.tickets", e["effects"]["tickets"], f"{base}/scenarios/{s}/{arm}/world/ledger.json")
            fact(f"{k}.notifications", e["effects"]["notifications"], f"{base}/scenarios/{s}/{arm}/world/ledger.json")
            fact(f"{k}.status", e["answer"]["status"], f"{base}/scenarios/{s}/{arm}/events.jsonl")
            fact(f"{k}.requests", sum(1 for a in r["access"] if a["target"] == "tool:issue_credit"), f"{base}/scenarios/{s}/{arm}/world/access.jsonl")
            table.append({"scenario": s, "arm": arm, "title": sc[s]["title"], "layer": sc[s]["layer"], "status": e["answer"]["status"],
                          "effects": e["effects"], "claims": e["answer"]["claims"], "decisions": e["decisions"],
                          "fails": [c for c in CHECKS if e["checks"][c]["result"] == "FAIL"], "duplicate": dup(r)})
    a2 = [r for r in rows if r["arm"] == "A2"]
    fact("A2.re1_pass", sum(r["eval"]["checks"]["RE1"]["result"] == "PASS" for r in a2), f"{base}/scenarios/*/A2/eval.json", "decision sequences equal to the oracle")
    fact("A2.decisions", sum(len(r["eval"]["decisions"]) for r in a2), f"{base}/scenarios/*/A2/events.jsonl")
    fact("A2.unnecessary_escalations", sum(r["eval"]["answer"]["status"] == "REQUIRES_HUMAN" and sc[r["scenario"]]["status"] != "REQUIRES_HUMAN" for r in a2),
         f"{base}/scenarios/*/A2/eval.json")
    fact("scenarios", len(sc), "recovery_poc/experiments/scenarios.toml")
    fact("arms", len(ARMS), "recovery_poc/experiments/preregistration.toml")
    fact("runs.deterministic", len(rows), f"{base}/scenarios/")
    fact("oracle.completed", len(completed_oracle), "recovery_poc/experiments/scenarios.toml")
    fact("oracle.escalate", sum(sc[s]["status"] == "REQUIRES_HUMAN" for s in sc), "recovery_poc/experiments/scenarios.toml")
    fact("checks.per_run", len(CHECKS), "recovery_poc/recovery/evals.py")
    acts = {}
    for r in a2:
        for d in r["eval"]["decisions"]:
            acts[d[2]] = acts.get(d[2], 0) + 1
    for a, n in acts.items():
        fact(f"A2.action.{a}", n, f"{base}/scenarios/*/A2/events.jsonl")
    fact("A2.actions_used", len(acts), f"{base}/scenarios/*/A2/events.jsonl")
    classes = {d[0] for r in a2 for d in r["eval"]["decisions"]}
    fact("A2.classes_seen", len(classes), f"{base}/scenarios/*/A2/events.jsonl")

    # flagship (S09) identifiers and the timeline the figures draw
    fl = run / "scenarios" / "S09" / "A2"
    fev = read_jsonl(fl / "events.jsonl")
    disp = [e for e in fev if e["kind"] == "tool.dispatch" and e["step"] == "credit"]
    fail = next(e for e in fev if e["kind"] == "failure" and e["step"] == "credit")
    rec = next(e for e in fev if e["kind"] == "reconcile")
    led = read_json(fl / "world" / "ledger.json")
    src = f"{base}/scenarios/S09/A2/events.jsonl"
    fact("S09.op_id", disp[0]["operation_id"], src)
    fact("S09.attempt_id", disp[0]["attempt_id"], src)
    fact("S09.credit_id", led["credits"][0]["credit_id"], f"{base}/scenarios/S09/A2/world/ledger.json")
    fact("S09.certainty_rule", fail["certainty_rule"], src)
    fact("S09.transport", fail["transport"], src)
    fact("S09.dispatches.A2", len(disp), src)
    fact("S09.decision_rule", next(e for e in fev if e["kind"] == "decision")["rule"], src)
    fact("S09.reconcile_found", rec["found"], src)
    fact("S09.dispatches.A0", sum(1 for e in by[("S09", "A0")]["events"] if e["kind"] == "tool.dispatch" and e["step"] == "credit"), f"{base}/scenarios/S09/A0/events.jsonl")
    fact("S09.dispatches.A1", sum(1 for e in by[("S09", "A1")]["events"] if e["kind"] == "tool.dispatch" and e["step"] == "credit"), f"{base}/scenarios/S09/A1/events.jsonl")
    fact("S09.A1.replayed", sum(1 for a in by[("S09", "A1")]["access"] if a["outcome"] == "REPLAYED"), f"{base}/scenarios/S09/A1/world/access.jsonl")
    fact("S10.A0.requests", sum(1 for a in by[("S10", "A0")]["access"] if a["target"] == "tool:issue_credit"), f"{base}/scenarios/S10/A0/world/access.jsonl")
    spans = read_jsonl(run / "scenarios" / "S16" / "A2" / "telemetry" / "spans.jsonl")
    fact("S16.A2.traces", len({s["trace_id"] for s in spans}), f"{base}/scenarios/S16/A2/telemetry/spans.jsonl")
    fact("S16.A2.spans", len(spans), f"{base}/scenarios/S16/A2/telemetry/spans.jsonl")
    fact("S16.A2.trace_id", spans[0]["trace_id"][:16], f"{base}/scenarios/S16/A2/telemetry/spans.jsonl")
    fact("S16.A0.traces", len({s["trace_id"] for s in read_jsonl(run / "scenarios" / "S16" / "A0" / "telemetry" / "spans.jsonl")}),
         f"{base}/scenarios/S16/A0/telemetry/spans.jsonl")
    cfg = __import__("recovery.common", fromlist=["world_config"]).world_config()
    fact("cfg.client_timeout_ms", cfg["client_timeout_ms"], "recovery_poc/config/world.toml")
    fact("cfg.lost_response_hold_ms", cfg["lost_response_hold_ms"], "recovery_poc/config/world.toml")
    fact("cfg.request_deadline_ms", cfg["request_deadline_ms"], "recovery_poc/config/world.toml")
    fact("cfg.idempotency_ttl_s", 86400, "recovery_poc/config/tools.toml")
    fact("cfg.S18_outage_s", 90000, "recovery_poc/experiments/scenarios.toml")
    m = __import__("recovery.common", fromlist=["matrix"]).matrix()
    fact("matrix.rules", len(m["rules"]), "recovery_poc/config/recovery-matrix.toml")
    fact("matrix.certainty_rules", len(m["certainty"]), "recovery_poc/config/recovery-matrix.toml")
    fact("matrix.version", m["version"], "recovery_poc/config/recovery-matrix.toml")
    fact("taxonomy.classes", len([c for c in __import__("recovery.taxonomy", fromlist=["LAYER"]).LAYER if c != "GENERIC_ERROR"]), "recovery_poc/recovery/taxonomy.py")

    # mutants (H8) and the negative control (X1)
    mut_rows = []
    detected = 0
    for mid in MUTANTS:
        es = {sid: read_json(run / "mutants" / mid / sid / "eval.json") for sid in sorted(sc)}
        failing = {sid: [c for c in CHECKS if e["checks"][c]["result"] == "FAIL"] for sid, e in es.items()}
        failing = {k: v for k, v in failing.items() if v}
        by_check = sorted({c for v in failing.values() for c in v})
        dups = [sid for sid, e in es.items() if e["checks"]["I1"]["result"] == "FAIL" or e["checks"]["I2"]["result"] == "FAIL"]
        detected += bool(failing)
        src = f"{base}/mutants/{mid}/*/eval.json"
        fact(f"mut.{mid}.scenarios_failed", len(failing), src)
        fact(f"mut.{mid}.checks", ", ".join(by_check), src)
        fact(f"mut.{mid}.dups", len(dups), src)
        name = next(x["name"] for x in prereg()["mutants"] if x["id"] == mid)
        mut_rows.append({"id": mid, "name": name, "scenarios_failed": len(failing), "checks": by_check, "duplicates": dups, "failing": failing})
    fact("mut.detected", detected, f"{base}/mutants/*/*/eval.json", "mutants that failed at least one check in at least one scenario")
    fact("mut.total", len(MUTANTS), "recovery_poc/experiments/preregistration.toml")
    s09x1 = read_json(run / "mutants" / "X1" / "S09" / "eval.json")
    fact("mut.X1.S09.credits", s09x1["effects"]["credits_total"], f"{base}/mutants/X1/S09/eval.json")
    fact("mut.X1.S09.failing", ", ".join(c for c in CHECKS if s09x1["checks"][c]["result"] == "FAIL"), f"{base}/mutants/X1/S09/eval.json")
    x1 = [r for r in mut_rows if r["id"] == "X1"][0]
    x1_runs = [read_json(run / "mutants" / "X1" / sid / "workers.json") for sid in sorted(sc)]
    fact("nc.harness_completed", sum(all(w["exit"] in (0, -9, 75) for w in ws) for ws in x1_runs), f"{base}/mutants/X1/*/workers.json")
    fact("nc.dup_scenarios", len(x1["duplicates"]), f"{base}/mutants/X1/*/eval.json")
    fact("nc.dup_list", ", ".join(x1["duplicates"]), f"{base}/mutants/X1/*/eval.json")

    # model change (H9)
    mc = run / "model-change"
    if (mc / "gate.json").exists():
        g = read_json(mc / "gate.json")
        scores = read_json(mc / "scores.json")
        for mod, key in (("scripted-v1", "v1"), ("scripted-v2", "v2")):
            fact(f"mc.{key}.gate", g[mod]["decision"], f"{base}/model-change/gate.json")
            b = scores[mod]["all"]
            fact(f"mc.{key}.arguments", b["arguments_exact"], f"{base}/model-change/scores.json")
            fact(f"mc.{key}.n", b["n"], f"{base}/model-change/scores.json")
            fact(f"mc.{key}.unsafe", b["unsafe_proposal"], f"{base}/model-change/scores.json")
            fact(f"mc.{key}.unsafe_executed", b["unsafe_executed"], f"{base}/model-change/scores.json")
            fact(f"mc.{key}.blind_args_pct", round(100 * g[mod]["rates"]["arguments_exact"]), f"{base}/model-change/gate.json")
        for arm in ARMS:
            e = read_json(mc / "runtime" / f"S00-{arm}" / "eval.json")
            fact(f"mc.runtime.{arm}.status", e["answer"]["status"], f"{base}/model-change/runtime/S00-{arm}/eval.json")
            fact(f"mc.runtime.{arm}.credits", e["effects"]["credits_total"], f"{base}/model-change/runtime/S00-{arm}/eval.json")
            fact(f"mc.runtime.{arm}.invariant_failures", sum(e["checks"][c]["result"] == "FAIL" for c in CHECKS if FAMILY[c] == "invariant"),
                 f"{base}/model-change/runtime/S00-{arm}/eval.json")
        e2 = read_json(mc / "runtime" / "S00-A2" / "eval.json")
        fact("mc.runtime.A2.decisions", " → ".join(d[2] for d in e2["decisions"]), f"{base}/model-change/runtime/S00-A2/eval.json")

    # the real-model slice (H10, H11) and retrieval
    ms = run / "model-slice"
    if (ms / "gate.json").exists():
        g = read_json(ms / "gate.json")
        scores = read_json(ms / "scores.json")
        for mod in scores:
            key = "qwen" if mod.startswith("qwen") else "llama"
            fact(f"ms.{key}.model", mod, f"{base}/model-slice/scores.json")
            fact(f"ms.{key}.gate", g[mod]["decision"], f"{base}/model-slice/gate.json")
            fact(f"ms.{key}.missed", ", ".join(g[mod]["missed"]) or "none", f"{base}/model-slice/gate.json")
            for split in ("blind", "all", "dev"):
                b = scores[mod][split]
                for k in ("schema_valid", "tool_selection", "arguments_exact", "grounded_citation", "unsafe_proposal", "unsafe_executed",
                          "would_execute", "pass_k", "pass_1", "cases", "n", "anomalies"):
                    fact(f"ms.{key}.{split}.{k}", b[k], f"{base}/model-slice/scores.json")
                n = b["n"] or 1
                for k in ("schema_valid", "tool_selection", "arguments_exact", "grounded_citation"):
                    fact(f"ms.{key}.{split}.{k}_pct", round(100 * b[k] / n), f"{base}/model-slice/scores.json")
        tot_unsafe_exec = sum(scores[m]["all"]["unsafe_executed"] for m in scores)
        fact("ms.unsafe_executed_total", tot_unsafe_exec, f"{base}/model-slice/scores.json")
        fact("ms.unsafe_proposals_total", sum(scores[m]["all"]["unsafe_proposal"] for m in scores), f"{base}/model-slice/scores.json")
        fact("ms.calls", sum(scores[m]["all"]["n"] for m in scores), f"{base}/model-slice/tape.jsonl")
        fact("ms.tape_digest", modelslice.tape_digest(read_jsonl(ms / "tape.jsonl")), f"{base}/model-slice/tape.jsonl")
        models = read_json(ms / "models.json")
        for mod, v in models.items():
            fact(f"ms.digest.{'qwen' if mod.startswith('qwen') else 'llama'}", v["digest"][:12], f"{base}/model-slice/models.json")
    lab = modelslice.labels()
    hits = [c["id"] for c in modelslice.cases() if lab[c["id"]]["relevant_doc"] in [d["id"] for d in modelslice.retrieve(c)]]
    fact("retrieval.recall_at_3", len(hits), "recovery_poc/recovery/world.py search() over experiments/model_slice/cases.jsonl")
    fact("retrieval.cases", len(lab), "recovery_poc/experiments/model_slice/labels.jsonl")
    fact("retrieval.misses", ", ".join(sorted(set(lab) - set(hits))), "recovery_poc/recovery/world.py search()")

    F = dict(sorted(F.items()))
    write_json(run / "facts.json", F)
    write_json(run / "reports" / "scenarios.json", table)
    write_json(run / "reports" / "mutants.json", mut_rows)
    write_json(run / "reports" / "checks.json", {"checks": [{"id": c, "family": FAMILY[c], "title": TITLE[c]} for c in CHECKS]})
    summary(run, F, table, mut_rows)
    return F


def summary(run: Path, F: dict, table: list[dict], muts: list[dict]) -> None:
    v = lambda k: F[k]["value"]   # noqa: E731
    L = [f"# Run {run.name}", "", "R1+R2 · Evals, Observability & Production Reliability · recovery_poc", "",
         f"{v('scenarios')} scenarios × {v('arms')} runtimes = {v('runs.deterministic')} deterministic runs; {v('mut.total')} mutants × {v('scenarios')}; "
         "a deterministic model change; " + ("a real-model slice." if "ms.calls" in F else "no live model slice."), "",
         "| | A0 naive | A1 idempotent-retry | A2 classified |", "|---|---|---|---|"]
    for k, label in (("dup_scenarios", "scenarios with a duplicate effect"), ("excess_effects", "excess effects"),
                     ("false_claims", "false claims in the answer"), ("completed", f"completed (of {v('oracle.completed')})"),
                     ("escalations", "escalations"), ("terminal_retries", "retries of terminal refusals"),
                     ("trace_split", "runs split across traces"), ("invariant_failures", "invariant FAILs"), ("status_queries", "reconciliation queries")):
        L.append(f"| {label} | {v('A0.' + k)} | {v('A1.' + k)} | {v('A2.' + k)} |")
    L += ["", f"A2 decisions equal to the oracle: {v('A2.re1_pass')} of {v('scenarios')}.",
          f"Mutants detected: {v('mut.detected')} of {v('mut.total')}. Negative control (X1): duplicates in {v('nc.dup_scenarios')} scenarios ({v('nc.dup_list')}).", "",
          "| scenario | A0 | A1 | A2 | A2 decisions |", "|---|---|---|---|---|"]
    rows = {(r["scenario"], r["arm"]): r for r in table}
    for sid in sorted({r["scenario"] for r in table}):
        cell = lambda a: f"{rows[(sid, a)]['status']} c{rows[(sid, a)]['effects']['credits_total']}/t{rows[(sid, a)]['effects']['tickets']}/n{rows[(sid, a)]['effects']['notifications']}"  # noqa: E731
        L.append(f"| {sid} {rows[(sid, 'A2')]['title']} | {cell('A0')} | {cell('A1')} | {cell('A2')} | "
                 f"{' → '.join(d[2] for d in rows[(sid, 'A2')]['decisions']) or '—'} |")
    (run / "summary.md").write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["record", "aggregate", "score-slice", "reevaluate", "record-live", "replay-live", "aggregate-live"])
    ap.add_argument("--source", help="replay-live: the recorded live run whose tapes to replay")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--only")
    o = ap.parse_args()
    run = RUNS / o.run_id
    if o.cmd == "record":
        record(o.run_id, o.live, o.only)
        aggregate(run)
    elif o.cmd == "record-live":
        aggregate_live(record_live(o.run_id))
    elif o.cmd == "replay-live":
        aggregate_live(record_live(o.run_id, mode="replay", source=Path(o.source)))
    elif o.cmd == "aggregate-live":
        aggregate_live(run)
    elif o.cmd == "reevaluate":
        reevaluate(run)
        aggregate(run)
    elif o.cmd == "score-slice":
        score_slice(run)
        aggregate(run)
    else:
        aggregate(run)
    print(f"wrote {run.relative_to(POC)}/facts.json and summary.md")


if __name__ == "__main__":
    sys.exit(main())
