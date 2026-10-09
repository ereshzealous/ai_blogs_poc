"""Build T4's Lab Console: every scenario of every run, its input, output, steps, data lineage and outcome.

    python3 tools/build_lab_console.py [RUN_ID]      (make console; default: the published run, runs/PUBLISHED)
      -> results/lab-console.html                  one self-contained page (evidence-kit 4.1.0, as F1 and F2)
      -> results/lab-console.evidence.json         the canonical evidence it renders

The page is generated from the run directories, so it follows the runs: every directory under control_plane_poc/runs/
with recorded scenarios becomes a selectable run.  Run the experiments again and rebuild (make console) and the page
updates; nothing is typed by hand.  The words are in tools/lab_console/learning.toml, where every number is a {{fact}}.

A scenario's outcome is the governed property it tests: HELD (the property held), QUALIFIED (it held within a stated
bound, such as the staleness bound during an outage) or BROKEN (the design lost it, which is what the embedded baseline is
there to show).  Separately, every scenario is checked against its expectation by the run's own checks (checks.json).
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

sys.path.insert(0, str(ROOT / "tools"))
from ledger import rows as ledger_rows  # noqa: E402

SPEC = ROOT / "tools" / "lab_console" / "learning.toml"
OUT = ROOT / "results" / "lab-console.html"
SEV = {"held": "none", "qualified": "qualified", "broken": "broken"}
TONE = {"held": "ok", "qualified": "warn", "broken": "bad"}
MARK = {"held": "✓", "qualified": "~", "broken": "✕"}


def step_of(where: str | None) -> str:
    """The step named at the head of scenario.json's `where` ('approval.requested: …' -> 'approval.requested')."""
    return where.split(":")[0] if where else "—"


def contract(run: dict, sd: Path, sc: dict, role: dict, led: list[dict]) -> str:
    """The scenario's contract: the property under test, what changed, the runtime state, versions, requests, decisions,
    what the systems of record show, the assertions, the evidence and the outcome, each read from the run."""
    rt = [w for w in led if w["source"] != "control plane"]
    changes = [f"{w['cp_version'] or ''} {w['audit_event'].split(' ', 1)[-1]} ({w['decision'].split(' · ')[0].lower()}, {w['actor']})".strip()
               for w in led if w["source"] == "control plane" and not w["audit_event"].endswith(" seed")]
    procs = sorted({w["runtime_pid"] for w in rt if w["runtime_pid"]})
    restarted = any(not p.endswith("/pid-1") for p in procs)
    versions = sorted({w["cp_version"] for w in rt if w["cp_version"]}, key=lambda v: (len(v), v))
    reqs = sorted({w["request_sha256"] for w in rt if w["request_sha256"]})
    dec = Counter(w["decision"].split(" · ")[0] for w in rt if w["rule"] and w["decision"])
    eff = json.loads((sd / "state" / "systems" / "effects.json").read_text()) if (sd / "state" / "systems" / "effects.json").exists() else {}
    reached = sum(1 for w in rt if " → " in (w["system_of_record"] or ""))
    n_ok = sum(c["passed"] for c in sc["checks"])
    return B.card(
        B.kv("Scenario contract",
             B.line("Group · role", f"{role['group']} · {role['role']}"),
             B.line("Property under test", role["property"]),
             B.line("Change", "; ".join(changes) or "none (configuration only)"),
             B.line("Runtime state", (", ".join(f"`{p}`" for p in procs) + (" · restarted" if restarted else " · never restarted")) if procs else "no runtime process"),
             B.line("Control plane versions seen", " → ".join(f"`{v}`" for v in versions) or "—"),
             B.line("Requests", f"{len(reqs)} distinct request hash{'es' if len(reqs) != 1 else ''}" + (f": `{'`, `'.join(reqs[:3])}`" if reqs else "")),
             B.line("Decisions", " · ".join(f"{k} {v}" for k, v in dec.items()) or "—"),
             B.line("System of record", f"{reached} call(s) reached a system · " + " · ".join(f"{k} {len(v)}" for k, v in eff.items()) if eff else f"{reached} call(s) reached a system"),
             B.line("Test assertions", f"{n_ok}/{len(sc['checks'])} passed"),
             B.line("Evidence", f"`{sd.relative_to(ROOT)}/`"),
             B.line("Outcome", A.OUTCOME[sc["outcome"]]),
             B.line("Qualification", sc["where"] or "none: the property held")),
        title="Scenario contract", sub="Read from the run: the step ledger (runtime audit, change log, transcript) and the systems of record.")


def row_tabs(run: dict, sd: Path, sc: dict, ev: list[dict], first: int | None, role: dict, led: list[dict]) -> dict:
    """The case tabs of one scenario: Input & output · Steps · Data lineage · Systems."""
    o = sc["outcome"]
    inp = B.card(B.kv("Scenario", B.line("Scenario id", f"`{sc['id']}`"), B.line("Use case", sc["use_case"]),
                      B.line("Question", A.EXPERIMENTS[sc["experiment"]][1]), B.line("Design", f"{sc['variant']} · {A.MODEL[sc['variant']]}")),
                 B.kv("What went in", *[B.line(k.replace("_", " ").capitalize(), str(v))
                                        for k, v in sc["input"].items()]),
                 title="Input", sub="Which agents ran, what the control plane was changed to, and what fault the scenario injected.")
    out = B.card(B.kv("Outcome", B.chips([(A.OUTCOME[o], TONE[o])]), B.line("Where it was qualified or broke", f"`{sc['where']}`" if sc["where"] else "—")),
                 B.kv("Expected vs observed", B.line("Expected", sc["expected"]), B.line("Observed", sc["observed"])),
                 B.kv("Measured", *[B.line(k, f"`{v}`") for k, v in sc["measures"]]),
                 title="Output", sub="Read from the runtime audit, the control plane's change log and the systems of record, not from what an agent says it did.")
    checks = B.card(B.kv("Checks (checks.json)", B.row_flags("Outcome")), B.kv("Measurements", B.row_measurements()),
                    title="Checks", sub="The run's own pass/fail checks that this scenario answers." if sc["checks"]
                    else "This scenario is context for its experiment's checks; it answers none on its own.")
    seen = [x for x in A.STEPS if any(e["step"] == x for e in ev)]
    srows = []
    for x in seen:
        es = [e for e in ev if e["step"] == x]
        c = Counter(e["kind"] for e in es)
        bad = any(e.get("failed") for e in es)
        warn = any(e["tone"] in ("warn", "bad") for e in es)
        srows.append([B.cell(("code", x)), B.cell(("pill", "broke here" if bad else "denied / warning" if warn else "ok", "bad" if bad else "warn" if warn else "ok")),
                      B.cell(("text", ", ".join(f"{n} {k}" for k, n in c.items())))])
    tl = [{"n": i + 1, "tone": e["tone"], "text": e["text"] + (" ← **where the property was qualified or broke**" if i == first else ""),
           "msg": e.get("msg"), "code": e.get("code"), "notes": [f"source: `{e['src']}`"]} for i, e in enumerate(ev)]
    head = B.callout(f"{A.OUTCOME[o]}" + (f" · {sc['where']}" if sc["where"] else " · the governed property held"), tone=TONE[o],
                     icon="check" if o == "held" else "alert")
    steps = [head, B.card(B.table(["Step", "Status", "Recorded events"], srows) if srows else B.chip("derived from configuration: no events"),
                          title="Steps", sub="control plane → config sync → run → enforcement → approval → model → system, as recorded."),
             B.transcript(tl, "Every recorded event", f"{len(ev)} events in tick order: control-plane changes, runtime audit rows and every system call.")]
    lin = A.lineage(run, sd, sc)
    lrows = [[B.cell(("text", a)), B.cell(("code", f)), B.cell(("text", n)), B.cell(("text", d))] for a, f, n, d in lin]
    lineage = [B.card(B.table(["Stage", "File (in the run)", ("Records", "n"), "Carries"], lrows), title="Data lineage",
                      sub="From the scenario's inputs to the published number. Every file is in the run directory.")]
    logs = A.tool_log_transcript(sd)
    logtab = [B.transcript(logs, "Systems", f"{len(logs)} record(s): what each system and model endpoint saw, and the side effects.")] if logs else [B.chip("no system calls in this scenario")]
    return {"io": [contract(run, sd, sc, role, led), B.grid(inp, out), checks], "steps": steps, "lineage": lineage, "logs": logtab}


def collect(primary: str) -> tuple[dict, kit.Facts]:
    runs = A.discover(primary)
    assert runs and runs[0]["id"] == primary, f"run {primary} has no recorded scenarios (rerun: make run)"
    P = runs[0]
    cases, traces, out_runs, per_run, all_ev = {}, {}, [], {}, {}
    for run in runs:
        rows, tr = [], {}
        grp, led = A.roles(run), ledger_rows(run["dir"])
        for sd, sc in A.scenarios(run):
            ev = A.events(sd)
            first = A.mark_where(ev, sc["where"])
            parts = sc["id"].split("-", 2)
            cid = f"{parts[0]}-{parts[2]}"
            title, question = A.EXPERIMENTS[sc["experiment"]]
            cases.setdefault(cid, {"group": grp[sc["experiment"]]["group"], "title": sc["use_case"], "who": ", ".join(f"{k}: {v}" for k, v in sc["input"].items() if k in ("agent", "agents", "instances")) or "control plane",
                                   "facts": [["Experiment", f"{sc['experiment']} · {title}"], ["Group", f"{grp[sc['experiment']]['group']} · {grp[sc['experiment']]['role']}"],
                                             ["Property", grp[sc["experiment"]]["property"]], ["Question", question]], "chips": []})
            ok_n = sum(1 for c in sc["checks"] if c["passed"])
            rows.append({"id": sc["id"], "case": cid, "key": sc["variant"], "x": int(sc["experiment"][1:]),
                         "pass": all(c["passed"] for c in sc["checks"]), "sev": SEV[sc["outcome"]],
                         "note": sc["where"] if sc["outcome"] != "held" else None,
                         "flags": [[c["check"], c["passed"]] for c in sc["checks"]],
                         # short values only: long principals and reasons stay in the Output card, where they wrap
                         # labels with spaces, not underscores, so a long measure name wraps at phone width
                         "metrics": [[k.replace("_", " "), str(v)] for k, v in sc["measures"] if len(str(v)) <= 24] + [["Recorded events", str(len(ev))]],
                         "kv": [["Outcome", A.OUTCOME[sc["outcome"]]], ["Where it broke", step_of(sc["where"])], ["Checks", f"{ok_n}/{len(sc['checks'])}"],
                                ["Proof", sc["experiment"]], ["Design", A.MODEL[sc["variant"]]], ["Group", grp[sc["experiment"]]["group"]]],
                         "_s": sc, "_ev": len(ev)})
            tr[sc["id"]] = {"tabs": row_tabs(run, sd, sc, ev, first, grp[sc["experiment"]], [w for w in led if w["scenario_id"] == sc["id"]])}
        per_run[run["id"]] = rows
        traces[run["id"]] = tr
        out_runs.append({"id": run["id"], "label": run["label"], "kind": run["kind"], "path": str(run["scen"].relative_to(ROOT)),
                         "note": "deterministic: fixed agent plans, simulated systems and clock; real runtime processes, control plane and enforcement",
                         "rows": [{k: x for k, x in r.items() if not k.startswith("_")} for r in rows]})
    rows = per_run[primary]
    checks = json.loads((P["dir"] / "checks.json").read_text())
    facts = kit.Facts()
    add = facts.add
    src = f"control_plane_poc/runs/{primary}/scenarios/*/scenario.json"
    add("run.id", primary, source=f"control_plane_poc/runs/{primary}")
    add("run.filed", primary[:10], source="the run id")
    add("run.scenarios", len(rows), unit="scenarios", source=src)
    add("run.experiments", len({r["_s"]["experiment"] for r in rows}), source=src)
    add("run.sources", len(runs), source="control_plane_poc/runs/*")
    add("run.events", sum(r["_ev"] for r in rows), source=f"{src} → state/")
    add("checks.passed", sum(c["passed"] for c in checks), source="checks.json")
    add("checks.total", len(checks), source="checks.json")
    add("run.python", P["manifest"].get("python", ""), source="manifest.json → python")
    for o in ("held", "qualified", "broken"):
        ids = [r["id"] for r in rows if r["_s"]["outcome"] == o]
        add(f"all.{o}", len(ids), rows={"run": primary, "ids": ids} if ids else None, derivation=f"scenarios with outcome {o}", source=src)
        for key in "EC":
            ids = [r["id"] for r in rows if r["_s"]["outcome"] == o and r["key"] == key]
            n = sum(1 for r in rows if r["key"] == key)
            add(f"{key}.{o}", len(ids), rows={"run": primary, "ids": ids} if ids else None, denominator=n,
                derivation=f"{A.MODEL[key]} scenarios with outcome {o}", source=src)
            add(f"{key}.{o}.kn", f"{len(ids)}/{n}", source=src)
    for key in "EC":
        add(f"{key}.runs", sum(1 for r in rows if r["key"] == key), source=src)
    add("all.as_expected", sum(1 for r in rows if r["pass"]), source=f"{src} → checks")

    # ---- datasets
    G = A.roles(P)
    ORDER = sorted({r["_s"]["experiment"] for r in rows}, key=lambda e: (A.GROUPS.index(G[e]["group"]), int(e[1:])))
    cell = lambda rs: " · ".join(f"{MARK[r['_s']['outcome']]} `{r['id'].split('-', 2)[2]}`" for r in rs) or "—"  # noqa: E731
    matrix = {"head": ["Group", "Proof", "Property under test", "E · Embedded governance", "C · Control plane"],
              "rows": [[G[e]["group"], f"**{e}** · {A.EXPERIMENTS[e][0]}", G[e]["property"]] + [cell([r for r in rows if r["_s"]["experiment"] == e and r["key"] == k]) for k in "EC"]
                       for e in ORDER]}
    problems = {"head": ["Scenario", "Design", "Outcome", "Step", "What the record shows"],
                "rows": [{"row": r["id"], "run": primary, "cells": [f"`{r['id']}`", A.MODEL[r["key"]], f"**{A.OUTCOME[r['_s']['outcome']]}**",
                                                                    f"`{step_of(r['_s']['where'])}`", r["_s"]["where"]]}
                         for r in rows if r["_s"]["outcome"] != "held"]}
    every = {"head": ["Group", "Scenario", "Use case", "Design", "Outcome", "Assertions", "Recorded events"],
             "rows": [{"row": r["id"], "run": primary, "cells": [G[r["_s"]["experiment"]]["group"], f"`{r['id']}`", r["_s"]["use_case"], A.MODEL[r["key"]],
                                                                  f"{MARK[r['_s']['outcome']]} **{A.OUTCOME[r['_s']['outcome']]}**", r["kv"][2][1], str(r["_ev"])]}
                      for r in rows]}
    allruns = {"head": ["Run", "Kind", "Scenarios", "Held", "Qualified", "Broken", "Directory"],
               "rows": [[f"`{x['id']}`", x["kind"], str(len(per_run[x["id"]])),
                         *(str(sum(1 for r in per_run[x["id"]] if r["_s"]["outcome"] == o)) for o in ("held", "qualified", "broken")),
                         f"`{x['scen'].relative_to(ROOT)}`"] for x in runs]}
    sample = A.lineage(P, P["scen"] / rows[0]["id"], rows[0]["_s"])
    lineage = {"head": ["Stage", "Where (per scenario, in the run)", "Carries"],
               "rows": [[a, f"`{f.replace(rows[0]['id'], '‹scenario›')}`", d] for a, f, n, d in sample]}
    systems = {"items": [["layers", "Control plane", "versions · signatures · change log"], ["cpu", "Runtime process", "long-lived · enforcement at every call"],
                         ["server", "Services", "approvals · broker · spend meter"], ["box", "Simulated systems", "deploy · billing · support · observability · models"],
                         ["check", "Checks", "checks.json"]], "label": "What every scenario touches"}
    checks_ds = {"head": ["Exp", "Check", "Result", "Scenarios that answer it"],
                 "rows": [[c["experiment"], c["check"], "✓ pass" if c["passed"] else "✕ **FAIL**",
                           " ".join(f"`{r['id']}`" for r in rows if any(f[0] == c["check"] for f in r["flags"])) or "—"] for c in checks]}
    pj = ROOT / "evidence" / "runs" / primary / "checks.jsonl"
    pchecks = [json.loads(x) for x in pj.read_text().splitlines()] if pj.exists() else []
    xs = {x["id"]: x for x in json.loads((pj.parent / "results.json").read_text())["experiments"]} if pchecks else {}
    proof_ds = {"head": ["Check", "Experiment", "What must hold", "Observed", "Status", "Finding"],
                "rows": [[f"`{c['id']}`", xs[c["experiment"]]["title"], c["description"], f"`{c['actual']}` ({c['expected']})", c["status"], c["finding"]] for c in pchecks]}
    datasets = {"matrix": matrix, "problems": problems, "every": every, "allruns": allruns, "lineage": lineage, "systems": systems, "checks": checks_ds, "proof": proof_ds}
    for k, n_ in (("proof.checks", len(pchecks)), ("proof.pass", sum(c["status"] == "PASS" for c in pchecks)),
                  ("proof.limitation", sum(c["finding"] == "LIMITATION OBSERVED" for c in pchecks)), ("proof.expected_failure", sum(c["status"] == "EXPECTED_FAILURE" for c in pchecks))):
        add(k, n_, source=f"evidence/runs/{primary}/checks.jsonl")
    metrics = {f"{o}-{key}": {"rows": [r["id"] for r in rows if r["key"] == key and r["_s"]["outcome"] == o],
                              "breakdown": [{"label": e, "count": sum(1 for r in rows if r["key"] == key and r["_s"]["outcome"] == o and r["_s"]["experiment"] == e),
                                             "rows": [r["id"] for r in rows if r["key"] == key and r["_s"]["outcome"] == o and r["_s"]["experiment"] == e]}
                                            for e in ORDER]}
               for o, key in (("held", "C"), ("qualified", "C"), ("broken", "E"))}
    man = P["manifest"]
    artifacts = {
        "frozen": [[f"config/{k}", h, True] for k, h in man.get("config_sha256", {}).items()],
        "models": [["agents", "deterministic plans (acp/agents/*.py); no model"]],
        "run_meta": [["Run", primary], ["Python", man.get("python", "")], ["Agents", man.get("agents", "")],
                     ["Simulated", "; ".join(man.get("simulated", []))], ["Real", "; ".join(man.get("real", []))]],
        "checks": [c["check"] for c in checks if c["passed"]] + ["every scenario's outcome is read from its state directory: runtime audit, change log, systems of record (acp/experiments.py)"],
    }
    data = {"factor": {"values": sorted({r["x"] for r in rows}), "primary": sorted({r["x"] for r in rows})[0]},
            "groups": {g: g for g in A.GROUPS}, "cases": cases, "runs": out_runs, "traces": traces, "datasets": datasets,
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
