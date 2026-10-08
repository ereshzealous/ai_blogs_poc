"""Turn recorded runs into facts.json: the one place every number in every edition comes from.

    python -m coord.analysis --e1 <run> [--e6 <run>] [--e7 <run>] [--e8 <run>] --out runs/<published>/facts.json

Each fact is {"value": ..., "source": "<run>/<file>: <how>"}.  Hypotheses are evaluated with the preregistered tests
(experiments/preregistration.toml), verbatim, and reported SUPPORTED / NOT SUPPORTED, whichever the data says.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from coord.util import ROOT

ARCHS = ("A", "B", "C")
SUBSETS = {"simple": ["B1", "B2", "B8"], "complex": ["B4", "B5", "B6"], "other": ["B3", "B7"]}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, c - h), 3), round(min(1.0, c + h), 3))


def q(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(math.ceil(p * len(xs))) - 1)] if xs else 0.0


def med(xs: list[float]) -> float:
    return round(statistics.median(xs), 1) if xs else 0.0


def rows(run: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (ROOT / "runs" / run / "rows.jsonl").read_text().splitlines() if line.strip()]


class Facts:
    def __init__(self) -> None:
        self.f: dict[str, dict[str, Any]] = {}

    def put(self, key: str, value: Any, source: str) -> None:
        self.f[key] = {"value": value, "source": source}

    def v(self, key: str) -> Any:
        return self.f[key]["value"]


def e1_facts(F: Facts, run: str) -> None:
    rs = [r for r in rows(run) if r["split"] == "blind"]
    src = f"runs/{run}/rows.jsonl"
    F.put("e1.runs", len(rs), f"{src}: blind rows")
    F.put("e1.anomalies", [r["workflow_id"] for r in rs if r.get("anomaly")], f"{src}: rows with an anomaly note")
    by = defaultdict(list)
    for r in rs:
        by[r["arch"]].append(r)
    for a in ARCHS:
        R = by[a]
        n, k = len(R), sum(r["eval"]["success"] for r in R)
        m = lambda key, R=R: [r["metrics"][key] for r in R]  # noqa: E731
        lo, hi = wilson(k, n)
        F.put(f"e1.{a}.n", n, f"{src}: arch={a}")
        F.put(f"e1.{a}.success", k, f"{src}: eval.success, arch={a}")
        F.put(f"e1.{a}.success_pct", round(100 * k / n) if n else 0, f"{src}: success / n")
        F.put(f"e1.{a}.success_ci", f"{round(100 * lo)}–{round(100 * hi)}%", "Wilson 95% interval")
        for conj in ("rc_ok", "evidence_ok", "remediation_ok", "prohibited_ok", "approval_ok", "outcome_ok"):
            F.put(f"e1.{a}.{conj}", sum(r["eval"][conj] for r in R), f"{src}: eval.{conj}")
        lat = [x / 1000 for x in m("latency_ms")]
        F.put(f"e1.{a}.latency_median_s", round(statistics.median(lat), 1) if lat else 0, f"{src}: metrics.latency_ms median")
        F.put(f"e1.{a}.latency_p90_s", round(q(lat, 0.9), 1), f"{src}: metrics.latency_ms p90 (n={n})")
        F.put(f"e1.{a}.latency_max_s", round(max(lat), 1) if lat else 0, f"{src}: metrics.latency_ms max")
        for key in ("tokens_total", "llm_calls", "tool_calls", "duplicate_tool_calls", "duplicate_cross_component", "handoffs", "handoff_bytes",
                    "max_prompt_tokens", "tokens_coordination", "deterministic_steps", "review_rejections", "process_boundaries",
                    "boundary_overhead_ms", "model_ms", "tool_ms", "other_ms"):
            F.put(f"e1.{a}.{key}_median", med(m(key)), f"{src}: metrics.{key} median")
            F.put(f"e1.{a}.{key}_total", round(sum(m(key)), 1), f"{src}: metrics.{key} sum")
        F.put(f"e1.{a}.state_conflicts", sum(m("state_conflicts")), f"{src}: metrics.state_conflicts sum")
        F.put(f"e1.{a}.terminations", dict(Counter(m("termination"))), f"{src}: metrics.termination counts")
        F.put(f"e1.{a}.outcomes", dict(Counter(r["eval"]["outcome"] for r in R)), f"{src}: eval.outcome counts")
        F.put(f"e1.{a}.trace_complete", sum(1 for r in R if r["metrics"]["trace"].get("complete")), f"{src}: metrics.trace.complete")
        F.put(f"e1.{a}.prohibited_attempts", sum(len(r["eval"]["prohibited_hits"]) for r in R), f"{src}: eval.prohibited_hits")
        F.put(f"e1.{a}.model_error_runs", sum(1 for r in R if r["metrics"]["llm_errors"]), f"{src}: runs ended by a model-server error (llm_errors > 0)")
        F.put(f"e1.{a}.claim_checks", sum(r["metrics"].get("claim_checks", 0) for r in R), f"{src}: metrics.claim_checks sum")
        F.put(f"e1.{a}.multi_write_runs", sum(1 for r in R if len(r["eval"]["executed_writes"]) >= 2), f"{src}: runs with two or more executed production writes")
        F.put(f"e1.{a}.llm_calls_total", sum(m("llm_calls")), f"{src}: metrics.llm_calls sum")
        F.put(f"e1.{a}.failed_by_model_error", sum(1 for r in R if r["metrics"]["llm_errors"] and r["metrics"]["termination"] == "FAILED"),
              f"{src}: runs ended FAILED by a model-server error")
        F.put(f"e1.{a}.right_action_wrong_label", sum(1 for r in R if r["eval"]["outcome_ok"] and r["eval"]["remediation_ok"] and not r["eval"]["rc_ok"]),
              f"{src}: outcome and write right, category outside the acceptable set")
        F.put(f"e1.{a}.right_outcome_no_evidence", sum(1 for r in R if r["eval"]["outcome_ok"] and not r["eval"]["evidence_ok"]),
              f"{src}: expected outcome reached without the required evidence")
        F.put(f"e1.{a}.unsafe_writes", sum(len(r["eval"]["unsafe_writes"]) for r in R), f"{src}: eval.unsafe_writes")
        tok = sum(m("tokens_total"))
        F.put(f"e1.{a}.coordination_token_share_pct", round(100 * sum(m("tokens_coordination")) / tok) if tok else 0,
              f"{src}: sum tokens_coordination / sum tokens_total")
        for sub, fx in SUBSETS.items():
            S = [r for r in R if r["fixture"] in fx]
            F.put(f"e1.{a}.{sub}.success", sum(r["eval"]["success"] for r in S), f"{src}: subset {sub}")
            F.put(f"e1.{a}.{sub}.n", len(S), f"{src}: subset {sub}")
            F.put(f"e1.{a}.{sub}.tokens_median", med([r["metrics"]["tokens_total"] for r in S]), f"{src}: subset {sub}")
            F.put(f"e1.{a}.{sub}.latency_median_s", round(med([r["metrics"]["latency_ms"] for r in S]) / 1000, 1), f"{src}: subset {sub}")
        for fx in sorted({r["fixture"] for r in rs}):
            S = [r for r in R if r["fixture"] == fx]
            F.put(f"e1.{a}.fixture.{fx}", f"{sum(r['eval']['success'] for r in S)}/{len(S)}", f"{src}: fixture {fx}")
    # incident-level view (post-hoc, descriptive): the three repeats of an incident share its fixture, so they are not
    # independent incident samples; compare architectures incident by incident as well as run by run
    per = {a: {fx: sum(r["eval"]["success"] for r in rs if r["arch"] == a and r["fixture"] == fx) for fx in sorted({r["fixture"] for r in rs})}
           for a in ARCHS}
    fxs = sorted(per["A"])
    F.put("e1.incidents", len(fxs), f"{src}: distinct blind fixtures")
    for x, y in (("B", "C"), ("B", "A"), ("C", "A")):
        F.put(f"inc.{x}_gt_{y}", sum(per[x][f] > per[y][f] for f in fxs), f"{src}: incidents where {x} had more successes (of 3) than {y}")
        F.put(f"inc.{y}_gt_{x}", sum(per[y][f] > per[x][f] for f in fxs), f"{src}: incidents where {y} had more successes (of 3) than {x}")
        F.put(f"inc.{x}_eq_{y}", sum(per[x][f] == per[y][f] for f in fxs), f"{src}: incidents where {x} and {y} tied")
    for a in ARCHS:
        F.put(f"inc.{a}.all3", sum(v == 3 for v in per[a].values()), f"{src}: incidents {a} passed in all three repeats")
        F.put(f"inc.{a}.none", sum(v == 0 for v in per[a].values()), f"{src}: incidents {a} never passed")
    F.put("inc.none_passed", sum(all(per[a][f] == 0 for a in ARCHS) for f in fxs), f"{src}: incidents no architecture passed in any repeat")

    def fx_med(a: str, fx: str, k: str) -> float:
        return med([r["metrics"][k] for r in rs if r["arch"] == a and r["fixture"] == fx])
    for k, name in (("tokens_total", "tokens"), ("latency_ms", "latency")):
        ratios = [fx_med("C", f, k) / fx_med("B", f, k) for f in fxs]
        F.put(f"inc.C_{name}_gt_B", sum(x > 1 for x in ratios), f"{src}: incidents where C's median {k} exceeded B's")
        F.put(f"inc.C_over_B_{name}_min_ratio", round(min(ratios), 1), f"{src}: smallest per-incident ratio of C's to B's median {k}")
    for f_ in fxs:
        F.put(f"inc.{f_}.C_over_B_tokens", round(fx_med("C", f_, "tokens_total") / fx_med("B", f_, "tokens_total"), 1),
              f"{src}: fixture {f_}, C's median tokens / B's median tokens")
    # hypotheses (preregistered tests, verbatim)
    s = lambda a, sub=None: F.v(f"e1.{a}.{sub}.success" if sub else f"e1.{a}.success")  # noqa: E731
    h1 = (F.v("e1.C.simple.tokens_median") > F.v("e1.B.simple.tokens_median") and F.v("e1.C.simple.latency_median_s") > F.v("e1.B.simple.latency_median_s")
          and s("C", "simple") <= s("B", "simple"))
    F.put("H1", "SUPPORTED" if h1 else "NOT SUPPORTED", "prereg H1 test on e1 simple subset")
    F.put("H2", "SUPPORTED" if s("C", "complex") >= s("B", "complex") + 2 else "NOT SUPPORTED", "prereg H2 test on e1 complex subset")
    F.put("H3", "SUPPORTED" if s("A", "simple") >= s("B", "simple") - 1 else "NOT SUPPORTED", "prereg H3 test on e1 simple subset")
    dup = {a: F.v(f"e1.{a}.duplicate_tool_calls_median") for a in ARCHS}
    F.put("H4", "SUPPORTED" if dup["C"] > dup["A"] and dup["C"] > dup["B"] else "NOT SUPPORTED", "prereg H4 test on e1 medians")
    F.put("H5", "SUPPORTED" if s("B") >= s("A") and s("B") >= s("C") else "NOT SUPPORTED", "prereg H5 test on e1 totals")
    # coordination tax decomposition, C relative to B (components, never summed)
    F.put("tax.C_minus_B_tokens_median", round(F.v("e1.C.tokens_total_median") - F.v("e1.B.tokens_total_median")), "e1 medians")
    F.put("tax.C_over_B_tokens_ratio", round(F.v("e1.C.tokens_total_median") / max(1, F.v("e1.B.tokens_total_median")), 1), "e1 medians")
    F.put("tax.C_over_A_tokens_ratio", round(F.v("e1.C.tokens_total_median") / max(1, F.v("e1.A.tokens_total_median")), 1), "e1 medians")
    F.put("tax.A_over_B_tokens_ratio", round(F.v("e1.A.tokens_total_median") / max(1, F.v("e1.B.tokens_total_median")), 1), "e1 medians")
    F.put("ctx.window", 32768, "config/models.yaml num_ctx (configuration, not a measurement)")
    F.put("ctx.max_prompt_share_pct", round(100 * max(F.v(f"e1.{a}.max_prompt_tokens_median") for a in ARCHS) / 32768),
          "largest per-run median of the largest prompt, as % of num_ctx")
    F.put("tax.C_over_B_latency_ratio", round(F.v("e1.C.latency_median_s") / max(0.1, F.v("e1.B.latency_median_s")), 1), "e1 medians")
    C = by["C"]
    dels = sum(r["metrics"]["delegation_attempts"] for r in C)
    completed = sum(len(r["metrics"].get("delegation_server_ms", [])) for r in C)
    F.put("c.delegations_total", dels, f"{src}: metrics.delegation_attempts sum, arch C")
    F.put("c.delegations_completed", completed, f"{src}: completed delegation attempts, arch C")
    F.put("c.boundary_ms_per_delegation", round(sum(r["metrics"]["boundary_overhead_ms"] for r in C) / max(1, completed), 1),
          f"{src}: sum boundary_overhead_ms / completed delegation attempts, arch C (prereg definition)")
    share = 100 * sum(r["metrics"]["boundary_overhead_ms"] for r in C) / max(1, sum(r["metrics"]["latency_ms"] for r in C))
    F.put("c.boundary_share_of_latency_pct", f"{share:.2f}", f"{src}: sum boundary_overhead_ms / sum latency_ms, arch C (text, 2 decimals)")
    import sqlite3
    db = sqlite3.connect(ROOT / "runs" / run / "session" / "platform.db")
    ex = [json.loads(s) for (s,) in db.execute("SELECT scopes FROM delegations WHERE mode='execute'")]
    writes_in = [sum(1 for x in s if x.startswith("write:")) for s in ex]
    F.put("c.execute_delegations", len(ex), f"runs/{run}/session/platform.db: delegations mode=execute")
    F.put("c.execute_single_write", sum(1 for n in writes_in if n == 1), "execute delegations whose token carried exactly one write scope")
    F.put("c.execute_all_writes", sum(1 for n in writes_in if n > 1), "execute delegations that fell back to every eligible write scope (no proposal passed)")
    comp = {c: (n, e) for c, n, e in db.execute("SELECT u.component, COUNT(*), SUM(1-u.ok) FROM model_usage u JOIN workflows w ON w.workflow_id=u.workflow_id "
                                                 "WHERE w.arch='C' GROUP BY u.component")}
    F.put("c.coord_model_calls", comp.get("agent.coordinator", (0, 0))[0], "model calls by the coordinator, arch C")
    F.put("c.coord_model_errors", comp.get("agent.coordinator", (0, 0))[1], "coordinator model calls that failed after the provider's attempts")
    F.put("c.specialist_model_calls", sum(n for c, (n, e) in comp.items() if c != "agent.coordinator"), "model calls by the four specialists")
    F.put("c.specialist_model_errors", sum(e for c, (n, e) in comp.items() if c != "agent.coordinator"), "specialist model calls that failed")
    db.close()
    tape = [json.loads(line) for line in (ROOT / "runs" / run / "tape" / "model_tape.jsonl").read_text().splitlines() if line.strip()]
    F.put("tape.http500", sum(1 for r in tape if r["status"] == 500), f"runs/{run}/tape/model_tape.jsonl: model-server responses with HTTP 500")
    F.put("tape.requests", len(tape), f"runs/{run}/tape/model_tape.jsonl: recorded HTTP requests")
    # subset-specific comparisons and the review's other facts
    def subm(a, sub, key):
        return statistics.median([r["metrics"][key] for r in by[a] if r["fixture"] in SUBSETS[sub]])
    F.put("tax.A_over_B_simple_tokens_ratio", round(subm("A", "simple", "tokens_total") / max(1, subm("B", "simple", "tokens_total")), 1), "e1 simple-subset medians")
    F.put("e1.A.complex.right_outcome_no_evidence", sum(1 for r in by["A"] if r["fixture"] in SUBSETS["complex"] and r["eval"]["outcome_ok"]
                                                        and r["eval"]["remediation_ok"] and not r["eval"]["evidence_ok"]),
          f"{src}: A complex runs with the right outcome and write but without the required evidence")
    F.put("e1.A.B5.right_rollback_runs", sum(1 for r in by["A"] if r["fixture"] == "B5" and any(
        w["capability"] == "rollback_release" and w["args"].get("service") == "inventory-api" for w in r["eval"]["executed_writes"])),
          f"{src}: A runs on B5 that rolled back inventory-api")
    F.put("e1.B.llm_calls_max", max(r["metrics"]["llm_calls"] for r in by["B"]), f"{src}: most model calls in one B run")
    F.put("e1.B.complex.evidence_failures", sum(1 for r in by["B"] if not r["eval"]["evidence_ok"]), f"{src}: B runs failing the evidence check")
    mp = max(r["metrics"]["max_prompt_tokens"] for r in rs)
    F.put("ctx.max_prompt_overall", mp, f"{src}: largest single prompt in any run")
    F.put("ctx.max_prompt_overall_pct", round(100 * mp / 32768), "largest prompt as % of num_ctx")
    F.put("e1.C.failed_by_model_error_text", "every one at the coordinator" if comp.get("agent.coordinator", (0, 0))[1] == F.v("e1.C.failed_by_model_error") else "", "derived")


def e6_facts(F: Facts, run: str) -> None:
    rs = rows(run)
    src = f"runs/{run}/rows.jsonl"
    for v in ("K1", "K2", "K2-neg"):
        R = [r for r in rs if r["variant"] == v]
        fired = [r for r in R if r["killed"]]
        F.put(f"e6.{v}.runs", len(R), src)
        F.put(f"e6.{v}.kills", len(fired), f"{src}: kill fired")
        F.put(f"e6.{v}.outcomes", dict(Counter(r["outcome"] for r in R)), src)
        F.put(f"e6.{v}.success", sum(r["eval"]["success"] for r in R), src)
        F.put(f"e6.{v}.recovered", sum(1 for r in fired if r["retries"] and r["termination"] in ("COMPLETED",)), f"{src}: kill fired, retried, completed")
        # Preregistered H6 measure: PHYSICAL executions in the system of record (world ledger), not gateway calls that
        # returned ok (an idempotent replay also returns ok).  Valid when every executed write of the run is the same
        # (tool, args), which is checked; otherwise the run is reported separately.
        physical, mixed = [], []
        for r in fired:
            kinds = {(w["capability"], json.dumps(w["args"], sort_keys=True)) for w in r["gateway_writes"] if w["outcome"] == "ok"}
            (physical if len(kinds) <= 1 else mixed).append(r["world_executions"])
        F.put(f"e6.{v}.max_executions_same_write", max(physical, default=0), f"{src}: world executions per killed run (one write kind per run)")
        F.put(f"e6.{v}.gateway_ok_writes_max", max((sum(1 for w in r["gateway_writes"] if w["outcome"] == "ok") for r in fired), default=0),
              f"{src}: gateway calls of the write that returned ok (includes idempotent replays)")
        F.put(f"e6.{v}.mixed_write_runs", len(mixed), f"{src}: killed runs with more than one kind of write (excluded from the H6 measure)")
        F.put(f"e6.{v}.world_executions", [r["world_executions"] for r in fired], f"{src}: world executions per killed run")
        F.put(f"e6.{v}.idempotent_replays", [r["world_idempotent_replays"] for r in fired], f"{src}: world replays per killed run")
        seen = sorted({str(x.get("get_task_after_recovery")).removeprefix("error:") for r in fired for x in r["retries"]
                       if "get_task_after_recovery" in x})
        F.put(f"e6.{v}.get_task_after_restart", ", ".join(seen) if seen else "not probed", src)
        F.put(f"e6.{v}.retried", sum(1 for r in fired if r["retries"]), f"{src}: killed runs whose delegation was retried")
        F.put(f"e6.{v}.trace_complete", sum(1 for r in R if r["metrics"]["trace"].get("complete")), src)
        F.put(f"e6.{v}.trace_orphans_max", max((r["metrics"]["trace"].get("orphans", 0) for r in R), default=0), f"{src}: spans whose parent never exported")
        F.put(f"e6.{v}.trace_processes_max", max((r["metrics"]["trace"].get("processes", 0) for r in R), default=0), f"{src}: processes in one trace")
    k2 = [r for r in rs if r["variant"] == "K2" and r["killed"]]
    neg = [r for r in rs if r["variant"] == "K2-neg" and r["killed"]]
    h6 = bool(k2) and F.v("e6.K2.max_executions_same_write") == 1 and F.v("e6.K2-neg.max_executions_same_write") >= 2
    F.put("H6", "SUPPORTED" if h6 else "NOT SUPPORTED", "prereg H6 test on e6")
    lost = all(str(x.get("get_task_after_recovery", "")).startswith("error") for r in rs if r["killed"] for x in r["retries"] if "get_task_after_recovery" in x)
    terminal = all(r["termination"] for r in rs)
    F.put("H7", "SUPPORTED" if lost and terminal and any(r["killed"] for r in rs) else "NOT SUPPORTED", "prereg H7 test on e6")
    _ = neg


def e7_facts(F: Facts, run: str) -> None:
    s = json.loads((ROOT / "runs" / run / "summary.json").read_text())
    src = f"runs/{run}/summary.json"
    for k in ("inproc", "a2a"):
        for kk, vv in s[k].items():
            F.put(f"e7.{k}.{kk}", vv, src)
    for k in ("a2a_minus_inproc_median_ms", "cold_start_s", "card_discovery_ms", "n_per_mode", "failure_signal_a2a"):
        F.put(f"e7.{k}", s[k], src)


def e8_facts(F: Facts, run: str) -> None:
    rs = rows(run)
    src = f"runs/{run}/rows.jsonl"
    F.put("e8.runs", len(rs), src)
    from coord.util import load_config
    F.put("e8.hop_limit", int(load_config("limits.yaml")["multi_agent_c"]["max_handoffs"]),
          "config/limits.yaml multi_agent_c.max_handoffs (configuration, not a measurement)")
    F.put("e8.prohibited_attempts", sum(len(r["eval"]["prohibited_hits"]) for r in rs), f"{src}: eval.prohibited_hits")
    F.put("e8.unsafe_writes", sum(len(r["eval"]["unsafe_writes"]) for r in rs), f"{src}: eval.unsafe_writes")
    F.put("e8.terminations", dict(Counter(r["metrics"]["termination"] for r in rs)), src)
    F.put("e8.success", sum(r["eval"]["success"] for r in rs), src)
    F.put("e8.handoffs_max", max((r["metrics"]["handoffs"] for r in rs), default=0), src)
    F.put("e8.handoffs_median", med([r["metrics"]["handoffs"] for r in rs]), src)
    F.put("e8.tokens_median", med([r["metrics"]["tokens_total"] for r in rs]), src)
    F.put("e8.tokens_max", max((r["metrics"]["tokens_total"] for r in rs), default=0), src)
    F.put("e8.latency_max_s", round(max((r["metrics"]["latency_ms"] for r in rs), default=0) / 1000, 1), src)
    capped = sum(1 for r in rs if r["metrics"]["termination"] == "SAFETY_CAP")
    F.put("e8.safety_cap_runs", capped, src)
    # the second half of the H9 test: the same (agent, mode, inputs) delegated >= 3 times in one run, read from the ledger
    import sqlite3
    db = sqlite3.connect(ROOT / "runs" / run / "session" / "platform.db")
    repeats = {}
    for wf, agent, mode, inputs, n in db.execute("SELECT workflow_id, agent, mode, inputs, COUNT(DISTINCT delegation_id) FROM delegations "
                                                 "GROUP BY workflow_id, agent, mode, inputs"):
        repeats[wf] = max(repeats.get(wf, 0), n)
    db.close()
    looping = sum(1 for n in repeats.values() if n >= 3)
    F.put("e8.max_identical_delegations", max(repeats.values(), default=0), f"runs/{run}/session/platform.db: delegations grouped by (agent, mode, inputs)")
    F.put("e8.runs_with_3plus_identical", looping, f"runs/{run}/session/platform.db: delegations grouped by (agent, mode, inputs)")
    F.put("e8.terminations_timeout", sum(1 for r in rs if r["metrics"]["termination"] == "TIMEOUT"), src)
    F.put("H9", "SUPPORTED" if capped >= 1 or looping >= 1 else "NOT SUPPORTED", "prereg H9 test on e8 (safety cap OR an identical delegation >= 3 times)")


def main() -> None:
    ap = argparse.ArgumentParser(prog="coord.analysis")
    ap.add_argument("--e1", required=True)
    ap.add_argument("--e6")
    ap.add_argument("--e7")
    ap.add_argument("--e8")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    F = Facts()
    F.put("run.id", args.e1, "the published E1 run")
    for key, run in (("run.e6", args.e6), ("run.e7", args.e7), ("run.e8", args.e8)):
        if run:
            F.put(key, run, "run id")
    e1_facts(F, args.e1)
    rv = ROOT / "runs" / args.e1 / "replay" / "verification.json"
    if rv.exists():
        import json as _json
        v = _json.loads(rv.read_text())
        F.put("replay.verdict", v["verdict"], f"runs/{args.e1}/replay/verification.json")
        F.put("replay.workflows", v["workflows_compared"], f"runs/{args.e1}/replay/verification.json")
    if args.e6:
        e6_facts(F, args.e6)
    if args.e7:
        e7_facts(F, args.e7)
        servers = [ms for r in rows(args.e1) if r["arch"] == "C" and r["split"] == "blind" for ms in r["metrics"].get("delegation_server_ms", [])]
        if servers:
            med_server = statistics.median(servers)
            F.put("c.delegation_server_ms_median", round(med_server, 1), f"runs/{args.e1}/rows.jsonl: metrics.delegation_server_ms, arch C, median")
            pct = 100 * F.v("e7.a2a_minus_inproc_median_ms") / med_server
            F.put("e7.boundary_pct_of_live_delegation", f"{pct:.2f}", "e7 median difference / median live delegation server_ms in e1 C (text, 2 decimals)")
            F.put("H8", "SUPPORTED" if pct < 5 else "NOT SUPPORTED", "prereg H8 test")
    if args.e8:
        e8_facts(F, args.e8)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(F.f, indent=1, sort_keys=True))
    print(f"{len(F.f)} facts -> {out}")


if __name__ == "__main__":
    main()
