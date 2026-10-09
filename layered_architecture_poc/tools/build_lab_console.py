"""Build F2's Lab Console: every run, every scenario, its input, output, steps, data lineage and status.

    python tools/build_lab_console.py [RUN_ID]      (make console; default: the published run, runs/PUBLISHED)
      -> docs/results/lab-console.html              one self-contained page (F1's Lab Console, evidence-kit 4.1.0)
      -> docs/results/lab-console.evidence.json     the canonical evidence it renders

The page is generated from the run directories, so it follows the runs: every directory under layered_architecture_poc/runs/
with scored scenarios becomes a selectable run (the primary first; a run's supplementary re-runs as their own run).
Record or replay a new run and rebuild (make console) and the page updates; nothing is typed by hand.  The words are in
tools/lab_console/learning.toml, where every number is a {{fact}}; the kit refuses hand-typed numbers.
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
OUT = ROOT / "docs" / "results" / "lab-console.html"
SEV = {"SUCCESS": "none", "FAILURE": "failure", "ERROR": "error"}
TONE = {"SUCCESS": "ok", "FAILURE": "warn", "ERROR": "bad"}
MARK = {"SUCCESS": "✓", "FAILURE": "✕", "ERROR": "!"}


def row_tabs(run: dict, sd: Path, s: dict, ev: list[dict], v: dict, prompt: str, plan: dict) -> dict:
    """The case tabs of one row, as blocks: Input & output · Steps · Data lineage · Logs."""
    st, key = v["status"], A.KEY[s["arch"]]
    rep = (s.get("report") or "").strip()
    writes = {k: n for k, n in s["physical_writes"].items() if n}
    fault = A.FAULT.get(s.get("fault") or "", s.get("fault") or "none")
    crash = A.CRASH.get(s.get("crash_point") or "", s.get("crash_point") or "none")
    inp = B.card(
        B.kv("Request", B.quote(prompt), B.small(f"asked by sre.alice · approver ic.bob · {A.ARCH[key]}")),
        B.kv("Scenario", B.line("Run id", f"`{s['scenario']}`"), B.line("Use case", plan["title"]), B.line("Question", plan["question"]),
             B.line("Model", f"`{s['model']}`"), B.line("Seed", str(s["seed"])), B.line("What the harness did", A.harness(s)), B.line("Fault injected", fault), B.line("Crash point", crash),
             B.line("Change applied", f"`{s['change']}`" if s.get("change") else "none")),
        title="Input", sub="What went in: the request, the scenario and what the harness did to it.")
    out = B.card(
        B.kv("Status", B.chips([(st, TONE[st])]), B.line("Failed at step", f"`{v['step']}`" if v["step"] else "—"), *( [B.small(v["why"])] if v["why"] else [])),
        B.kv("World state at the end", B.line("Workflow status", str(s.get("final_status") or "no final status")),
             B.line("Running release", f"`{s['running_release']}`"), B.line("Incident status", str(s["incident_status"])),
             B.line("Incident notes written", str(s["incident_notes"])),
             B.line("Physical writes", ", ".join(f"`{k}` × {n}" for k, n in writes.items()) or "none")),
        B.kv("Report", B.quote(rep[:700] + ("…" if len(rep) > 700 else "")) if rep else B.chip("no final report")),
        title="Output", sub="What came out, read from the world database and the process, not from the model's prose.")
    checks = B.card(B.kv("Checks (score.json)", B.row_flags("Status")), B.kv("Measurements", B.row_measurements()),
                    title="Checks", sub="The eight checks read `world.db` and the ledgers." + (" E9 is a dry run: the four rollback checks do not apply (—); "
                                                                                                "its preregistered criterion is zero deploy writes." if s["exp"] == "E9" else ""))
    # steps: a per-step summary, then every event
    steps_seen = [x for x in A.STEPS if any(e["step"] == x for e in ev)]
    srows = []
    for x in steps_seen:
        es = [e for e in ev if e["step"] == x]
        c = Counter(e["kind"] for e in es)
        bad = any(e.get("failed") for e in es) or (v["step"] == x and st != "SUCCESS")
        warn = any(e["tone"] in ("warn", "bad") for e in es)
        what = ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in c.items() if k not in ("step",))
        srows.append([B.cell(("code", x)), B.cell(("pill", "failed here" if bad else "fault/warning" if warn else "ok", "bad" if bad else "warn" if warn else "ok")),
                      B.cell(("text", what))])
    first = next((i for i, e in enumerate(ev) if e.get("failed")), None)
    tl = [{"n": i + 1, "tone": e["tone"], "text": f"`{e['step']}` · {e['text']}" + (" ← **first failing event**" if i == first else ""),
           "msg": e.get("msg"), "code": e.get("code"), "notes": [f"source: `{e['src']}`"]} for i, e in enumerate(ev)]
    head = B.callout(f"{st}" + (f" · failed at step {v['step']} · {v['why'].replace('`', '')}" if st != "SUCCESS" else " · every applicable check passed"),
                     tone=TONE[st], icon="check" if st == "SUCCESS" else "alert")
    steps = [head, B.card(B.table(["Step", "Status", "Recorded events"], srows), title="Steps",
                          sub="Layered steps are the workflow's own; the monolith's events are mapped onto the same step names by what they do."),
             B.transcript(tl, "Every recorded event", f"{len(ev)} events in time order, from the scenario's ledgers.")]
    lin = A.lineage(run, sd, s, f"the {s['exp']} entry: fault, crash point, seeds, checks")
    lrows = [[B.cell(("text", a)), B.cell(("code", f)), B.cell(("text", str(n))), B.cell(("text", d))] for a, f, n, d in lin]
    lineage = [B.card(B.table(["Stage", "File (in the run)", ("Records", "n"), "Carries"], lrows), title="Data lineage",
                      sub="From the request to the published number. Each file is in the run directory; the evidence bundle carries all of them.")]
    logs = A.process_logs(sd)
    logtab = [B.transcript(logs, "Process logs", f"{len(logs)} process log(s); the last lines of each.")] if logs else [B.chip("no process logs recorded")]
    return {"io": [B.grid(inp, out), checks], "steps": steps, "lineage": lineage, "logs": logtab}


def collect(primary: str) -> tuple[dict, kit.Facts]:
    runs = A.discover(primary)
    assert runs and runs[0]["id"] == primary, f"run {primary} has no scored scenarios"
    P = runs[0]
    plan = A.yaml.safe_load((P["dir"] / "config_snapshot" / "experiments" / "preregistration" / "experiment_plan.yaml").read_text())
    exps = plan["experiments"]
    PROMPTS = A.prompts()
    cases, traces, out_runs, per_run = {}, {}, [], {}
    for run in runs:
        rows, tr = [], {}
        for sd in sorted(p for p in run["scen"].iterdir() if (p / "score.json").exists()):
            s = json.loads((sd / "score.json").read_text())
            ev = A.events(sd, s["arch"])
            v = A.verdict(s, ev, exps[s["exp"]])
            key = A.KEY[s["arch"]]
            cid = f"{s['exp']}-{'adv' if s['scenario'].endswith('adv') else 's' + str(s['seed'])}"
            cases[cid] = {"group": s["exp"], "title": f"{exps[s['exp']]['title']} · seed {s['seed']}", "who": "sre.alice (requester) · ic.bob (approver)",
                          "facts": [["Use case", exps[s["exp"]]["title"]], ["Question", exps[s["exp"]]["question"]]], "chips": []}
            ok_n = sum(1 for x in v["checks"].values() if x)
            app = sum(1 for x in v["checks"].values() if x is not None)
            flags = [[A.CHECK_TEXT[k], x] for k, x in v["checks"].items()]
            if s["exp"] == "E9":
                flags.append(["Dry run: zero deploy writes (preregistered)", v["deploy_writes"] == 0])
            rows.append({"id": s["scenario"], "case": cid, "key": key, "x": s["seed"], "pass": v["status"] == "SUCCESS", "sev": SEV[v["status"]],
                         "note": f"{v['step']}: {v['why']}" if v["status"] != "SUCCESS" else None, "flags": flags,
                         "metrics": [["Model calls", f"{s['model_calls']:,}"], ["Tokens", f"{s['tokens']:,}"], ["Tool calls", f"{s['tool_calls_client']:,}"],
                                     ["Physical writes", str(sum(s["physical_writes"].values()))], ["Processes", str(s["processes"])],
                                     ["SIGKILLs", str(s["sigkills"])], ["Wall time", f"{s['wall_s_total']} s"]],
                         "kv": [["Status", v["status"]], ["Failed at step", v["step"] or "—"], ["Checks", f"{ok_n}/{app}"], ["Exp", s["exp"]],
                                ["Harness", A.harness(s)]],
                         "_v": v, "_s": s})
            tr[s["scenario"]] = {"tabs": row_tabs(run, sd, s, ev, v, PROMPTS[s["prompt"]], exps[s["exp"]])}
        per_run[run["id"]] = rows
        traces[run["id"]] = tr
        out_runs.append({"id": run["id"], "label": run["label"], "kind": run["kind"], "path": str(run["scen"].relative_to(ROOT)),
                         "note": {"recorded": "live models, real MCP, real SIGKILL", "replay": "every model answer served from the recorded tape",
                                  "supplementary": "declared re-runs, kept beside the run"}[run["kind"]],
                         "rows": [{k: x for k, x in r.items() if not k.startswith("_")} for r in rows]})
    rows = per_run[primary]
    facts = kit.Facts()
    add = facts.add
    src = f"layered_architecture_poc/runs/{primary}/scenarios/*/score.json → status rules in tools/lab_console/adapter.py"
    man, ver = P["manifest"], json.loads((P["dir"] / "verification.json").read_text())
    rep = json.loads((P["dir"] / "replay_comparison.json").read_text()) if (P["dir"] / "replay_comparison.json").exists() else None
    add("run.id", primary, source=f"layered_architecture_poc/runs/{primary}")
    add("run.filed", (man.get("started_utc") or "")[:10], source="manifest.json → started_utc")
    add("run.scenarios", len(rows), unit="runs", source=src)
    add("run.experiments", len({r["_s"]["exp"] for r in rows}), source=src)
    add("run.sources", len(runs), source="layered_architecture_poc/runs/*")
    add("run.model_calls", sum(r["_s"]["model_calls"] for r in rows), source=src)
    add("run.tool_calls", sum(r["_s"]["tool_calls_client"] for r in rows), source=src)
    add("run.sigkills", sum(r["_s"]["sigkills"] for r in rows), source=src)
    add("run.models", ", ".join(m["name"] for m in man.get("models", {}).values()), source="manifest.json → models")
    add("verify.passed", ver["passed"], source="verification.json")
    add("verify.total", ver["total"], source="verification.json")
    for st in ("SUCCESS", "FAILURE", "ERROR"):
        ids = [r["id"] for r in rows if r["_v"]["status"] == st]
        add(f"all.{st.lower()}", len(ids), rows={"run": primary, "ids": ids} if ids else None, derivation=f"runs with status {st}", source=src)
        for key in ("M", "L"):
            ids = [r["id"] for r in rows if r["_v"]["status"] == st and r["key"] == key]
            n = sum(1 for r in rows if r["key"] == key)
            add(f"{key}.{st.lower()}", len(ids), rows={"run": primary, "ids": ids} if ids else None, denominator=n,
                derivation=f"{A.ARCH[key]} runs with status {st}", source=src)
            add(f"{key}.{st.lower()}.kn", f"{len(ids)}/{n}", source=src)
    for key in ("M", "L"):
        add(f"{key}.runs", sum(1 for r in rows if r["key"] == key), source=src)
    add("replay.served", rep["model_calls_served_from_tape"] if rep else 0, source="replay_comparison.json")
    add("replay.fresh", rep["fresh_model_calls"] if rep else 0, source="replay_comparison.json")

    # ---- datasets
    ORDER = sorted({r["_s"]["exp"] for r in rows}, key=lambda e: int(e[1:]))
    cell = lambda rs: " ".join(f"{MARK[r['_v']['status']]} `s{r['_s']['seed']}`" if not r["id"].endswith("adv") else f"{MARK[r['_v']['status']]} `adv`" for r in sorted(rs, key=lambda r: r["_s"]["seed"])) or "—"  # noqa: E731
    matrix = {"head": ["Exp", "Use case", "What the harness did", "Agent monolith", "Layered platform"],
              "rows": [[f"**{e}**", exps[e]["title"], (next((r["kv"][4][1] for r in rows if r["_s"]["exp"] == e), "")),
                        cell([r for r in rows if r["_s"]["exp"] == e and r["key"] == "M"]), cell([r for r in rows if r["_s"]["exp"] == e and r["key"] == "L"])]
                       for e in ORDER]}
    problems = {"head": ["Run id", "Architecture", "Status", "Failed at step", "What happened"],
                "rows": [{"row": r["id"], "run": primary, "cells": [f"`{r['id']}`", A.ARCH[r["key"]], f"**{r['_v']['status']}**", f"`{r['_v']['step']}`", r["_v"]["why"]]}
                         for r in rows if r["_v"]["status"] != "SUCCESS"]}
    every = {"head": ["Run id", "Use case", "Architecture", "Seed", "Status", "Failed at step", "Checks", "Model calls", "Physical writes"],
             "rows": [{"row": r["id"], "run": primary, "cells": [f"`{r['id']}`", exps[r["_s"]["exp"]]["title"], A.ARCH[r["key"]], str(r["_s"]["seed"]),
                                                                  f"{MARK[r['_v']['status']]} **{r['_v']['status']}**", f"`{r['_v']['step']}`" if r["_v"]["step"] else "—",
                                                                  r["kv"][2][1], r["metrics"][0][1], r["metrics"][3][1]]} for r in rows]}
    allruns = {"head": ["Run", "Kind", "Scenarios", "Success", "Failure", "Error", "Directory"],
               "rows": [[f"`{x['id']}`", x["kind"], str(len(per_run[x["id"]])),
                         *(str(sum(1 for r in per_run[x["id"]] if r["_v"]["status"] == st)) for st in ("SUCCESS", "FAILURE", "ERROR")),
                         f"`{x['scen'].relative_to(ROOT)}`"] for x in runs]}
    sample = A.lineage(P, P["scen"] / rows[0]["id"], rows[0]["_s"], "the experiment's preregistered entry")
    lineage = {"head": ["Stage", "Where (per scenario, in the run)", "Carries"],
               "rows": [[a, f"`{f.replace(rows[0]['id'], '‹run id›')}`", d] for a, f, n, d in sample]}
    systems = {"items": [["user", "Request", "sre.alice"], ["cpu", "Ollama", man.get("ollama_version", "")], ["plug", "MCP servers", f"SDK {man.get('mcp_sdk', '')}"],
                         ["box", "Simulated backends", "SQLite world"], ["check", "Scorer", "score.json"]], "label": "What every run touches"}
    datasets = {"matrix": matrix, "problems": problems, "every": every, "allruns": allruns, "lineage": lineage, "systems": systems}
    metrics = {f"{st.lower()}-{key}": {"rows": [r["id"] for r in rows if r["key"] == key and r["_v"]["status"] == st],
                                        "breakdown": [{"label": e, "count": sum(1 for r in rows if r["key"] == key and r["_v"]["status"] == st and r["_s"]["exp"] == e),
                                                       "rows": [r["id"] for r in rows if r["key"] == key and r["_v"]["status"] == st and r["_s"]["exp"] == e]}
                                                      for e in ORDER]}
               for st in ("SUCCESS", "FAILURE", "ERROR") for key in ("M", "L")}
    # ---- artifacts
    rev = (man.get("evidence_revisions") or [None])[0]
    hash_ok = next((c["ok"] for c in ver["checks"] if c["check"].startswith("frozen inputs")), False)
    rp_detail = []
    if len(runs) > 1 and rep:
        rr = next((x for x in runs if x["kind"] == "replay"), None)
        if rr:
            other = {r["id"]: r for r in per_run[rr["id"]]}
            for r in rows:
                o = other.get(r["id"])
                same = bool(o) and o["_s"]["checks"] == r["_s"]["checks"] and o["_v"]["status"] == r["_v"]["status"]
                rp_detail.append([r["id"], same, 0 if same else 1, rr["id"]])
    artifacts = {
        "frozen": [[k, h, hash_ok] for k, h in man.get("hashes", {}).items()],
        "models": [[m["name"], m.get("digest", "")[:16]] for m in man.get("models", {}).values()],
        "run_meta": [["Run", primary], ["Mode", man.get("mode", "")], ["Started (UTC)", man.get("started_utc", "")], ["Machine", f"{man.get('cpu')} · {man.get('memory_gb')} GB · {man.get('platform')}"],
                     ["Python", man.get("python", "")], ["Ollama", man.get("ollama_version", "")], ["MCP SDK", man.get("mcp_sdk", "")], ["Temperature", str(man.get("temperature"))],
                     ["Seeds", ", ".join(str(x) for x in man.get("seeds", []))]],
        "checks": [c["check"] for c in ver["checks"] if c["ok"]] + ["every row's status is derived from its score.json and ledgers (tools/lab_console/adapter.py)"],
        "revision": {"id": rev["id"], "label": rev.get("affects", ""), "summary": rev.get("reason") or rev.get("change") or "",
                     "rows": [[k, str(x)] for k, x in rev.items() if k not in ("id",)]} if rev else None,
        "replay": {"reproduced": sum(1 for d in rp_detail if d[1]), "rows": len(rp_detail), "mismatches": sum(d[2] for d in rp_detail), "detail": rp_detail} if rp_detail else None,
    }
    data = {"factor": {"values": sorted({r["x"] for r in rows}), "primary": sorted({r["x"] for r in rows})[0]}, "groups": {e: exps[e]["title"] for e in ORDER},
            "cases": cases, "runs": out_runs, "traces": traces, "datasets": datasets, "hypotheses": {}, "failures": {}, "metrics": metrics,
            "failure_classes": [], "artifacts": {k: x for k, x in artifacts.items() if x is not None},
            "generated": {"runs": [x["id"] for x in runs], "primary": primary}}
    return data, facts


def main() -> None:
    primary = sys.argv[1] if len(sys.argv) > 1 else (A.RUNS / "PUBLISHED").read_text().strip()
    data, facts = collect(primary)
    res = kit.build(SPEC, data, facts, OUT, out_json=OUT.with_name("lab-console.evidence.json"), generated_by="tools/build_lab_console.py")
    ev = res["evidence"]
    print(f"{res['out'].relative_to(ROOT)} ({res['bytes'] // 1024} KB) · runs: {', '.join(r['id'] + ' (' + str(len(r['rows'])) + ')' for r in ev['runs'])}")


if __name__ == "__main__":
    main()
