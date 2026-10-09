"""agentops: the O1 + O2 POC's command line.

    agentops demo                         the story in one run: a surge with and without admission, then a canary
    agentops scenario E1 [--arm naive]    one scenario, every arm (or one), summarised
    agentops record --run-id <id>         a new recorded run -> runs/<id>/   (python -m agentops.run record does the same)
    agentops explain <card> [--run-id]    a recorded decision, explained from the run's files (docs/explain/ cards)
    agentops prereg-check                 frozen files unchanged since the freeze?
    agentops freeze                       write experiments/FROZEN.sha256 (before the recorded run only)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

from . import run as R
from . import scenarios as SC
from .common import EXPERIMENTS, RUNS, freeze, prereg_check

CARDS = ["E1-surge", "E4-runaway", "E5-routing", "E8-release", "E9-gate", "E10-canary"]


def published() -> str:
    return (RUNS / "PUBLISHED").read_text().strip()


def explain(card: str, run_id: str) -> str:
    run = RUNS / run_id
    f = {k: v["value"] for k, v in json.loads((run / "facts.json").read_text()).items()}
    L: list[str] = []
    if card == "E1-surge":
        L += [f"E1 · Black Friday surge: {f['cfg.e1_surge_rate']} requests/s for {f['cfg.e1_surge_s']} s against {f['cfg.slots']} slots",
              "", f"{'':28}{'open admission':>18}{'bounded admission':>20}"]
        for label, k in (("support requests", "requests"), ("attempts (retries incl.)", "attempts"), ("max work in system", "max_work_in_system"),
                         ("max queued", "max_queued"), ("p99 queue delay, ms", "queue_p99_ms"), ("refused explicitly", "refused"),
                         ("served while waiting", "served"), ("goodput %", "goodput_pct"), ("cu on abandoned work %", "wasted_cu_pct")):
            L.append(f"{label:28}{f['e1.naive.' + k]!s:>18}{f['e1.controlled.' + k]!s:>20}")
        L += ["", f"bound: work in system <= slots + queue bound = {f['cfg.work_in_system_bound']}; over it -> 429 + Retry-After {f['cfg.retry_after_s']} s"]
    elif card == "E4-runaway":
        lim = json.loads((run / "scenarios/E4/limits.json").read_text())["refund-dispute"]
        L += ["E4 · a refund whose payment stays PENDING: the agent re-checks it forever", "",
              "envelope (refund-dispute, calibrated on the development sample x 1.25):",
              "  " + " · ".join(f"{k} {v}" for k, v in lim.items() if v is not None), "",
              f"{'':16}{'result':>18}{'steps':>8}{'model':>8}{'tools':>8}{'cu':>10}"]
        for arm in ("none", "per-agent", "envelope"):
            k = f"e4.{arm}.runaway"
            L.append(f"{arm:16}{f[k + '.result']:>18}{f[k + '.steps']:>8}{f[k + '.model_calls']:>8}{f[k + '.tool_calls']:>8}{f[k + '.cost_cu']:>10}")
        L += ["", f"stopped on: {f['e4.envelope.runaway.reason']} · the harness guard ({f['cfg.harness_guard_steps']} steps) is not a platform control"]
    elif card == "E5-routing":
        L += ["E5 · 800 workflows, the EU private deployment throttled for 30 s", "",
              f"{'':22}{'success %':>10}{'cu/req':>9}{'cu/success':>12}{'+escalation':>13}{'cap.viol':>10}{'data viol':>11}{'deferred':>10}"]
        for arm in ("all-large", "all-small", "routed", "routed-any-fallback"):
            k = f"e5.{arm}"
            L.append(f"{arm:22}{f[k + '.success_pct']:>10}{f[k + '.cost_per_request']:>9}{f[k + '.cost_per_success']:>12}"
                     f"{f[k + '.cost_per_success_incl_escalation']:>13}{f[k + '.capability_violations']:>10}{f[k + '.data_violations']:>11}{f[k + '.deferred']:>10}")
        L += ["", "the success table is a declared assumption (config/models.toml), not a measurement of any model"]
    elif card == "E8-release":
        diffs = json.loads((run / "scenarios/E8/diffs.json").read_text())
        L += ["E8 · the same code, seven releases", "", f"image digest (code): {f['e8.image_digest']}  (identical for all {f['e8.releases']})", ""]
        L.append(f"{'release':12}{'release id':>18}  {'changed artifact':24}{'tools/wf':>9}{'cu/wf':>8}")
        for n in ["R41"] + list(diffs):
            L.append(f"{n:12}{f['e8.' + n + '.release_id']:>18}  {(', '.join(diffs[n]['artifacts']) if n in diffs else '(production)'):24}"
                     f"{f['e8.' + n + '.tool_calls_per_wf']:>9}{f['e8.' + n + '.cost_per_wf']:>8}")
    elif card == "E9-gate":
        L += [f"E9 · offline suite ({f['e9.cases']} cases) and invariant gates", "",
              f"{'candidate':12}{'task ok':>8}{'data':>6}{'approval':>10}{'envelope':>10}{'cost Δ%':>9}  decision"]
        for n in ("R42-a", "R42-b", "R42-c", "R42-d", "R42-e"):
            k = f"e9.{n}"
            dec = "BLOCKED" if n in f["e9.blocked"] else "PASSED"
            L.append(f"{n:12}{f[k + '.task_success']:>8}{f[k + '.inv.data_policy']:>6}{f[k + '.inv.approval_bypass']:>10}"
                     f"{f[k + '.inv.envelope_unenforceable']:>10}{round(f[k + '.cost_delta_pct'], 1) + 0.0:>+9.1f}  {dec}")
        L += ["", f"canary traffic granted to blocked candidates: {f['e9.blocked_weight_granted']} %"]
    elif card == "E10-canary":
        c = json.loads((run / "scenarios/E10/R42-a__mix-adjusted/canary.json").read_text())
        L += [f"E10 · canary {c['candidate']} ({c['candidate_id']}) vs R41 ({c['baseline_id']}), {f['cfg.canary_window']} candidate workflows per window", ""]
        for w in c["windows"]:
            d = w["deltas"]
            L.append(f"stage {w['stage_pct']}% window {w['window']}: error {d['error_pp']:+.1f} pp · success {d['success_pp']:+.1f} pp · "
                     f"p95 {d['p95_pct']:+.1f}% · cost/success {d['cost_per_success_pct']:+.1f}% · tool calls/wf {d['tool_calls_pct']:+.1f}%")
            L.append(f"  breaches: {', '.join(w['breaches']) or 'none'}")
        L += ["", f"decision: {c['decision']} at {c['decided_at_ms'] / 1000:.1f} s · requests to the candidate afterwards: "
                  f"{f['e10.R42-a.mix-adjusted.candidate_after_decision']}",
              f"replies already sent by the candidate: {c['effects']['by_candidate_before_decision']} · undone by the rollback: {c['effects']['reverted_by_rollback']}"]
    else:
        raise SystemExit(f"unknown card {card}; one of {', '.join(CARDS)}")
    return "\n".join(L)


def demo() -> None:
    print("Northwind Goods, Black Friday. One shared agent platform, two ways to run it.\n")
    for arm in ("naive", "controlled"):
        a = SC.e1(arm)
        served = sum(q["served"] for q in a.requests)
        print(f"  {arm:11} admission: {len(a.requests)} requests, {len(a.rows)} attempts, max work in system {a.stats['max']['work_in_system']}, "
              f"served {served} ({100 * served / len(a.requests):.1f} %)")
    print("\nCyber Monday. R42-a changes one tool description and no code. The canary:\n")
    c = SC.canary("R42-a")
    for w in c["windows"]:
        d = w["deltas"]
        print(f"  window {w['window']} at {w['stage_pct']} %: error {d['error_pp']:+.1f} pp, cost/success {d['cost_per_success_pct']:+.1f} %, "
              f"tool calls/wf {d['tool_calls_pct']:+.1f} % -> {', '.join(w['breaches']) or 'pass'}")
    print(f"\n  decision: {c['decision']}; replies already sent by the candidate: {c['effects']['by_candidate_before_decision']} (a rollback does not unsend them)")
    print("\nSimulation units only (sim-ms, cu). See README.md for what this does and does not prove.")


def main() -> None:
    ap = argparse.ArgumentParser(prog="agentops")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    s = sub.add_parser("scenario")
    s.add_argument("scenario")
    s.add_argument("--arm")
    r = sub.add_parser("record")
    r.add_argument("--run-id", required=True)
    e = sub.add_parser("explain")
    e.add_argument("card")
    e.add_argument("--run-id")
    e.add_argument("--write", action="store_true", help="write ../docs/explain/<card>.txt")
    sub.add_parser("prereg-check")
    sub.add_parser("freeze")
    o = ap.parse_args()
    if o.cmd == "demo":
        demo()
    elif o.cmd == "scenario":
        fn = {"E1": SC.e1, "E2": SC.e2, "E3": SC.e3, "E5": SC.e5, "E7": SC.e7}.get(o.scenario)
        if fn is None:
            raise SystemExit("scenario takes E1, E2, E3, E5 or E7 (the others: agentops explain, or a full record)")
        for arm in [o.arm] if o.arm else R.ARMS[o.scenario]:
            a = fn(arm)
            reqs = [q for q in a.requests if q["tenant"] == "support"] or a.rows
            served = sum(q.get("served", q.get("result") == "SUCCESS") for q in reqs)
            print(f"{o.scenario} {arm:12} rows {len(a.rows):6}  max {a.stats['max']}  support served {100 * served / max(len(reqs), 1):.1f} %")
    elif o.cmd == "record":
        R.record(o.run_id)
        print(f"recorded runs/{o.run_id}")
    elif o.cmd == "explain":
        rid = o.run_id or published()
        text = explain(o.card, rid)
        print(text)
        if o.write:
            p = EXPERIMENTS.parent.parent / "docs" / "explain" / f"{o.card}.txt"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text + "\n")
    elif o.cmd == "prereg-check":
        changed = prereg_check()
        print("unchanged since the freeze" if not changed else "CHANGED: " + ", ".join(changed))
        sys.exit(1 if changed else 0)
    elif o.cmd == "freeze":
        freeze()
        (EXPERIMENTS / "FROZEN.at").write_text(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") + "\n")
        print("frozen:", (EXPERIMENTS / "FROZEN.sha256").read_text())


if __name__ == "__main__":
    main()
