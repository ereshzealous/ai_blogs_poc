"""docs/source/{evidence,report,real-vs-simulated}.src.md, generated from proof/*.toml and the run's reports.

Every number stays a {{fact}} token, resolved by tools/build_docs.py like the editions'.
    python3 tools/build_result_sources.py
"""
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "recovery_poc"
RUN = (POC / "runs" / "PUBLISHED").read_text().strip()
SRC = ROOT / "docs" / "source"
FM = """---
title: {title}
subtitle: {subtitle}
byline: R1 + R2 · Production AI Engineering
kicker: Production AI Engineering · R1 + R2
filed: 2026-10-07
run: Recorded run {{{{run.id}}}}
---
"""


def evidence() -> str:
    claims = tomllib.loads((ROOT / "proof" / "claims.toml").read_text())["claims"]
    exps = {x["id"]: x for x in tomllib.loads((ROOT / "proof" / "experiments.toml").read_text())["experiments"]}
    checks = {c["id"]: c for x in exps.values() for c in x["checks"]}
    res = json.loads((ROOT / "evidence" / "runs" / RUN / "results.json").read_text())
    status = {json.loads(l)["id"]: json.loads(l) for l in (ROOT / "evidence" / "runs" / RUN / "checks.jsonl").read_text().splitlines()}
    out = [FM.format(title="Evidence Check: every claim, traced to its proof",
                     subtitle="Each claim of the R1 + R2 editions, the experiment and checks behind it, what the run observed, and the class a reader should give it."),
           "## How to read this", "",
           "Every claim below is stated without its numbers; the numbers are the checks' observed values, substituted from the published run. "
           "A check compares a recorded fact with a preregistered value. **SUPPORTED** means every check held; **QUALIFIED** means it held within a "
           "stated bound, measured by checks marked LIMITATION OBSERVED; **NEGATIVE CONTROL** means a property broke on purpose when its safeguard was "
           "removed; **ARGUED** and **NOT TESTED** are reasoned or out of scope.", "",
           "The proof pack: {{proof.experiments}} experiments, {{proof.checks}} checks ({{proof.pass}} pass, {{proof.fail}} fail as declared "
           "limitations, {{proof.expected_failure}} expected failure), {{proof.claims}} claims. Replay {{replay.level}}: {{replay.identical}} of "
           "{{replay.files}} files byte-identical.", ""]
    for cl in claims:
        out += [f"## {cl['id']} · {cl['class']}", "", f"**{cl['statement']}**", ""]
        if cl.get("qualification"):
            out += [f"*Bound:* {cl['qualification']}.", ""]
        if cl.get("rests_on"):
            out += [f"*Rests on:* {cl['rests_on']}.", ""]
        if cl["checks"]:
            out += ["| Check | What must hold | Observed | Status |", "|---|---|---|---|"]
            for cid in cl["checks"]:
                c, st = checks[cid], status[cid]
                obs = "{{" + c["fact"] + "}}"
                out.append(f"| {cid} | {c['description']} | {obs} | {st['finding'] if st['status'] != 'PASS' else 'PASS'} |")
            out.append("")
            xs = sorted({cid.rsplit('-C', 1)[0] for cid in cl['checks']})
            out += [f"*Experiments:* " + "; ".join(f"{x} · {exps[x]['title']}" for x in xs) + f". *Raw evidence:* `recovery_poc/runs/{RUN}/`.", ""]
    return "\n".join(out) + "\n"


def report() -> str:
    table = json.loads((POC / "runs" / RUN / "reports" / "scenarios.json").read_text())
    sids = sorted({r["scenario"] for r in table})
    title = {r["scenario"]: (r["title"], r["layer"]) for r in table}
    dec = {r["scenario"]: r["decisions"] for r in table if r["arm"] == "A2"}
    out = [FM.format(title="Run report: every scenario, every runtime",
                     subtitle="The forensic record of the recorded run: what each runtime did with each injected fault, counted in the providers' ledgers."),
           "## The run", "",
           "{{scenarios}} preregistered scenarios × {{arms}} runtimes = {{runs.deterministic}} scenario runs; {{mut.total}} mutants × {{scenarios}}; "
           "a deterministic model change; {{ms.calls}} real-model calls. Effects are credits on the charge (c), open tickets (t) and messages (m); "
           "the correct count is 1 · 1 · 1 unless the scenario denies or escalates first.", "",
           "## Per scenario", "",
           "| Scenario | Layer | A0 naive | A1 idempotent retry | A2 classified | A2 decisions |", "|---|---|---|---|---|---|"]
    for s in sids:
        cells = []
        for a in ("A0", "A1", "A2"):
            cells.append(f"{{{{{s}.{a}.status}}}} · c{{{{{s}.{a}.credits}}}} t{{{{{s}.{a}.tickets}}}} m{{{{{s}.{a}.notifications}}}}")
        d = " → ".join(f"{x[0]}/{x[1]}/**{x[2]}**" for x in dec[s]) or "—"
        out.append(f"| **{s}** {title[s][0]} | {title[s][1]} | {cells[0]} | {cells[1]} | {cells[2]} | {d} |")
    out += ["", "## Per runtime", "", "| | A0 | A1 | A2 |", "|---|---|---|---|"]
    for k, lab in (("dup_scenarios", "scenarios with a duplicate effect"), ("excess_effects", "excess effects"), ("outcome_correct", "correct outcomes"),
                   ("false_claims", "false claims"), ("terminal_retries", "retries of refusals"), ("trace_split", "runs split across traces"),
                   ("failures_diagnosed", "failures with class and certainty"), ("failure_events", "failure events"), ("invariant_failures", "invariant FAILs"),
                   ("eval_failures", "eval FAILs"), ("escalations", "escalations"), ("status_queries", "reconciliation queries"),
                   ("write_requests", "write requests reaching providers"), ("workers", "worker processes"), ("sigkills", "SIGKILLs"), ("anomalies", "harness anomalies")):
        out.append(f"| {lab} | {{{{A0.{k}}}}} | {{{{A1.{k}}}}} | {{{{A2.{k}}}}} |")
    out += ["", "## Mutants", "", "| Mutant | Scenarios failing | Checks that caught it |", "|---|---|---|"]
    for m in json.loads((POC / "runs" / RUN / "reports" / "mutants.json").read_text()):
        out.append(f"| {m['id']} {m['name']} | {{{{mut.{m['id']}.scenarios_failed}}}} | {{{{mut.{m['id']}.checks}}}} |")
    out += ["", "## Real-model slice (blind cases)", "", "| | {{ms.qwen.model}} | {{ms.llama.model}} |", "|---|---|---|"]
    for k, lab in (("schema_valid_pct", "structured output valid (%)"), ("tool_selection_pct", "right tool (%)"), ("arguments_exact_pct", "right arguments (%)"),
                   ("grounded_citation_pct", "grounded citation (%)"), ("pass_k", "pass^3 (cases)"), ("unsafe_proposal", "unsafe proposals"),
                   ("unsafe_executed", "unsafe proposals that would execute")):
        out.append(f"| {lab} | {{{{ms.qwen.blind.{k}}}}} | {{{{ms.llama.blind.{k}}}}} |")
    out.append("| gate | {{ms.qwen.gate}} | {{ms.llama.gate}} |")
    out += ["", f"Raw files: `recovery_poc/runs/{RUN}/` · per-run evals: `scenarios/<S>/<arm>/eval.json` · explain any run: "
            f"`uv run recovery explain runs/{RUN} S09 A2`.", ""]
    return "\n".join(out) + "\n"


def real() -> str:
    m = tomllib.loads((ROOT / "proof" / "manifest.toml").read_text())
    out = [FM.format(title="Real vs simulated: what actually ran",
                     subtitle="Which parts of the R1 + R2 POC exercised the real mechanism, which are faithful local substitutes, what was recorded and what was injected."),
           ]
    for r in m["reality"]:
        out += [f"## {r['class'].title()}", "", f"*{r['meaning']}.*", ""]
        for i in r["items"]:
            out.append(f"- {i['text']}" + (f" (check `{i['check']}`)" if i.get("check") else ""))
        out.append("")
    out += ["## What the simulation idealises", "",
            "- Reconciliation queries are immediately consistent once the request deadline has passed.",
            "- Providers have no rate limits on status queries, no partial batch success and no clock skew with the runtime.",
            "- Each scenario runs once; results are coverage of named faults, not a distribution of production failures.", ""]
    return "\n".join(out) + "\n"


def main() -> None:
    (SRC / "evidence.src.md").write_text(evidence())
    (SRC / "report.src.md").write_text(report())
    (SRC / "real-vs-simulated.src.md").write_text(real())
    print("wrote evidence, report, real-vs-simulated sources")


if __name__ == "__main__":
    main()
