"""Build T5's Lab Console: every scenario, seen through each observation layer, with its input, output, answers, steps and lineage.

    python3 tools/build_lab_console.py [RUN_ID]      (make console; default: the published run, runs/PUBLISHED)
      -> results/lab-console.html                  one self-contained page (evidence-kit 4.1.0, as F1, F2, T1 and T3)
      -> results/lab-console.evidence.json         the canonical evidence it renders

Ported from T3's tools/build_lab_console.py.  A row is one scenario seen through one layer (L0 application logs, L1 logs +
traces, L2 execution lineage), so every scenario appears three times; the three rows share the scenario's recorded steps and
differ in the answers.  A row's outcome: Held when the layer answered all thirteen questions correctly; Qualified when some
answers were missing or partial but none was wrong; Broken when the layer recorded an answer that is false.  The words are
in tools/lab_console/learning.toml, where every number is a {{fact}}.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor" / "kit4"))
sys.path.insert(0, str(ROOT / "tools" / "lab_console"))
import evidence_kit as kit  # noqa: E402  (4.1.0, vendor/kit4)
from evidence_kit import blocks as B  # noqa: E402

import adapter as A  # noqa: E402

SPEC = ROOT / "tools" / "lab_console" / "learning.toml"
OUT = ROOT / "results" / "lab-console.html"
SEV = {"HELD": "none", "QUALIFIED": "qualified", "BROKEN": "broken"}
TONE = {"HELD": "ok", "QUALIFIED": "warn", "BROKEN": "bad"}
MARK = {"HELD": "✓", "QUALIFIED": "~", "BROKEN": "✕"}
FIRST = "e12a-lost-response"
VTONE = {"CORRECT": "ok", "INCOMPLETE": "warn", "UNANSWERABLE": "warn", "AMBIGUOUS": "warn", "WRONG": "bad"}
VLABEL = {"CORRECT": "correct", "INCOMPLETE": "partial", "UNANSWERABLE": "not recorded", "AMBIGUOUS": "ambiguous", "WRONG": "WRONG"}


def layer_outcome(verdicts: dict) -> str:
    if any(v == "WRONG" for v in verdicts.values()):
        return "BROKEN"
    return "HELD" if all(v == "CORRECT" for v in verdicts.values()) else "QUALIFIED"


def fmt(v) -> str:
    import re
    return re.sub(r"(sha256:[0-9a-f]{12})[0-9a-f]+", r"\1…", _fmt(v))


def _fmt(v) -> str:
    if v is None:
        return "—  (not recorded)"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, dict):
        return " · ".join(f"{k}={'—' if x is None else x}" for k, x in v.items())
    if isinstance(v, list):
        return ", ".join(" ".join(map(str, x)) if isinstance(x, list) else str(x) for x in v) or "none"
    return str(v)


def row_tabs(run: dict, sd: Path, S: dict, layer: str, ev: list[dict], spans: list[dict]) -> dict:
    res, rec, spec = S["result"], S["recon"][layer], S["spec"]
    case = A.CASES[sd.name]
    o = layer_outcome({q: a["verdict"] for q, a in rec["answers"].items()})
    x = spec["executions"]["target"]
    faults = ", ".join(f"{f['kind']} ×{f['times']}" for f in spec.get("faults", [])) or "none"
    inp = B.card(B.kv("Scenario", B.line("Scenario id", f"`{sd.name}`"), B.line("Group", case["group"]), B.line("Question", case["question"]),
                      B.line("Injected", faults + (f" · crash at `{x['crash_at']}`" if x.get("crash_at") else "")
                             + (" · step delivered twice" if x.get("redeliver_step") else "") + (" · compromised plan (SIMULATED)" if x.get("planner_override") else "")
                             + (f" · context request `{x['context_request']}`" if x.get("context_request") else "")),
                      B.line("Pins", f"`{x['policy']}` · `{x['agent_config']}` · severity {x['severity']} · idempotency {x['idempotency']}"),
                      B.line("Approvers (scripted)", "; ".join(f"{d['who']} {d['decision']}" for d in x["decisions"]))),
                 B.kv("Observed through", B.line("Layer", f"{layer} · {A.LAYERS[layer]}"), B.line("Sources read", ", ".join(rec["sources"])),
                      B.line("Joins", f"{rec['key_joins']} on keys · {rec['heuristic_joins']} on timestamps")),
                 title="Input", sub="What happened to the system, and what this investigator was allowed to read. The execution is the same for all three layers.")
    out = B.card(B.kv("Outcome", B.chips([(o, TONE[o])]), B.line("Correct answers", f"{sum(1 for a in rec['answers'].values() if a['verdict'] == 'CORRECT')}/13")),
                 B.kv("What happened (systems of record)", B.line("Recorded outcome", res["outcome"]), B.line("Production changed", f"{res['mutations']}×"),
                      B.line("Attempts reaching the API", str(res["attempts"])), B.line("Agent processes · SIGKILLs", f"{res['processes']} · {res['sigkills']}"),
                      B.line("Evidence chain", "intact" if res["evidence_intact"] else "BROKEN"), B.line("Recorded events (this execution, all layers)", str(len(ev))),
                      B.line("Spans in this execution's trace", str(len(spans)))),
                 title="Output", sub="Ground truth from the deployment API's and approval service's own databases; not from any layer under test.")
    qrows = [[B.cell(("code", q)), B.cell(("pill", VLABEL[a["verdict"]], VTONE[a["verdict"]])), B.cell(("text", A.QUESTIONS[q])),
              B.cell(("text", fmt(a["answer"]))), B.cell(("text", fmt(a["truth"])))] for q, a in rec["answers"].items()]
    answers = [B.callout(f"{o} · {layer} answered {sum(1 for a in rec['answers'].values() if a['verdict'] == 'CORRECT')} of 13 correctly"
                         + (" · it recorded a false answer" if o == "BROKEN" else ""), tone=TONE[o], icon="check" if o == "HELD" else "alert"),
               B.card(B.table(["Q", "Verdict", "Question", f"{layer}'s answer", "Truth"], qrows), title="Thirteen questions",
                      sub="Answered from this layer alone, by the rules in lineage/investigate.py; scored against truth.json."),
               B.card(B.table(["From", "To", "Joined on", "Kind"], [[B.cell(("text", j["from"])), B.cell(("text", j["to"])), B.cell(("text", j["on"])),
                                                                      B.cell(("pill", j["kind"], "ok" if j["kind"] == "key" else "warn"))] for j in rec["joins"]]),
                      title="Joins the investigator needed", sub="A key join uses an identifier both sides recorded; a heuristic join uses time or content.")]
    seen = [s for s in A.STEPS if any(e["step"] == s for e in ev)]
    srows = []
    for s in seen:
        es = [e for e in ev if e["step"] == s]
        c = Counter(e["layer"] for e in es)
        bad = any(e["tone"] == "bad" for e in es)
        srows.append([B.cell(("code", s)), B.cell(("pill", "failure / refusal recorded" if bad else "ok", "warn" if bad else "ok")),
                      B.cell(("text", ", ".join(f"{n} {k}" for k, n in c.items())))])
    tl = [{"n": i + 1, "tone": e["tone"], "text": f"`{e['ts'][11:23]}` [{e['layer']}] " + e["text"], "msg": None, "code": None,
           "notes": [f"source: `{e['src']}`"]} for i, e in enumerate(ev)]
    steps = [B.card(B.table(["Step", "Status", "Records (by layer)"], srows), title="Steps",
                    sub="trigger → context → model → policy → approval → tool → deploy API → verify → complete, as recorded by each layer and the system of record."),
             B.transcript(tl, "Every recorded event of this execution", f"{len(ev)} events in wall-clock order: L2 evidence, L0/L1 log lines, and the deployment API's own request log (truth).")]
    lrows = [[B.cell(("text", a)), B.cell(("code", f)), B.cell(("text", n)), B.cell(("text", d))] for a, f, n, d in A.lineage(run, sd)]
    lineage = [B.card(B.table(["Stage", "File (in the run)", ("Records", "n"), "Carries"], lrows), title="Data lineage",
                      sub="From the frozen inputs to the published number. Every file is in the run directory.")]
    return {"io": [B.grid(inp, out)], "answers": answers, "steps": steps, "lineage": lineage}


def collect(primary: str) -> tuple[dict, kit.Facts]:
    runs = A.discover(primary)
    assert runs and runs[0]["id"] == primary, f"run {primary} has no scored scenarios"
    P = runs[0]
    cases, traces, out_runs, per_run = {}, {}, [], {}
    for run in runs:
        rows, tr = [], {}
        for sd, S in A.scenarios(run):
            ev = A.events(sd)
            sp = A.spans(sd)
            c = A.CASES[sd.name]
            cases.setdefault(sd.name, {"group": ("flagship · " + c["group"]) if sd.name == FIRST else c["group"], "title": c["title"], "who": "the same execution, read three ways",
                                       "facts": [["Scenario", sd.name], ["Question", c["question"]]], "chips": []})
            for layer in A.LAYERS:
                rec = S["recon"][layer]
                verdicts = {q: a["verdict"] for q, a in rec["answers"].items()}
                o = layer_outcome(verdicts)
                wrong = [q for q, v in verdicts.items() if v == "WRONG"]
                gaps = [q for q, v in verdicts.items() if v != "CORRECT" and v != "WRONG"]
                note = (f"false answer to {', '.join(wrong)}" if wrong else "") + ("; " if wrong and gaps else "") + (f"not fully recorded: {', '.join(gaps)}" if gaps else "")
                rid = f"{sd.name}·{layer}"
                rows.append({"id": rid, "case": sd.name, "key": layer, "x": A.ORDER.index(sd.name) + 1, "pass": o == "HELD", "sev": SEV[o], "note": note or None,
                             "flags": [[f"{q} {A.QUESTIONS[q]}", v == "CORRECT"] for q, v in verdicts.items()],
                             "metrics": [["Correct", f"{13 - len(wrong) - len(gaps)}/13"], ["Wrong", str(len(wrong))], ["Partial / missing", str(len(gaps))],
                                         ["Key joins", str(rec["key_joins"])], ["Timestamp joins", str(rec["heuristic_joins"])], ["Sources", str(len(rec["sources"]))]],
                             "kv": [["Outcome", o], ["Layer", A.LAYERS[layer]], ["Scenario", sd.name], ["Group", ("flagship · " + c["group"]) if sd.name == FIRST else c["group"]],
                                    ["Production changed", f"{S['result']['mutations']}×"]],
                             "_o": o, "_ev": len(ev), "_S": S, "_wrong": wrong, "_gaps": gaps})
                tr[rid] = {"tabs": row_tabs(run, sd, S, layer, ev, sp)}
        rows.sort(key=lambda r: r["case"] != FIRST)      # the flagship first: the case a reader arriving from the articles wants
        per_run[run["id"]] = rows
        traces[run["id"]] = tr
        out_runs.append({"id": run["id"], "label": run["label"], "kind": run["kind"], "path": str(run["scen"].relative_to(ROOT)),
                         "note": "live model on tape; simulated deployment API, faults, incident and people; real processes, SIGKILL, HTTP, OpenTelemetry"
                         if run["kind"] == "recorded" else "replayed from the recorded model tape; no model called",
                         "rows": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]})
    rows = per_run[primary]
    checks = json.loads((P["dir"] / "checks.json").read_text())
    rep = json.loads((P["dir"] / "reports" / "replay-comparison.json").read_text()) if (P["dir"] / "reports" / "replay-comparison.json").exists() else {}
    F = json.loads((P["dir"] / "facts.json").read_text())
    env = json.loads((P["dir"] / "environment.json").read_text())
    facts = kit.Facts()
    add = facts.add
    src = f"observability_governance_poc/runs/{primary}/scenarios/*/reconstruction.json"
    add("run.id", primary, source=f"observability_governance_poc/runs/{primary}")
    add("run.filed", primary[:10], source="the run id")
    add("run.scenarios", len(rows) // 3, unit="scenarios", source=src)
    add("run.rows", len(rows), unit="rows", source=src)
    add("run.sources", len(runs), source="observability_governance_poc/runs/*")
    add("run.events", sum(r["_ev"] for r in rows) // 3, source="evidence + logs + world/external-transactions.json")
    add("run.model", "qwen3:8b", source="config/control_plane.toml → agent_configs")
    add("run.python", env["python"], source="environment.json → python")
    add("checks.passed", sum(c["pass"] for c in checks), source="checks.json")
    add("checks.total", len(checks), source="checks.json")
    add("replay.served", rep.get("answers_served", "n/a"), source="reports/replay-comparison.json")
    add("replay.misses", rep.get("tape_misses", "n/a"), source="reports/replay-comparison.json")
    add("replay.identical", "identical" if rep.get("all_identical") else "NOT identical", source="reports/replay-comparison.json")
    add("pred.held", F["predictions_held"]["value"], source="facts.json")
    add("pred.total", F["predictions"]["value"], source="facts.json")
    add("exp.held", F["expectations_held"]["value"], source="facts.json")
    add("exp.total", F["expectations"]["value"], source="facts.json")
    for L in A.LAYERS:
        lr = [r for r in rows if r["key"] == L]
        add(f"{L}.correct", F[f"{L}_correct_total"]["value"], source="facts.json")
        add(f"{L}.answers", F["answers_per_layer"]["value"], source="facts.json")
        for o, lab in (("HELD", "held"), ("QUALIFIED", "qualified"), ("BROKEN", "broken")):
            ids = [r["id"] for r in lr if r["_o"] == o]
            add(f"{L}.{lab}", len(ids), rows={"run": primary, "ids": ids} if ids else None, denominator=len(lr),
                derivation=f"{A.LAYERS[L]} rows with outcome {o}", source=src)
            add(f"{L}.{lab}.kn", f"{len(ids)}/{len(lr)}", source=src)
    for o, lab in (("HELD", "held"), ("QUALIFIED", "qualified"), ("BROKEN", "broken")):
        add(f"all.{lab}", sum(1 for r in rows if r["_o"] == o), source=src)
    cell = lambda rs: " ".join(f"{MARK[r['_o']]} {13 - len(r['_wrong']) - len(r['_gaps'])}/13" for r in rs) or "—"  # noqa: E731
    matrix = {"head": ["Scenario", "Question it asks", "L0 · logs", "L1 · + traces", "L2 · lineage", "Production changed"],
              "rows": [[f"**{c}**", A.CASES[c]["title"]] + [cell([r for r in rows if r["case"] == c and r["key"] == k]) for k in A.LAYERS]
                       + [f"{next(r for r in rows if r['case'] == c)['_S']['result']['mutations']}×"] for c in A.ORDER if any(r["case"] == c for r in rows)]}
    problems = {"head": ["Row", "Layer", "Outcome", "What was missing or wrong"],
                "rows": [{"row": r["id"], "run": primary, "cells": [f"`{r['id']}`", A.LAYERS[r["key"]], f"**{r['_o']}**", r["note"] or ""]}
                         for r in rows if r["_o"] != "HELD"]}
    every = {"head": ["Row", "Scenario", "Layer", "Outcome", "Correct", "Key · timestamp joins", "Recorded events"],
             "rows": [{"row": r["id"], "run": primary, "cells": [f"`{r['id']}`", A.CASES[r["case"]]["title"], A.LAYERS[r["key"]], f"{MARK[r['_o']]} **{r['_o']}**",
                                                                  f"{13 - len(r['_wrong']) - len(r['_gaps'])}/13", f"{r['metrics'][3][1]} · {r['metrics'][4][1]}", str(r["_ev"])]}
                      for r in rows]}
    allruns = {"head": ["Run", "Kind", "Scenarios", "Rows", "Held", "Qualified", "Broken", "Directory"],
               "rows": [[f"`{x['id']}`", x["kind"], str(len(per_run[x["id"]]) // 3), str(len(per_run[x["id"]])),
                         *(str(sum(1 for r in per_run[x["id"]] if r["_o"] == o)) for o in ("HELD", "QUALIFIED", "BROKEN")),
                         f"`{x['scen'].relative_to(ROOT)}`"] for x in runs]}
    first = P["scen"] / A.ORDER[0]
    lineage = {"head": ["Stage", "Where (per scenario, in the run)", "Carries"],
               "rows": [[a, f"`{f.replace(A.ORDER[0], '‹scenario›')}`", d] for a, f, n, d in A.lineage(P, first)]}
    systems = {"items": [["cpu", "Agent runtimes", "target + concurrent, real processes"], ["server", "Deployment API", "simulated, idempotent, faults"],
                         ["user", "Scripted approvers", "signed, action-bound"], ["layers", "Three layers", "logs · + traces · lineage"],
                         ["check", "Scorer", "truth from systems of record"]], "label": "What every scenario touches"}
    checks_ds = {"head": ["Check", "Result"], "rows": [[c["check"], "✓ pass" if c["pass"] else "✕ **FAIL**"] for c in checks]}
    fl = [r for r in rows if r["case"] == FIRST]
    start = {"head": ["Open", "Layer", "Correct", "What this row shows"],
             "rows": [{"row": r["id"], "run": primary, "cells": [f"`{r['id']}`", A.LAYERS[r["key"]], f"{13 - len(r['_wrong']) - len(r['_gaps'])}/13",
                                                                  {"L0": "attempt 1 timed out, attempt 2 succeeded, one rollout: right counts, no delegation, no configuration, no integrity",
                                                                   "L1": "the same answers, joined by trace id instead of by timestamp",
                                                                   "L2": "attempt 1 committed, response lost, attempt 2 replayed, one physical change, one transaction, verified and anchored"}[r["key"]]]}
                      for r in fl]}
    contract = {"head": ["", "The experiment contract"],
                "rows": [["**Hypothesis**", "Governed execution lineage reconstructs an autonomous production change more completely than application logs or logs plus traces, and stays correct through crashes, retries, lost responses and tools that lie."],
                         ["**Control**", "One execution per scenario. The action path is shared: the same policy, approvals, checkpoints, retries and idempotency. The governed path adds one behaviour: it reads the world back before declaring success."],
                         ["**Variable**", "What the investigator may read: L0 application logs (trace ids removed) · L1 the same logs with trace context plus every span · L2 the evidence events, witness anchors and the transaction lookup."],
                         ["**Ground truth**", "The deployment API's and approval service's own databases and the scenario pins: never the records being scored."],
                         ["**Scoring**", "Thirteen questions per row: correct · partial (some parts not recorded) · not recorded · wrong · ambiguous. Joins counted as key joins or timestamp heuristics."],
                         ["**Important**", "L2's completeness is by design: a coverage test, not a benchmark. Survival under injected failures is the experiment. Idempotency makes a retry safe; lineage makes it explainable."]]}
    datasets = {"start": start, "contract": contract, "matrix": matrix, "problems": problems, "every": every, "allruns": allruns, "lineage": lineage, "systems": systems, "checks": checks_ds}
    metrics = {f"{lab}-{L}": {"rows": [r["id"] for r in rows if r["key"] == L and r["_o"] == o],
                              "breakdown": [{"label": g, "count": sum(1 for r in rows if r["key"] == L and r["_o"] == o and A.CASES[r["case"]]["group"] == g),
                                             "rows": [r["id"] for r in rows if r["key"] == L and r["_o"] == o and A.CASES[r["case"]]["group"] == g]}
                                            for g in dict.fromkeys(A.CASES[c]["group"] for c in A.ORDER)]}
               for o, lab in (("HELD", "held"), ("QUALIFIED", "qualified"), ("BROKEN", "broken")) for L in A.LAYERS}
    man = P["manifest"]
    artifacts = {
        "frozen": [[k, h, True] for k, h in man.get("frozen_inputs", {}).items()],
        "models": [["agent", "qwen3:8b via Ollama, temperature 0 (config v8) / 0.3 (config v9); record/replay tape"]],
        "run_meta": [["Run", primary], ["Python", env["python"]], ["OpenTelemetry SDK", env["opentelemetry-sdk"]], ["Started", man.get("started", "")],
                     ["Finished", man.get("finished", "")], ["Simulated", "deployment API, faults, incident, people"],
                     ["Real", "processes, SIGKILL, HTTP, SQLite, idempotency, OpenTelemetry, hash chain, scoring"]],
        "checks": [c["check"] for c in checks if c["pass"]],
    }
    data = {"factor": {"values": sorted({r["x"] for r in rows}), "primary": 1},
            "groups": {c: A.CASES[c]["title"] for c in A.ORDER}, "cases": cases, "runs": out_runs, "traces": traces, "datasets": datasets,
            "hypotheses": {}, "failures": {}, "metrics": metrics, "failure_classes": [], "artifacts": artifacts,
            "generated": {"runs": [x["id"] for x in runs], "primary": primary}}
    return data, facts


def main() -> None:
    primary = sys.argv[1] if len(sys.argv) > 1 else (A.RUNS / "PUBLISHED").read_text().strip()
    data, facts = collect(primary)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    res = kit.build(SPEC, data, facts, OUT, out_json=OUT.with_name("lab-console.evidence.json"), generated_by="tools/build_lab_console.py")
    ev = res["evidence"]
    print(f"{res['out'].relative_to(ROOT)} ({res['bytes'] // 1024} KB) · runs: {', '.join(r['id'] + ' (' + str(len(r['rows'])) + ')' for r in ev['runs'])}")


if __name__ == "__main__":
    main()
