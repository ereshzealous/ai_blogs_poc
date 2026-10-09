"""docs/source/{evidence,report}.src.md, generated from proof/*.toml and the published run's facts.

Every number stays a {{fact}} token, resolved by tools/build_docs.py like the editions'.
    python3 tools/build_result_sources.py
"""
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "ops_poc"
RUN = (POC / "runs" / "PUBLISHED").read_text().strip()
SRC = ROOT / "docs" / "source"
FM = """---
title: {title}
subtitle: {subtitle}
byline: O1 + O2 · Production AI Engineering
kicker: Production AI Engineering · O1 + O2
filed: 2026-10-08
run: Recorded run {{{{run.id}}}}
---
"""


def evidence() -> str:
    claims = tomllib.loads((ROOT / "proof" / "claims.toml").read_text())["claims"]
    exps = {x["id"]: x for x in tomllib.loads((ROOT / "proof" / "experiments.toml").read_text())["experiments"]}
    checks = {c["id"]: c for x in exps.values() for c in x["checks"]}
    status = {json.loads(l)["id"]: json.loads(l) for l in (ROOT / "evidence" / "runs" / RUN / "checks.jsonl").read_text().splitlines()}
    out = [FM.format(title="Evidence Check: every claim, traced to its proof",
                     subtitle="Each claim of the O1 + O2 editions: the scenario, the mechanism, the checks behind it, what the run observed, and the class a reader should give it."),
           "## How to read this", "",
           "Every claim is stated without its numbers; the numbers are the checks' observed values, substituted from the published run. A check "
           "compares a recorded fact with a preregistered value or with the other arm. **SUPPORTED** means every check held; **QUALIFIED** means "
           "it held, with a limitation the run observed (a check marked LIMITATION OBSERVED); **NEGATIVE CONTROL** means a property broke on "
           "purpose when its safeguard was removed; **ARGUED** and **NOT TESTED** are reasoned or out of scope.", "",
           "All values are **simulation units** (simulated milliseconds, cost units). They show that a mechanism behaves as claimed under a "
           "declared workload; they are not benchmarks of any real provider, model or platform.", "",
           "The proof pack: {{proof.experiments}} experiments, {{proof.checks}} checks ({{proof.pass}} pass, {{proof.fail}} fail as a recorded "
           "limitation, {{proof.expected_failure}} expected failure), {{proof.claims}} claims. Replay {{replay.level}}: {{replay.identical}} of "
           "{{replay.files}} files byte-identical. The same mapping, machine-readable: `results/claim-evidence.json`.", ""]
    for cl in claims:
        out += [f"## {cl['id']} · {cl['class']}", "", f"**{cl['statement']}**", ""]
        if cl.get("note"):
            out += [f"*Note:* {cl['note']}", ""]
        if cl.get("rests_on"):
            out += ["*Rests on:* " + "; ".join(cl["rests_on"]) + ".", ""]
        xs = [exps[x] for x in cl.get("experiments", [])]
        for x in xs:
            setup = x["setup"][:1].upper() + x["setup"][1:]
            out += [f"*Scenario:* {x['id']} · {x['title']}. {setup}.", "", f"*Mechanism (the only variable):* {x['variable'][:1].upper() + x['variable'][1:]}.", ""]
        ids = cl.get("checks", []) + cl.get("bound_checks", [])
        if ids:
            out += ["| Check | What must hold | Observed | Result |", "|---|---|---|---|"]
            for cid in ids:
                c, st = checks[cid], status[cid]
                obs = "{{" + c["fact"] + "}}"
                res = "PASS" if st["status"] == "PASS" else st["finding"]
                out.append(f"| {cid} | {c['description']} | {obs} | {res} |")
            out += ["", f"*Raw evidence:* `ops_poc/runs/{RUN}/` (see each check's `evidence` in `evidence/runs/{RUN}/checks.jsonl`).", ""]
    return "\n".join(out) + "\n"


def report() -> str:
    out = [FM.format(title="Run report: every scenario, every arm",
                     subtitle="The recorded run, scenario by scenario: the naive arm, the controlled arm, and what each one cost. Simulation units."),
           "## The run", "",
           "Ten scenarios and a negative control, recorded once from the frozen preregistration (seed 4917), replayed byte for byte. Every row below "
           "is aggregated from the run's raw telemetry rows (`ops_poc/runs/{{run.id}}/scenarios/`).", "",
           "## E1 · Admission (Black Friday surge)", "",
           "| | open admission | bounded admission |", "|---|---|---|"]
    for k, lab in (("requests", "support requests"), ("attempts", "attempts, retries included"), ("retry_amplification", "attempts per request"),
                   ("max_work_in_system", "max work in system"), ("max_queued", "max queued"), ("queue_p50_ms", "queue delay p50 (sim-ms)"),
                   ("queue_p99_ms", "queue delay p99 (sim-ms)"), ("latency_p95_ms", "latency p95, successes (sim-ms)"), ("refused", "refused explicitly"),
                   ("served", "served while the client waited"), ("goodput_pct", "goodput (%)"), ("wasted_cu_pct", "cost on attempts nobody waited for (%)"),
                   ("cost_cu", "total cost (cu)")):
        out.append(f"| {lab} | {{{{e1.naive.{k}}}}} | {{{{e1.controlled.{k}}}}} |")
    out += ["", "## E2 · Tenant fairness (support + a finance batch)", "", "| | one global FIFO | fair scheduling + bulkhead |", "|---|---|---|"]
    for k, lab in (("support.goodput_pct", "support served in time (%)"), ("support.queue_p99_ms", "support queue delay p99 (sim-ms)"),
                   ("support.retry_amplification", "support attempts per request"), ("finance.completed", "finance items completed"),
                   ("finance.makespan_s", "finance makespan (sim-s)"), ("finance.max_active", "finance running at once, max"),
                   ("support.max_active", "support running at once, max")):
        out.append(f"| {lab} | {{{{e2.naive.{k}}}}} | {{{{e2.controlled.{k}}}}} |")
    out += ["", "## E3 · Bounded concurrency and deadlines", "", "| | unbounded | slots + bounded queue + deadlines |", "|---|---|---|"]
    for k, lab in (("max_active", "running at once, max"), ("goodput_pct", "goodput (%)"), ("latency_p95_ms", "latency p95, successes (sim-ms)"),
                   ("wasted_cu_pct", "cost on attempts nobody waited for (%)"), ("results.SHED_DEADLINE", "dropped at dequeue (deadline)"),
                   ("results.CANCELLED_DEADLINE", "cancelled at the deadline"), ("refused", "refused explicitly"), ("started_after_deadline", "started after the client's deadline")):
        out.append(f"| {lab} | {{{{e3.naive.{k}}}}} | {{{{e3.controlled.{k}}}}} |")
    out += ["", "## E4 · Workflow resource envelopes", "", "| | no budget | per-agent budgets | propagated envelope |", "|---|---|---|---|"]
    for k, lab in (("runaway.result", "runaway refund: result"), ("runaway.steps", "runaway refund: steps"), ("runaway.cost_cu", "runaway refund: cost (cu)"),
                   ("coord.result", "coordinator + 3 sub-agents: result"), ("coord.model_calls", "coordinator: model calls, children included"),
                   ("coord.cost_cu", "coordinator: cost (cu)"), ("coord.reason", "coordinator: stopped on"), ("legit_cut", "legitimate workflows cut")):
        out.append(f"| {lab} | {{{{e4.none.{k}}}}} | {{{{e4.per-agent.{k}}}}} | {{{{e4.envelope.{k}}}}} |")
    out += ["", "Cut by the envelope: {{e4.envelope.legit_cut_reasons}} ({{e4.envelope.legit_cut_rerun}} of them had re-run after a wrong answer). "
            "The envelope (refund dispute): {{e4.limit.refund-dispute.steps}} steps, {{e4.limit.refund-dispute.model_calls}} model calls, "
            "{{e4.limit.refund-dispute.tool_calls}} tool calls, {{e4.limit.refund-dispute.cost_cu}} cu; coordinator: {{e4.limit.dispute-investigation.model_calls}} model calls.", "",
            "## E5 · Routing inside an eligibility contract", "",
            "| | all-large | all-small | routed | routed, any fallback |", "|---|---|---|---|---|"]
    for k, lab in (("success_pct", "success (%)"), ("wrong_first", "first answer wrong (caught)"), ("escalated", "escalated"), ("deferred", "deferred during the throttle"),
                   ("cost_per_request", "cost per request (cu)"), ("cost_per_success", "cost per success (cu)"),
                   ("cost_per_success_incl_escalation", "… with escalations at 60 cu"), ("capability_violations", "calls below the capability tier"),
                   ("data_violations", "calls breaking the data policy"), ("fallbacks", "fallbacks"), ("latency_p95_ms", "latency p95 (sim-ms)")):
        out.append(f"| {lab} | {{{{e5.all-large.{k}}}}} | {{{{e5.all-small.{k}}}}} | {{{{e5.routed.{k}}}}} | {{{{e5.routed-any-fallback.{k}}}}} |")
    out += ["", "Break-even: all-small stays cheaper per success than routed unless one escalation costs more than {{e5.break_even_escalation_cu}} cu "
            "(under this declared contract and success table).", "",
            "## E6 · Context budgets and cache scope", "", "| | naive | bounded |", "|---|---|---|"]
    for k, lab in (("context_tokens_mean", "context tokens per query (mean)"), ("chunks_retrieved", "chunks retrieved (12 queries)"),
                   ("sources_queried", "source queries"), ("missing_required", "required evidence ids missing"), ("retrieval_cost_cu", "retrieval cost (cu)")):
        out.append(f"| {lab} | {{{{e6.naive.{k}}}}} | {{{{e6.bounded.{k}}}}} |")
    out += ["", "| cache | lookups | hits | served across principals | served stale |", "|---|---|---|---|---|",
            "| keyed by query text | {{e6.cache.query-text.lookups}} | {{e6.cache.query-text.hits}} | {{e6.cache.query-text.cross_principal}} | {{e6.cache.query-text.stale}} |",
            "| scoped key | {{e6.cache.scoped.lookups}} | {{e6.cache.scoped.hits}} | {{e6.cache.scoped.cross_principal}} | {{e6.cache.scoped.stale}} |", "",
            "## E7 · The tool gateway", "", "| | direct calls | gateway | gateway + fair scheduling |", "|---|---|---|---|"]
    for k, lab in (("max_inflight", "payments calls in flight, max"), ("http_503", "503s"), ("http_429", "429s"), ("attempts_per_call", "attempts per logical call"),
                   ("completed", "workflows completed"), ("failed_tool", "workflows failed on the tool"), ("support_goodput_pct", "support served in time (%)"),
                   ("finance_completed", "finance items completed"), ("finance_makespan_s", "finance makespan (sim-s)")):
        out.append(f"| {lab} | {{{{e7.naive.{k}}}}} | {{{{e7.controlled.{k}}}}} | {{{{e7.composed.{k}}}}} |")
    out += ["", "## E8 · The behavioural release (same code, seven releases)", "", "| release | changed artifact | release id | tool calls/wf | input tokens/wf | cost/wf (cu) |",
            "|---|---|---|---|---|---|", "| R41 | (production) | {{e8.R41.release_id}} | {{e8.R41.tool_calls_per_wf}} | {{e8.R41.input_tokens_per_wf}} | {{e8.R41.cost_per_wf}} |"]
    for n in ("R42-e", "R42-a", "R42-topk", "R42-kb", "R42-policy", "R42-routing"):
        out.append(f"| {n} | {{{{e8.{n}.artifact}}}} | {{{{e8.{n}.release_id}}}} | {{{{e8.{n}.tool_calls_per_wf}}}} | {{{{e8.{n}.input_tokens_per_wf}}}} | {{{{e8.{n}.cost_per_wf}}}} |")
    out += ["", "Image digest, all seven: {{e8.image_digest}}. Telemetry rows with a release id: {{e8.rows_with_release_id}} of {{e8.rows_total}}.", "",
            "## E9 · The offline gate ({{e9.cases}} cases)", "", "| candidate | task success | data policy | approval bypass | envelope | cost Δ (%) | gate |", "|---|---|---|---|---|---|---|"]
    for n in ("R42-a", "R42-b", "R42-c", "R42-d", "R42-e"):
        out.append(f"| {n} | {{{{e9.{n}.task_success}}}} | {{{{e9.{n}.inv.data_policy}}}} | {{{{e9.{n}.inv.approval_bypass}}}} | {{{{e9.{n}.inv.envelope_unenforceable}}}} | "
                   f"{{{{e9.{n}.cost_delta_pct}}}} | {{{{e9.{n}.reasons}}}} |")
    out += ["", "## E10 · The canary", "", "| analysis | decision | windows | at (sim-s) | last window: tool calls Δ (%) | cost/success Δ (%) | error Δ (pp) | breaches |",
            "|---|---|---|---|---|---|---|---|"]
    for k in ("R42-a.mix-adjusted", "R42-e.mix-adjusted", "R42-e.raw"):
        out.append(f"| {k} | {{{{e10.{k}.decision}}}} | {{{{e10.{k}.windows}}}} | {{{{e10.{k}.decided_at_s}}}} | {{{{e10.{k}.last.tool_calls_pct}}}} | "
                   f"{{{{e10.{k}.last.cost_per_success_pct}}}} | {{{{e10.{k}.last.error_pp}}}} | {{{{e10.{k}.breaches}}}} |")
    out += ["", "R42-a: replies sent before the rollback {{e10.R42-a.mix-adjusted.effects_before_decision}}, undone {{e10.R42-a.mix-adjusted.effects_reverted}}; "
            "requests to R42-a after the decision {{e10.R42-a.mix-adjusted.candidate_after_decision}}.", "",
            "## Negative control", "", "E1's controlled arm without the admission bound: max work in system {{nc.max_work_in_system}} against a bound of "
            "{{cfg.work_in_system_bound}}; the check OPS-NC-C01 failed, as it must.", "",
            f"Raw files: `ops_poc/runs/{RUN}/` · every recorded decision explained: `uv run agentops explain E10-canary` (and E1-surge, E4-runaway, E5-routing, E8-release, E9-gate).", ""]
    return "\n".join(out) + "\n"


def main() -> None:
    (SRC / "evidence.src.md").write_text(evidence())
    (SRC / "report.src.md").write_text(report())
    print("wrote evidence and report sources")


if __name__ == "__main__":
    main()
