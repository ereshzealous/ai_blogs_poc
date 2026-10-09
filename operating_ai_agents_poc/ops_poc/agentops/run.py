"""Record a run and aggregate its facts.

    uv run python -m agentops.run record --run-id 2026-10-08-recorded      every scenario -> runs/<id>/ (raw files)
    uv run python -m agentops.run aggregate --run-id <id>                  runs/<id>/facts.json + summary.md from the raw files

`record` writes only raw evidence (rows, requests, timelines, stats, decision logs, release manifests) and then calls
`aggregate`, which reads those files back from disk. facts.json is therefore a function of the written files alone;
tools/verify_evidence.py recomputes it in a scratch copy and compares. Wall-clock timings go to volatile/ only.
"""

from __future__ import annotations

import argparse
import json
import platform as _platform
import sys
import time
from pathlib import Path

from . import scenarios as SC
from .common import RUNS, cfg, dump, experiments, frozen_sha256, pct, r1, r2, source_sha256

ARMS = {"E1": ["naive", "controlled"], "E2": ["naive", "controlled"], "E3": ["naive", "controlled"],
        "E5": ["all-large", "all-small", "routed", "routed-any-fallback"], "E7": ["naive", "controlled", "composed"]}


def jl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows))


def wj(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump(obj))


def write_arm(d: Path, arm) -> None:
    jl(d / "rows.jsonl", arm.rows)
    jl(d / "requests.jsonl", arm.requests)
    jl(d / "timeline.jsonl", arm.timeline)
    wj(d / "stats.json", arm.stats)


def record(run_id: str) -> Path:
    run = RUNS / run_id
    if run.exists() and any(run.iterdir()):
        raise SystemExit(f"runs/{run_id} exists: a recorded run is never overwritten")
    run.mkdir(parents=True, exist_ok=True)
    timing = {}
    for scn, fn in (("E1", SC.e1), ("E2", SC.e2), ("E3", SC.e3), ("E5", SC.e5), ("E7", SC.e7)):
        for arm in ARMS[scn]:
            t = time.time()
            write_arm(run / "scenarios" / scn / arm, fn(arm))
            timing[f"{scn}/{arm}"] = round(time.time() - t, 2)
    t = time.time()
    e4 = SC.e4()
    wj(run / "scenarios" / "E4" / "limits.json", e4["limits"])
    for arm in experiments("scenarios")["E4"]["arms"]:
        jl(run / "scenarios" / "E4" / arm / "rows.jsonl", e4[arm])
    timing["E4"] = round(time.time() - t, 2)
    e6 = SC.e6()
    jl(run / "scenarios" / "E6" / "retrieval.jsonl", e6["retrieval"])
    jl(run / "scenarios" / "E6" / "cache.jsonl", e6["cache"])
    t = time.time()
    e8 = SC.e8()
    for name, doc in e8["releases"].items():
        wj(run / "scenarios" / "E8" / "releases" / f"{name}.json", doc)
        jl(run / "scenarios" / "E8" / "rows" / f"{name}.jsonl", e8["rows"][name])
    wj(run / "scenarios" / "E8" / "diffs.json", e8["diffs"])
    timing["E8"] = round(time.time() - t, 2)
    e9 = SC.e9()
    for name, ev in [("R41", e9["baseline"])] + list(e9["candidates"].items()):
        jl(run / "scenarios" / "E9" / "rows" / f"{name}.jsonl", ev.pop("rows"))
        wj(run / "scenarios" / "E9" / "evals" / f"{name}.json", ev)
    wj(run / "scenarios" / "E9" / "registry.json", e9["registry"])
    t = time.time()
    for key, c in SC.e10().items():
        d = run / "scenarios" / "E10" / key.replace(":", "__")
        jl(d / "rows.jsonl", c.pop("rows"))
        wj(d / "canary.json", c)
    timing["E10"] = round(time.time() - t, 2)
    write_arm(run / "negative-control", SC.nc())
    man = {"run_id": run_id, "schema": "o1o2-run/v1", "python": sys.version.split()[0], "platform": f"{_platform.system()} {_platform.machine()}",
           "seed": experiments("scenarios")["seed"], "scenarios": ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10"],
           "arms": {k: v for k, v in ARMS.items()} | {"E4": experiments("scenarios")["E4"]["arms"]},
           "negative_control": "NC: E1 controlled arm with the admission bound removed",
           "units": {"time": "simulated milliseconds (sim-ms)", "cost": "cost units (cu)"},
           "source_sha256": source_sha256(), "frozen_sha256": frozen_sha256(), "model_calls": 0, "network": False}
    wj(run / "manifest.json", man)
    wj(run / "volatile" / "timing.json", {"seconds": timing})
    aggregate(run)
    return run


# ---- aggregation: facts from the written files ------------------------------------------------------------------------------

def rd(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def rj(p: Path):
    return json.loads(p.read_text())


class F:
    def __init__(self, run: Path):
        self.run, self.d = run, {}

    def add(self, key: str, value, source: str, derivation: str | None = None) -> None:
        if key in self.d:
            raise SystemExit(f"fact {key} twice")
        self.d[key] = {"value": value, "source": source, **({"derivation": derivation} if derivation else {})}


def machine(r: dict) -> float:
    return sum(v for k, v in r["cost_cu"].items() if k != "escalation")


def total(r: dict) -> float:
    return sum(r["cost_cu"].values())


def load_arm(run: Path, d: str) -> tuple[list, list, dict]:
    p = run / d
    return rd(p / "rows.jsonl"), rd(p / "requests.jsonl"), rj(p / "stats.json")


def support_summary(f: F, key: str, src: str, rows, reqs, stats, maxima: bool = True) -> None:
    sup = [q for q in reqs if q["tenant"] == "support"]
    srows = [r for r in rows if r["tenant"] == "support"]
    n = len(sup)
    served = sum(q["served"] for q in sup)
    f.add(f"{key}.requests", n, f"{src}/requests.jsonl", "support requests")
    f.add(f"{key}.attempts", len(srows), f"{src}/rows.jsonl", "support attempts submitted (retries included)")
    f.add(f"{key}.retry_amplification", r2(len(srows) / n), f"{src}/rows.jsonl", "support attempts / support requests")
    f.add(f"{key}.served", served, f"{src}/requests.jsonl", "requests with a SUCCESS attempt that finished while the client still waited")
    f.add(f"{key}.goodput_pct", r1(100 * served / n), f"{src}/requests.jsonl", "served / requests")
    refused = sum(q["outcome"] == "REFUSED" for q in sup)
    f.add(f"{key}.refused", refused, f"{src}/requests.jsonl", "requests refused with an explicit capacity error after their one polite retry")
    f.add(f"{key}.refused_pct", r1(100 * refused / n), f"{src}/requests.jsonl")
    f.add(f"{key}.gave_up", sum(q["outcome"] == "GAVE_UP" for q in sup), f"{src}/requests.jsonl", "requests whose client gave up on every attempt")
    qd = sorted(r["queue_delay_ms"] for r in srows if r["start_ms"] is not None)
    f.add(f"{key}.queue_p50_ms", pct(qd, 50), f"{src}/rows.jsonl", "nearest-rank p50 of queue delay, attempts that started")
    f.add(f"{key}.queue_p99_ms", pct(qd, 99), f"{src}/rows.jsonl", "nearest-rank p99 of queue delay, attempts that started")
    lat = sorted(r["latency_ms"] for r in srows if r["result"] == "SUCCESS")
    for p in (50, 95, 99):
        f.add(f"{key}.latency_p{p}_ms", pct(lat, p), f"{src}/rows.jsonl", f"nearest-rank p{p} of arrival-to-end, successful support attempts")
    wasted = [r for r in srows if r["client_waiting"] is False and r["start_ms"] is not None]
    all_cu = sum(total(r) for r in rows)
    f.add(f"{key}.wasted_completions", sum(r["result"] == "SUCCESS" for r in wasted), f"{src}/rows.jsonl",
          "successful attempts that finished after their client had given up")
    f.add(f"{key}.wasted_cu_pct", r1(100 * sum(total(r) for r in wasted) / all_cu) if all_cu else 0, f"{src}/rows.jsonl",
          "cu spent on attempts that ended after their client gave up / all cu")
    f.add(f"{key}.cost_cu", r1(all_cu), f"{src}/rows.jsonl", "every attempt, every cost component")
    f.add(f"{key}.started_after_deadline", sum(1 for r in srows if r["start_ms"] is not None and r["deadline_ms"] is not None and r["start_ms"] > r["deadline_ms"]),
          f"{src}/rows.jsonl", "attempts that started after their client's deadline")
    for k in ("active", "queued", "work_in_system") if maxima else ():
        f.add(f"{key}.max_{k}", stats["max"][k], f"{src}/stats.json", "maximum over every event of the run (platform counter)")
    res = {}
    for r in srows:
        res[r["result"]] = res.get(r["result"], 0) + 1
    for k in ("REJECTED_CAPACITY", "SHED_DEADLINE", "CANCELLED_DEADLINE", "FAILED_TOOL", "UNFINISHED"):
        f.add(f"{key}.results.{k}", res.get(k, 0), f"{src}/rows.jsonl", f"support attempts ending {k}")


def aggregate(run: Path) -> dict:
    run = Path(run)
    f = F(run)
    S = experiments("scenarios")
    plat = cfg("platform")
    f.add("run.id", run.name, "manifest.json")
    f.add("cfg.slots", plat["runtime"]["slots"], "config/platform.toml")
    f.add("cfg.capacity", plat["runtime"]["capacity"], "config/platform.toml")
    f.add("cfg.queue_bound", plat["admission"]["queue_bound"], "config/platform.toml")
    f.add("cfg.work_in_system_bound", plat["runtime"]["slots"] + plat["admission"]["queue_bound"], "config/platform.toml", "slots + queue_bound")
    f.add("cfg.client_timeout_s", plat["client"]["timeout_ms"] // 1000, "config/platform.toml")
    f.add("cfg.naive_retries", plat["client"]["naive_retries"], "config/platform.toml")
    f.add("cfg.retry_after_s", plat["admission"]["retry_after_ms"] // 1000, "config/platform.toml")
    f.add("cfg.finance_bulkhead", plat["tenants"]["finance"]["max_concurrency"], "config/platform.toml")
    f.add("cfg.weights", f"{plat['tenants']['support']['weight']}:{plat['tenants']['finance']['weight']}", "config/platform.toml")
    f.add("cfg.harness_guard_steps", plat["runtime"]["harness_guard_steps"], "config/platform.toml")
    tools = cfg("tools")["tools"]["payments.status"]
    f.add("cfg.payments_capacity", tools["capacity"], "config/tools.toml")
    f.add("cfg.payments_hard_limit", tools["hard_limit"], "config/tools.toml")
    f.add("cfg.payments_rps", tools["rps"], "config/tools.toml")
    f.add("cfg.e7_slots", S["E7"]["slots"], "experiments/scenarios.toml")
    f.add("cfg.e1_surge_rate", S["E1"]["phases"][0][1], "experiments/scenarios.toml")
    f.add("cfg.e1_surge_s", S["E1"]["phases"][0][0] // 1000, "experiments/scenarios.toml")
    f.add("cfg.e2_finance_items", S["E2"]["finance_items"], "experiments/scenarios.toml")
    f.add("cfg.e2_support_rate", S["E2"]["support_phases"][0][1], "experiments/scenarios.toml")
    f.add("cfg.batch_deadline_s", plat["tenants"]["finance"]["batch_deadline_ms"] // 1000, "config/platform.toml")
    f.add("cfg.canary_window", S["E10"]["window"], "experiments/scenarios.toml")
    f.add("cfg.canary_stages", " / ".join(str(x) for x in S["E10"]["stages"]), "experiments/scenarios.toml")
    g10 = next(h for h in experiments("preregistration")["hypotheses"] if h["id"] == "H10")["guardrails"]
    for k, v in g10.items():
        f.add(f"cfg.guardrail.{k}", v, "experiments/preregistration.toml")
    g9 = next(h for h in experiments("preregistration")["hypotheses"] if h["id"] == "H9")["gate"]
    for k, v in g9.items():
        f.add(f"cfg.gate.{k}", v, "experiments/preregistration.toml")

    # ---- E1, E3 ------------------------------------------------------------------------------------------------------
    for scn in ("E1", "E3"):
        for arm in ARMS[scn]:
            src = f"scenarios/{scn}/{arm}"
            support_summary(f, f"{scn.lower()}.{arm}", src, *load_arm(run, src))
    src = "negative-control"
    rows, reqs, stats = load_arm(run, src)
    f.add("nc.max_work_in_system", stats["max"]["work_in_system"], f"{src}/stats.json")
    f.add("nc.max_active", stats["max"]["active"], f"{src}/stats.json")
    f.add("nc.harness_completed", int(all(r["result"] is not None for r in rows)), f"{src}/rows.jsonl", "every attempt reached a recorded result")
    f.add("nc.goodput_pct", r1(100 * sum(q["served"] for q in reqs) / len(reqs)), f"{src}/requests.jsonl")

    # ---- E2 ------------------------------------------------------------------------------------------------------------
    for arm in ARMS["E2"]:
        src = f"scenarios/E2/{arm}"
        rows, reqs, stats = load_arm(run, src)
        support_summary(f, f"e2.{arm}.support", src, rows, reqs, stats, maxima=False)
        fin = [q for q in reqs if q["tenant"] == "finance"]
        done = [q for q in fin if q["outcome"] in ("SUCCESS", "ESCALATED")]
        f.add(f"e2.{arm}.finance.completed", len(done), f"{src}/requests.jsonl", "finance items that reached an answer (success or escalation)")
        mk = max(q["end_ms"] for q in done) - min(q["first_ms"] for q in fin)
        f.add(f"e2.{arm}.finance.makespan_s", r1(mk / 1000), f"{src}/requests.jsonl", "first submission to last completion, simulated seconds")
        f.add(f"e2.{arm}.finance.max_active", stats["max_by_tenant"]["finance"]["active"], f"{src}/stats.json")
        f.add(f"e2.{arm}.support.max_active", stats["max_by_tenant"]["support"]["active"], f"{src}/stats.json")
    f.add("e2.makespan_ratio", r2(f.d["e2.controlled.finance.makespan_s"]["value"] / f.d["e2.naive.finance.makespan_s"]["value"]),
          "scenarios/E2/*/requests.jsonl", "controlled makespan / naive makespan")

    # ---- E4 ------------------------------------------------------------------------------------------------------------
    lim = rj(run / "scenarios/E4/limits.json")
    for wf in ("refund-dispute", "dispute-investigation", "order-status", "delivery-change"):
        for d in ("steps", "model_calls", "tool_calls", "cost_cu", "fanout", "wall_ms"):
            if lim[wf].get(d) is not None:
                f.add(f"e4.limit.{wf}.{d}", lim[wf][d], "scenarios/E4/limits.json", "max over the development sample x 1.25, rounded up")
    for arm in S["E4"]["arms"]:
        src = f"scenarios/E4/{arm}/rows.jsonl"
        rows = rd(run / src)
        by = {r["request_id"]: r for r in rows}
        for tag, rid in (("runaway", "E4-RUNAWAY"), ("coord", "E4-COORD")):
            r = by[rid]
            f.add(f"e4.{arm}.{tag}.result", r["result"], src)
            f.add(f"e4.{arm}.{tag}.steps", r["steps"], src)
            f.add(f"e4.{arm}.{tag}.model_calls", r["model_calls"], src, "children included")
            f.add(f"e4.{arm}.{tag}.tool_calls", r["tool_calls"], src, "children included")
            f.add(f"e4.{arm}.{tag}.cost_cu", r1(total(r)), src, "children included")
            f.add(f"e4.{arm}.{tag}.reason", r["budget_reason"] or "none", src)
        legit = [r for r in rows if r["request_id"] not in ("E4-RUNAWAY", "E4-COORD")]
        cut = [r for r in legit if r["result"] == "BUDGET_EXCEEDED"]
        f.add(f"e4.{arm}.legit_n", len(legit), src)
        f.add(f"e4.{arm}.legit_cut", len(cut), src, "blind-sample workflows (no injected pathology) stopped by the envelope")
        f.add(f"e4.{arm}.legit_cut_ids", ", ".join(r["request_id"] for r in cut) or "none", src)
        f.add(f"e4.{arm}.legit_cut_reasons", "; ".join(sorted({f"{r['workflow']} ({r['budget_reason']})" for r in cut})) or "none", src)
        f.add(f"e4.{arm}.legit_cut_rerun", sum(r["workflow_attempts"] > 1 for r in cut), src, "cut workflows that had re-run after a wrong answer")
        coords = [r for r in legit if r["workflow"] == "dispute-investigation"]
        f.add(f"e4.{arm}.coord_model_calls_mean", r1(sum(r["model_calls"] for r in coords) / len(coords)), src)
    f.add("e4.runaway_cost_ratio", round(f.d["e4.none.runaway.cost_cu"]["value"] / f.d["e4.envelope.runaway.cost_cu"]["value"]),
          "scenarios/E4/*/rows.jsonl", "unbounded runaway cost / enveloped runaway cost")
    f.add("e4.coord_cost_ratio", round(f.d["e4.none.coord.cost_cu"]["value"] / f.d["e4.envelope.coord.cost_cu"]["value"]),
          "scenarios/E4/*/rows.jsonl")

    # ---- E5 ------------------------------------------------------------------------------------------------------------
    for arm in ARMS["E5"]:
        src = f"scenarios/E5/{arm}"
        rows = rd(run / src / "rows.jsonl")
        n = len(rows)
        succ = sum(r["result"] == "SUCCESS" for r in rows)
        mach = sum(machine(r) for r in rows)
        esc = sum(r["cost_cu"]["escalation"] for r in rows)
        k = f"e5.{arm}"
        f.add(f"{k}.n", n, f"{src}/rows.jsonl")
        f.add(f"{k}.success_pct", r1(100 * succ / n), f"{src}/rows.jsonl", "workflows that ended SUCCESS (after at most one re-run)")
        f.add(f"{k}.wrong_first", sum(r["workflow_attempts"] > 1 or r["result"] == "ESCALATED" for r in rows), f"{src}/rows.jsonl",
              "workflows whose first answer was wrong (caught by the declared validator)")
        f.add(f"{k}.escalated", sum(r["result"] == "ESCALATED" for r in rows), f"{src}/rows.jsonl")
        f.add(f"{k}.deferred", sum(r["result"] == "DEFERRED" for r in rows), f"{src}/rows.jsonl", "explicitly deferred during the throttle")
        f.add(f"{k}.cost_per_request", r2(mach / n), f"{src}/rows.jsonl", "machine cu / workflows")
        f.add(f"{k}.cost_per_success", r2(mach / succ), f"{src}/rows.jsonl", "machine cu (every attempt and re-run) / successes")
        f.add(f"{k}.cost_per_success_incl_escalation", r2((mach + esc) / succ), f"{src}/rows.jsonl", "plus the declared 60 cu per escalation")
        f.add(f"{k}.capability_violations", sum(r["capability_violations"] for r in rows), f"{src}/rows.jsonl", "model calls below the task's min tier")
        f.add(f"{k}.data_violations", sum(r["data_violations"] for r in rows), f"{src}/rows.jsonl", "model calls on a profile not allowed the data class")
        f.add(f"{k}.fallbacks", sum(r["fallbacks"] for r in rows), f"{src}/rows.jsonl")
        f.add(f"{k}.latency_p95_ms", pct(sorted(r["latency_ms"] for r in rows if r["result"] == "SUCCESS"), 95), f"{src}/rows.jsonl")
        f.add(f"{k}.mach_cu", r1(mach), f"{src}/rows.jsonl")
        f.add(f"{k}.successes", succ, f"{src}/rows.jsonl")
    cr = f.d["e5.routed.cost_per_success"]["value"]
    small_m, small_s, small_e = f.d["e5.all-small.mach_cu"]["value"], f.d["e5.all-small.successes"]["value"], f.d["e5.all-small.escalated"]["value"]
    f.add("e5.break_even_escalation_cu", round((cr * small_s - small_m) / small_e) if small_e else None, "scenarios/E5/*/rows.jsonl",
          "the cost a person handling one escalation would need to exceed for all-small's cost per success to reach routed's")
    f.add("e5.routed_vs_large_pct", r1(100 * (1 - cr / f.d["e5.all-large.cost_per_success"]["value"])), "scenarios/E5/*/rows.jsonl",
          "1 - routed cost per success / all-large cost per success")

    # ---- E6 ------------------------------------------------------------------------------------------------------------
    rr = rd(run / "scenarios/E6/retrieval.jsonl")
    for mode in ("naive", "bounded"):
        xs = [x for x in rr if x["mode"] == mode]
        f.add(f"e6.{mode}.queries", len(xs), "scenarios/E6/retrieval.jsonl")
        f.add(f"e6.{mode}.context_tokens_mean", round(sum(x["context_tokens"] for x in xs) / len(xs)), "scenarios/E6/retrieval.jsonl",
              "system + history + admitted chunks, mean over the fixture queries")
        f.add(f"e6.{mode}.chunks_retrieved", sum(x["retrieved"] for x in xs), "scenarios/E6/retrieval.jsonl")
        f.add(f"e6.{mode}.sources_queried", sum(x["sources"] for x in xs), "scenarios/E6/retrieval.jsonl")
        f.add(f"e6.{mode}.missing_required", sum(len(x["missing_required"]) for x in xs), "scenarios/E6/retrieval.jsonl",
              "required evidence ids (declared in the fixture) absent from the admitted context")
        f.add(f"e6.{mode}.retrieval_cost_cu", r2(sum(x["retrieval_cost_cu"] for x in xs)), "scenarios/E6/retrieval.jsonl")
    f.add("e6.required_ids", sum(len(x["required"]) for x in rr if x["mode"] == "bounded"), "scenarios/E6/retrieval.jsonl")
    f.add("e6.token_reduction_pct", r1(100 * (1 - f.d["e6.bounded.context_tokens_mean"]["value"] / f.d["e6.naive.context_tokens_mean"]["value"])),
          "scenarios/E6/retrieval.jsonl")
    cc = rd(run / "scenarios/E6/cache.jsonl")
    for c in ("query-text", "scoped"):
        xs = [x for x in cc if x["cache"] == c]
        k = f"e6.cache.{c}"
        f.add(f"{k}.lookups", len(xs), "scenarios/E6/cache.jsonl")
        f.add(f"{k}.hits", sum(x["hit"] for x in xs), "scenarios/E6/cache.jsonl")
        f.add(f"{k}.cross_principal", sum(x["cross_principal"] for x in xs), "scenarios/E6/cache.jsonl",
              "a personal answer cached for one customer served to another")
        f.add(f"{k}.stale", sum(x["stale"] for x in xs), "scenarios/E6/cache.jsonl", "an entry from an older knowledge or policy version served")

    # ---- E7 ------------------------------------------------------------------------------------------------------------
    for arm in ARMS["E7"]:
        src = f"scenarios/E7/{arm}"
        rows, reqs, stats = load_arm(run, src)
        ps = stats["tools"]["payments.status"]
        k = f"e7.{arm}"
        f.add(f"{k}.max_inflight", ps["max_inflight"], f"{src}/stats.json", "payments-status calls in flight, maximum over the run")
        f.add(f"{k}.http_503", ps["503"], f"{src}/stats.json")
        f.add(f"{k}.http_429", ps["429"], f"{src}/stats.json")
        f.add(f"{k}.http_200", ps["200"], f"{src}/stats.json")
        logical = sum(r["tool_calls"] for r in rows) + sum(r["result"] == "FAILED_TOOL" for r in rows)
        f.add(f"{k}.attempts_per_call", r2(sum(r["tool_attempts"] for r in rows) / logical), f"{src}/rows.jsonl",
              "downstream attempts / logical tool calls (a failed step counts once)")
        f.add(f"{k}.completed", sum(r["result"] in ("SUCCESS", "ESCALATED") for r in rows), f"{src}/rows.jsonl", "workflows that reached an answer")
        f.add(f"{k}.failed_tool", sum(r["result"] == "FAILED_TOOL" for r in rows), f"{src}/rows.jsonl")
        sup = [q for q in reqs if q["tenant"] == "support"]
        fin = [q for q in reqs if q["tenant"] == "finance"]
        f.add(f"{k}.support_goodput_pct", r1(100 * sum(q["served"] for q in sup) / len(sup)), f"{src}/requests.jsonl")
        fdone = [q for q in fin if q["outcome"] in ("SUCCESS", "ESCALATED")]
        f.add(f"{k}.finance_completed", len(fdone), f"{src}/requests.jsonl")
        f.add(f"{k}.finance_makespan_s", r1((max(q["end_ms"] for q in fdone) - min(q["first_ms"] for q in fin)) / 1000) if fdone else 0, f"{src}/requests.jsonl")
    f.add("cfg.e7_finance_items", S["E7"]["finance_items"], "experiments/scenarios.toml")

    # ---- E8 ------------------------------------------------------------------------------------------------------------
    names = ["R41"] + S["E8"]["candidates"]
    docs = {n: rj(run / f"scenarios/E8/releases/{n}.json") for n in names}
    diffs = rj(run / "scenarios/E8/diffs.json")
    f.add("e8.releases", len(names), "scenarios/E8/releases/")
    f.add("e8.distinct_release_ids", len({d["release_id"] for d in docs.values()}), "scenarios/E8/releases/*.json")
    f.add("e8.distinct_image_digests", len({d["image_digest"] for d in docs.values()}), "scenarios/E8/releases/*.json")
    f.add("e8.image_digest", docs["R41"]["image_digest"], "scenarios/E8/releases/R41.json")
    f.add("e8.max_artifacts_changed", max(len(v["artifacts"]) for v in diffs.values()), "scenarios/E8/diffs.json")
    f.add("e8.min_artifacts_changed", min(len(v["artifacts"]) for v in diffs.values()), "scenarios/E8/diffs.json")
    for n in names:
        f.add(f"e8.{n}.release_id", docs[n]["release_id"], f"scenarios/E8/releases/{n}.json")
        rows = rd(run / f"scenarios/E8/rows/{n}.jsonl")
        f.add(f"e8.{n}.tool_calls_per_wf", round(sum(r["tool_calls"] for r in rows) / len(rows), 3), f"scenarios/E8/rows/{n}.jsonl")
        f.add(f"e8.{n}.input_tokens_per_wf", round(sum(r["input_tokens"] for r in rows) / len(rows)), f"scenarios/E8/rows/{n}.jsonl")
        f.add(f"e8.{n}.cost_per_wf", r2(sum(total(r) for r in rows) / len(rows)), f"scenarios/E8/rows/{n}.jsonl")
        f.add(f"e8.{n}.model_calls_per_wf", r2(sum(r["model_calls"] for r in rows) / len(rows)), f"scenarios/E8/rows/{n}.jsonl")
        if n != "R41":
            f.add(f"e8.{n}.artifact", ", ".join(diffs[n]["artifacts"]), "scenarios/E8/diffs.json")
    base = f.d["e8.R41.tool_calls_per_wf"]["value"]
    f.add("e8.R42-a.tool_calls_delta_pct", r1(100 * (f.d["e8.R42-a.tool_calls_per_wf"]["value"] / base - 1)), "scenarios/E8/rows/*.jsonl")
    f.add("e8.behaviour_changed", sum(1 for n in S["E8"]["candidates"] if any(
        f.d[f"e8.{n}.{m}"]["value"] != f.d[f"e8.R41.{m}"]["value"] for m in ("tool_calls_per_wf", "input_tokens_per_wf", "cost_per_wf", "model_calls_per_wf"))),
        "scenarios/E8/rows/*.jsonl", "candidates whose replayed workload differs from R41 on any of four behaviour metrics")
    f.add("e8.replay_n", S["E8"]["replay_n"], "experiments/scenarios.toml")
    # every telemetry row of the run carries a release id
    allrows = [p for p in run.rglob("rows.jsonl")] + list((run / "scenarios/E8/rows").glob("*.jsonl")) + list((run / "scenarios/E9/rows").glob("*.jsonl"))
    tot = with_id = 0
    for p in allrows:
        for r in rd(p):
            tot += 1
            with_id += bool(r.get("release_id"))
    f.add("e8.rows_total", tot, "**/rows*.jsonl", "every telemetry row the run wrote")
    f.add("e8.rows_with_release_id", with_id, "**/rows*.jsonl")

    # ---- E9 ------------------------------------------------------------------------------------------------------------
    evs = {n: rj(run / f"scenarios/E9/evals/{n}.json") for n in ["R41"] + S["E9"]["candidates"]}
    f.add("e9.cases", evs["R41"]["n"], "scenarios/E9/evals/R41.json")
    blocked = sorted(n for n in S["E9"]["candidates"] if not evs[n]["gate"]["passed"])
    passed = sorted(n for n in S["E9"]["candidates"] if evs[n]["gate"]["passed"])
    f.add("e9.blocked", blocked, "scenarios/E9/evals/*.json")
    f.add("e9.passed", passed, "scenarios/E9/evals/*.json")
    f.add("e9.blocked_n", len(blocked), "scenarios/E9/evals/*.json")
    f.add("e9.blocked_weight_granted", sum(evs[n]["canary_weight_granted"] for n in blocked), "scenarios/E9/evals/*.json + registry.json",
          "canary traffic share the registry granted to blocked candidates")
    for n in ["R41"] + S["E9"]["candidates"]:
        e = evs[n]
        k = f"e9.{n}"
        f.add(f"{k}.task_success", e["task_success"], f"scenarios/E9/evals/{n}.json")
        f.add(f"{k}.tool_calls_per_wf", e["tool_calls_per_wf"], f"scenarios/E9/evals/{n}.json")
        for inv, v in e["invariants"].items():
            f.add(f"{k}.inv.{inv}", v, f"scenarios/E9/evals/{n}.json")
        if n != "R41":
            f.add(f"{k}.reasons", "; ".join(e["gate"]["reasons"]) or "none", f"scenarios/E9/evals/{n}.json")
            f.add(f"{k}.cost_delta_pct", e["gate"]["cost_delta_pct"], f"scenarios/E9/evals/{n}.json")
    f.add("e9.R42-a.tool_calls_delta_pct", r1(100 * (evs["R42-a"]["tool_calls_per_wf"] / evs["R41"]["tool_calls_per_wf"] - 1)), "scenarios/E9/evals/*.json")

    # ---- E10 -----------------------------------------------------------------------------------------------------------
    for cand, cmp in S["E10"]["analyses"]:
        d = run / "scenarios/E10" / f"{cand}__{cmp}"
        c = rj(d / "canary.json")
        rows = rd(d / "rows.jsonl")
        k = f"e10.{cand}.{cmp}"
        src = f"scenarios/E10/{cand}__{cmp}"
        f.add(f"{k}.decision", c["decision"], f"{src}/canary.json")
        f.add(f"{k}.windows", len(c["windows"]), f"{src}/canary.json")
        f.add(f"{k}.decided_at_s", r1(c["decided_at_ms"] / 1000) if c["decided_at_ms"] is not None else None, f"{src}/canary.json")
        last = c["windows"][-1] if c["windows"] else None
        if last:
            f.add(f"{k}.final_stage_pct", last["stage_pct"], f"{src}/canary.json")
            f.add(f"{k}.breaches", ", ".join(last["breaches"]) or "none", f"{src}/canary.json")
            for dk, dv in last["deltas"].items():
                f.add(f"{k}.last.{dk}", round(dv, 1) if isinstance(dv, float) else dv, f"{src}/canary.json", "the last analysis window")
            for dk, dv in last["raw_deltas"].items():
                f.add(f"{k}.last.raw.{dk}", round(dv, 1), f"{src}/canary.json", "raw window averages, no mix adjustment")
            for dk, dv in last["mix_adjusted_deltas"].items():
                f.add(f"{k}.last.adj.{dk}", round(dv, 1), f"{src}/canary.json", "per workflow type, weighted by the baseline's mix")
        cand_rows = [r for r in rows if r["release_id"] == c["candidate_id"]]
        f.add(f"{k}.candidate_requests", len(cand_rows), f"{src}/rows.jsonl")
        after = [r for r in cand_rows if c["decided_at_ms"] is not None and r["arrival_ms"] > c["decided_at_ms"]]
        f.add(f"{k}.candidate_after_decision", len(after), f"{src}/rows.jsonl", "requests that arrived after the decision and were served by the candidate")
        f.add(f"{k}.error_pct_delta_max", round(max((w["deltas"]["error_pp"] for w in c["windows"]), default=0), 1), f"{src}/canary.json")
        f.add(f"{k}.effects_before_decision", c["effects"]["by_candidate_before_decision"], f"{src}/canary.json",
              "replies sent to customers by candidate workflows before the decision")
        f.add(f"{k}.effects_reverted", c["effects"]["reverted_by_rollback"], f"{src}/canary.json")
        if c["decision"] == "PROMOTE":
            f.add(f"{k}.served_after_promotion", len(after), f"{src}/rows.jsonl")
    f.add("e10.R42-a.offline_cost_delta_pct", evs["R42-a"]["gate"]["cost_delta_pct"], "scenarios/E9/evals/R42-a.json")

    # ---- amplification and latency decomposition ------------------------------------------------------------------------------
    rows = rd(run / "scenarios/E8/rows/R41.jsonl")
    n = len(rows)
    ops = sum(r["model_calls"] + r["retrieval_calls"] + r["tool_calls"] for r in rows)
    f.add("amp.requests", n, "scenarios/E8/rows/R41.jsonl", "Cyber Monday sample under R41, no load")
    f.add("amp.steps", r1(sum(r["steps"] for r in rows) / n), "scenarios/E8/rows/R41.jsonl", "workflow steps per external request")
    f.add("amp.model_calls", r1(sum(r["model_calls"] for r in rows) / n), "scenarios/E8/rows/R41.jsonl")
    f.add("amp.retrieval_calls", r1(sum(r["retrieval_calls"] for r in rows) / n), "scenarios/E8/rows/R41.jsonl", "source queries per request")
    f.add("amp.tool_calls", r1(sum(r["tool_calls"] for r in rows) / n), "scenarios/E8/rows/R41.jsonl")
    f.add("amp.input_tokens", round(sum(r["input_tokens"] for r in rows) / n), "scenarios/E8/rows/R41.jsonl")
    f.add("amp.output_tokens", round(sum(r["output_tokens"] for r in rows) / n), "scenarios/E8/rows/R41.jsonl")
    f.add("amp.ops", r1(ops / n), "scenarios/E8/rows/R41.jsonl", "model + retrieval + tool operations per external request")
    f.add("amp.cost_cu", r2(sum(total(r) for r in rows) / n), "scenarios/E8/rows/R41.jsonl")
    shares = {k: sum(r["cost_cu"][k] for r in rows) for k in ("model", "retrieval", "tool", "platform")}
    tot = sum(shares.values())
    for k, v in shares.items():
        f.add(f"amp.cost_share.{k}_pct", r1(100 * v / tot), "scenarios/E8/rows/R41.jsonl", f"{k} share of workflow cost")
    e4n = rd(run / "scenarios/E4/none/rows.jsonl")
    coords = [r for r in e4n if r["workflow"] == "dispute-investigation" and r["request_id"] != "E4-COORD"]
    single = [r for r in e4n if r["workflow"] == "refund-dispute" and r["request_id"] != "E4-RUNAWAY"]
    f.add("amp.coord.model_calls", r1(sum(r["model_calls"] for r in coords) / len(coords)), "scenarios/E4/none/rows.jsonl",
          "a dispute investigation: coordinator + three sub-agents")
    f.add("amp.coord.input_tokens", round(sum(r["input_tokens"] for r in coords) / len(coords)), "scenarios/E4/none/rows.jsonl")
    f.add("amp.coord.cost_cu", r1(sum(total(r) for r in coords) / len(coords)), "scenarios/E4/none/rows.jsonl")
    f.add("amp.single.model_calls", r1(sum(r["model_calls"] for r in single) / len(single)), "scenarios/E4/none/rows.jsonl", "a single-agent refund dispute")
    f.add("amp.single.cost_cu", r1(sum(total(r) for r in single) / len(single)), "scenarios/E4/none/rows.jsonl")
    sumc = sum(sum(r["time_ms"].values()) for r in coords) / len(coords)
    wall = sum(r["latency_ms"] for r in coords) / len(coords)
    f.add("amp.coord.component_sum_s", r1(sumc / 1000), "scenarios/E4/none/rows.jsonl", "sum of every component's time, children included")
    f.add("amp.coord.wall_s", r1(wall / 1000), "scenarios/E4/none/rows.jsonl", "end-to-end: children run concurrently")
    rows, _, _ = load_arm(run, "scenarios/E1/controlled")
    ok = [r for r in rows if r["result"] == "SUCCESS"]
    for comp in ("model", "retrieval", "tool", "overhead"):
        xs = sorted(r["time_ms"][comp] for r in ok)
        f.add(f"lat.{comp}.p50_ms", pct(xs, 50), "scenarios/E1/controlled/rows.jsonl", f"per successful attempt: time in {comp}")
        f.add(f"lat.{comp}.p95_ms", pct(xs, 95), "scenarios/E1/controlled/rows.jsonl")
    xs = sorted(r["queue_delay_ms"] for r in ok)
    f.add("lat.queue.p50_ms", pct(xs, 50), "scenarios/E1/controlled/rows.jsonl")
    f.add("lat.queue.p95_ms", pct(xs, 95), "scenarios/E1/controlled/rows.jsonl")
    xs = sorted(r["latency_ms"] for r in ok)
    for p in (50, 95, 99):
        f.add(f"lat.e2e.p{p}_ms", pct(xs, p), "scenarios/E1/controlled/rows.jsonl")
    mean_lat = sum(xs) / len(xs)
    f.add("lat.queue_share_pct", r1(100 * sum(r["queue_delay_ms"] for r in ok) / sum(xs)), "scenarios/E1/controlled/rows.jsonl",
          "share of end-to-end time spent queued, successful attempts under surge")
    f.add("lat.e2e.mean_ms", round(mean_lat), "scenarios/E1/controlled/rows.jsonl")

    facts = dict(sorted(f.d.items()))
    (run / "facts.json").write_text(dump(facts))
    (run / "summary.md").write_text(summary_md(facts, run.name))
    return facts


def summary_md(facts: dict, run_id: str) -> str:
    v = lambda k: facts[k]["value"]  # noqa: E731
    lines = [f"# O1 + O2 · run {run_id}", "", "Simulation units: simulated milliseconds and cost units (cu). Not a benchmark of any real system.", "",
             "| Scenario | Naive / baseline | Controlled |", "|---|---|---|",
             f"| E1 admission | goodput {v('e1.naive.goodput_pct')} %, work in system max {v('e1.naive.max_work_in_system')}, retry x{v('e1.naive.retry_amplification')} | goodput {v('e1.controlled.goodput_pct')} %, work in system max {v('e1.controlled.max_work_in_system')}, refused {v('e1.controlled.refused_pct')} % |",
             f"| E2 fairness | support goodput {v('e2.naive.support.goodput_pct')} % | support goodput {v('e2.controlled.support.goodput_pct')} %, finance makespan {v('e2.controlled.finance.makespan_s')} s |",
             f"| E3 concurrency | max running {v('e3.naive.max_active')}, goodput {v('e3.naive.goodput_pct')} % | max running {v('e3.controlled.max_active')}, goodput {v('e3.controlled.goodput_pct')} % |",
             f"| E4 envelope | runaway {v('e4.none.runaway.cost_cu')} cu ({v('e4.none.runaway.result')}) | runaway {v('e4.envelope.runaway.cost_cu')} cu ({v('e4.envelope.runaway.result')}); legit cut {v('e4.envelope.legit_cut')} |",
             f"| E5 routing | all-large {v('e5.all-large.cost_per_success')} cu/success | routed {v('e5.routed.cost_per_success')} cu/success, violations {v('e5.routed.data_violations')} |",
             f"| E6 context | {v('e6.naive.context_tokens_mean')} tokens/query | {v('e6.bounded.context_tokens_mean')} tokens/query, missing required {v('e6.bounded.missing_required')} |",
             f"| E7 tool gateway | max in flight {v('e7.naive.max_inflight')}, 503 {v('e7.naive.http_503')} | max in flight {v('e7.controlled.max_inflight')}, 503 {v('e7.controlled.http_503')} |",
             f"| E8 release | image digests {v('e8.distinct_image_digests')} | release ids {v('e8.distinct_release_ids')} |",
             f"| E9 gate | blocked {', '.join(v('e9.blocked'))} | passed {', '.join(v('e9.passed'))} |",
             f"| E10 canary | R42-a: {v('e10.R42-a.mix-adjusted.decision')} | R42-e: {v('e10.R42-e.mix-adjusted.decision')} (raw comparison: {v('e10.R42-e.raw.decision')}) |",
             "", f"{len(facts)} facts, every one recomputed from the raw files of this run."]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["record", "aggregate"])
    ap.add_argument("--run-id", required=True)
    o = ap.parse_args()
    if o.cmd == "record":
        p = record(o.run_id)
        print(f"recorded {p.relative_to(RUNS.parent)}")
    else:
        aggregate(RUNS / o.run_id)
        print("aggregated")


if __name__ == "__main__":
    main()
