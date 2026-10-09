"""The ten scenarios (E1-E10) and the negative control (NC). Each returns its raw outputs per arm; agentops/run.py
writes them to the run directory and aggregates facts from the written files.

Every arm of a scenario runs on the same seed, arrivals, cases and clients; only the policy named in
experiments/scenarios.toml (`variable`) differs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import release as rel
from .budget import DIMENSIONS, Envelope, Ledger
from .common import cfg, draw, experiments, fixture, pct
from .platform import Platform, Policy
from .retrieval import Cache, Retriever, assemble
from .router import ModelService
from .runtime import Ctx, new_row, run_workflow
from .sim import Env
from .tools import ToolLayer
from .workload import arrivals, batch_submitter, finance_case, support_case, support_client

S = experiments("scenarios")
SEED = S["seed"]
PLAT = cfg("platform")


@dataclass
class Arm:
    rows: list = field(default_factory=list)
    requests: list = field(default_factory=list)
    timeline: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)


def policy(d: dict) -> Policy:
    slots = d.get("slots")
    return Policy(admission=d.get("admission", "open"), slots=None if slots == "unbounded" else slots,
                  scheduling=d.get("scheduling", "fifo"), deadlines=d.get("deadlines", False))


def finalize(arm: Arm, platform: Platform, ctx: Ctx, horizon: int) -> Arm:
    for r in platform.rows:
        if r["result"] is None:
            r["result"] = "UNFINISHED"
        r.setdefault("client_gave_up_ms", None)
        g = r["client_gave_up_ms"]
        r["client_waiting"] = None if r["tenant"] != "support" else (g is None or (r["end_ms"] is not None and r["end_ms"] <= g))
        r["cost_cu"] = {k: round(v, 6) for k, v in r["cost_cu"].items()}
    for q in arm.requests:
        a = q.pop("attempt_obj", None)
        if a is not None:
            q["served"] = a.result == "SUCCESS"
            q["outcome"] = a.result or "UNFINISHED"
            q["end_ms"] = a.row["end_ms"]
    arm.rows = platform.rows
    arm.timeline = platform.timeline
    arm.stats = {"max": platform.max, "max_by_tenant": platform.max_t, "tools": ctx.tools.stats(),
                 "model_calls": ctx.models.calls, "model_throttled": ctx.models.throttled, "horizon_ms": horizon,
                 "effects": len(ctx.effects)}
    return arm


def build(scn: str, arm_name: str, pol: Policy, tenants: list[str], *, mode: str = "routed", outages: dict | None = None,
          relaxed_tools: bool = True, gateway: bool = False, constrained: tuple = (), release=None,
          budget_mode: str = "none", envelopes: dict | None = None, escalation_cost: bool = False):
    env = Env()
    release = release or rel.load("R41")
    models = ModelService(env, mode=mode, overrides=release.routing_overrides, outages=outages)
    tools = ToolLayer(env, relaxed=relaxed_tools, gateway=gateway, constrained=constrained)
    ctx = Ctx(env=env, scenario=scn, arm=arm_name, models=models, tools=tools, retriever=Retriever(),
              budget_mode=budget_mode, envelopes=envelopes or {}, include_escalation_cost=escalation_cost, tool_backoff=gateway)
    platform = Platform(env, ctx, pol, tenants)
    models.contention = platform.contention
    ctx.retriever.contention = platform.contention
    return env, ctx, platform


def run_support(env, platform, scn: str, times: list[int], release_for, mix: str = "black-friday", shipments=None) -> list:
    reqs: list = []
    for i, t in enumerate(times):
        case = support_case(SEED, scn, i, mix, shipments)
        env.process(support_client(env, platform, case, release_for, t, reqs))
    return reqs


# ---- E1 · admission -----------------------------------------------------------------------------------------------------

def e1(arm_name: str, arm_cfg: dict | None = None, scn: str = "E1") -> Arm:
    c = S["E1"]
    d = arm_cfg or c["arms"][arm_name]
    env, ctx, platform = build(scn, arm_name, policy(d), ["support"])
    r41 = rel.load("R41")
    times = arrivals(SEED, "E1", [tuple(p) for p in c["phases"]])
    arm = Arm()
    arm.requests = run_support(env, platform, "E1", times, lambda case: r41)
    platform.sample(1000, c["horizon_ms"])
    env.run(until=c["horizon_ms"])
    return finalize(arm, platform, ctx, c["horizon_ms"])


# ---- E2 · tenant fairness -----------------------------------------------------------------------------------------------

def e2(arm_name: str) -> Arm:
    c = S["E2"]
    env, ctx, platform = build("E2", arm_name, policy(c["arms"][arm_name]), ["support", "finance"])
    r41 = rel.load("R41")
    arm = Arm()
    arm.requests = run_support(env, platform, "E2", arrivals(SEED, "E2", [tuple(p) for p in c["support_phases"]]), lambda case: r41)
    a, b = c["finance_window_ms"]
    n = c["finance_items"]
    ftimes = [a + (b - a) * i // n for i in range(n)]
    fin: list = []
    env.process(batch_submitter(env, platform, [finance_case("E2", i) for i in range(n)], ftimes, lambda case: r41, fin))
    platform.sample(1000, c["horizon_ms"])
    env.run(until=c["horizon_ms"])
    arm.requests += fin
    return finalize(arm, platform, ctx, c["horizon_ms"])


# ---- E3 · bounded concurrency, backpressure, deadlines --------------------------------------------------------------------

def e3(arm_name: str) -> Arm:
    c = S["E3"]
    env, ctx, platform = build("E3", arm_name, policy(c["arms"][arm_name]), ["support"])
    r41 = rel.load("R41")
    arm = Arm()
    arm.requests = run_support(env, platform, "E3", arrivals(SEED, "E3", [tuple(p) for p in c["phases"]]), lambda case: r41)
    platform.sample(1000, c["horizon_ms"])
    env.run(until=c["horizon_ms"])
    return finalize(arm, platform, ctx, c["horizon_ms"])


# ---- E4 · workflow resource envelopes -------------------------------------------------------------------------------------

def _e4_sample(seed: int, tag: str) -> list[dict]:
    c = S["E4"]
    cases = [support_case(seed, f"E4{tag}", i) for i in range(c["normal_n"])]
    cases += [{"request_id": f"E4{tag}-D{i:03d}", "tenant": "support", "workflow": "dispute-investigation", "shipments": 1, "amount": 0}
              for i in range(c["coordinators_n"])]
    cases += [finance_case(f"E4{tag}", i) for i in range(c["finance_n"])]
    return cases


def _e4_run(cases: list[dict], arm_name: str, budget_mode: str, envelopes: dict, stuck: set) -> tuple[list, Ctx]:
    c = S["E4"]
    env, ctx, platform = build("E4", arm_name, Policy(admission="open", slots=None), ["support", "finance"], budget_mode=budget_mode,
                               envelopes=envelopes)
    ctx.payments_stuck |= stuck
    r41 = rel.load("R41")
    gap = int(1000 / c["rate"])
    for i, case in enumerate(cases):
        env.at(i * gap, lambda case=case: platform.submit(case, 1, None, r41))
    env.run()
    for r in platform.rows + ctx.child_rows:
        r["client_waiting"] = None
        r.setdefault("client_gave_up_ms", None)
        r["cost_cu"] = {k: round(v, 6) for k, v in r["cost_cu"].items()}
    return platform.rows, ctx


def calibrate() -> dict:
    """Envelope per workflow type: the maximum of each dimension over the development sample, times the margin."""
    c = S["E4"]
    rows, ctx = _e4_run(_e4_sample(c["dev_seed"], "dev"), "calibrate", "none", {}, set())
    env_by: dict = {}
    for r in rows + ctx.child_rows:
        wall = r["latency_ms"] if r["latency_ms"] is not None else 0
        u = {"steps": r["steps"], "model_calls": r["model_calls"], "tool_calls": r["tool_calls"], "input_tokens": r["input_tokens"],
             "output_tokens": r["output_tokens"], "cost_cu": sum(r["cost_cu"].values()), "wall_ms": wall,
             "fanout": r["children"]}
        m = env_by.setdefault(r["workflow"], {d: 0 for d in DIMENSIONS})
        for d in DIMENSIONS:
            m[d] = max(m[d], u[d])
    out = {}
    for wf, m in env_by.items():
        lim = {}
        for d in DIMENSIONS:
            v = m[d] * c["calibration_margin"]
            lim[d] = round(math.ceil(v * 100) / 100, 2) if d == "cost_cu" else (math.ceil(v) if m[d] else None)
        out[wf] = lim
    out["child"]["wall_ms"] = None        # a child's own clock is not measured separately; its parent's is
    return out


def e4() -> dict:
    c = S["E4"]
    limits = calibrate()
    envs = {wf: Envelope(**l) for wf, l in limits.items()}
    blind = _e4_sample(SEED, "")
    runaway = {"request_id": "E4-RUNAWAY", "tenant": "support", "workflow": "refund-dispute", "shipments": 1, "amount": 40}
    coord = {"request_id": "E4-COORD", "tenant": "support", "workflow": "dispute-investigation", "shipments": 1, "amount": 0, "stuck": True}
    out = {"limits": limits}
    for arm_name in c["arms"]:
        rows, _ = _e4_run(blind + [runaway, coord], arm_name, arm_name, envs, {"E4-RUNAWAY"})
        out[arm_name] = rows
    return out


# ---- E5 · routing inside an eligibility contract -----------------------------------------------------------------------------

def e5(arm_name: str) -> Arm:
    c = S["E5"]
    o = c["outage"]
    env, ctx, platform = build("E5", arm_name, Policy(admission="open", slots=None), ["support", "finance"], mode=arm_name,
                               outages={o["profile"]: [tuple(o["window_ms"])]}, escalation_cost=True)
    r41 = rel.load("R41")
    gap = int(1000 / c["rate"])
    for i in range(c["n"]):
        case = finance_case("E5", i) if draw(SEED, "E5", i, "tenant") < c["finance_share"] else support_case(SEED, "E5", i)
        env.at(i * gap, lambda case=case: platform.submit(case, 1, None, r41))
    env.run()
    arm = Arm()
    return finalize(arm, platform, ctx, env.now)


# ---- E6 · context budgets and cache scope ------------------------------------------------------------------------------------

def e6() -> dict:
    kb = fixture("knowledge")
    retrieval = rel.load("R41").retrieval
    out = {"retrieval": [], "cache": []}
    for q in kb["queries"]:
        for mode in ("naive", "bounded"):
            out["retrieval"].append(assemble(q, kb, mode, retrieval))
    for scoped in (False, True):
        cache = Cache(scoped)
        for i, req in enumerate(kb["cache_sequence"]):
            res = cache.lookup(req)
            out["cache"].append({"i": i, "cache": "scoped" if scoped else "query-text", **{k: req[k] for k in ("query", "principal", "personal", "kb_version", "policy_version")}, **res})
    return out


# ---- E7 · the tool gateway -----------------------------------------------------------------------------------------------------

def e7(arm_name: str) -> Arm:
    c = S["E7"]
    gw = c["arms"][arm_name]["gateway"]
    sched = c["arms"][arm_name]["scheduling"]
    env, ctx, platform = build("E7", arm_name, Policy(admission="open", slots=c["slots"], scheduling=sched), ["support", "finance"],
                               relaxed_tools=False, gateway=gw, constrained=tuple(c["constrained"]))
    r41 = rel.load("R41")
    arm = Arm()
    arm.requests = run_support(env, platform, "E7", arrivals(SEED, "E7", [tuple(p) for p in c["support_phases"]]), lambda case: r41)
    a, b = c["finance_window_ms"]
    n = c["finance_items"]
    fin: list = []
    env.process(batch_submitter(env, platform, [finance_case("E7", i) for i in range(n)], [a + (b - a) * i // n for i in range(n)],
                                lambda case: r41, fin))
    platform.sample(1000, c["horizon_ms"])
    env.run(until=c["horizon_ms"])
    arm.requests += fin
    return finalize(arm, platform, ctx, c["horizon_ms"])


# ---- offline replay of one release (E8 behaviour, E9 evals) ------------------------------------------------------------------

def replay(release, cases: list[dict], scn: str) -> list[dict]:
    """Each case alone through the runtime (no load, tools sandboxed and read-only), under the given release."""
    rows = []
    for case in cases:
        env, ctx, platform = build(scn, release.name, Policy(admission="open", slots=None), ["support", "finance"], release=release,
                                   budget_mode="envelope", envelopes=E4_ENVELOPES())
        row = new_row(case, 1, release, release.name)
        row["arrival_ms"] = 0
        holder: dict = {}

        def body():
            return (yield from run_workflow(ctx, case, row, release, None))
        holder["p"] = env.process(body())
        env.run()
        row["result"] = holder["p"].value
        row["latency_ms"] = row["end_ms"] = env.now
        row["start_ms"], row["queue_delay_ms"], row["client_gave_up_ms"] = 0, 0, None
        row["cost_cu"] = {k: round(v, 6) for k, v in row["cost_cu"].items()}
        rows.append(row)
    return rows


_ENV_CACHE: dict = {}


def E4_ENVELOPES() -> dict:
    if "e" not in _ENV_CACHE:
        _ENV_CACHE["e"] = {wf: Envelope(**l) for wf, l in calibrate().items()}
    return _ENV_CACHE["e"]


def e8() -> dict:
    c = S["E8"]
    base = rel.load("R41")
    cases = [support_case(SEED, "E8", i, "cyber-monday", cfg("workflows")["mix"]["cyber-monday-shipments"]["shipments"])
             for i in range(c["replay_n"])]
    out = {"releases": {base.name: base.document()}, "rows": {base.name: replay(base, cases, "E8")}, "diffs": {}}
    for name in c["candidates"]:
        r = rel.load(name)
        out["releases"][name] = r.document()
        out["diffs"][name] = {"paths": rel.diff(base, r), "artifacts": rel.artifacts_changed(base, r)}
        out["rows"][name] = replay(r, cases, "E8")
    return out


# ---- E9 · offline evals and invariant gates -----------------------------------------------------------------------------------

def evaluate(release, suite: list[dict]) -> dict:
    """The offline suite under one release: per-case rows, quality metrics and the invariant checks."""
    cases = [{"request_id": f"E9-{c['id']}", "tenant": c["tenant"], "workflow": c["workflow"], "shipments": c["shipments"],
              "amount": c["amount"]} for c in suite]
    rows = replay(release, cases, "E9")
    n = len(rows)
    succ = sum(r["result"] == "SUCCESS" for r in rows)
    tool_ok = 0
    approval_bypass = 0
    for c, r in zip(suite, rows):
        called = set(_tools_called(c, r))
        tool_ok += set(c["required_tools"]) <= called
        if c["amount"] > release.delegated_limit and r["approvals_requested"] == 0:
            approval_bypass += 1
    machine = [sum(v for k, v in r["cost_cu"].items() if k != "escalation") for r in rows]
    lat = sorted(r["latency_ms"] for r in rows)
    envelope_ok = release.envelope_enforced and all(E4_ENVELOPES().get(c["workflow"]) is not None for c in suite)
    return {"release": release.name, "release_id": release.release_id, "n": n, "task_success": round(succ / n, 4),
            "tool_selection": round(tool_ok / n, 4), "cost_per_success": round(sum(machine) / max(succ, 1), 4),
            "p95_latency_ms": pct(lat, 95), "tool_calls_per_wf": round(sum(r["tool_calls"] for r in rows) / n, 4),
            "invariants": {"data_policy": sum(r["data_violations"] for r in rows),
                           "capability": sum(r["capability_violations"] for r in rows),
                           "approval_bypass": approval_bypass, "envelope_unenforceable": int(not envelope_ok)},
            "rows": rows}


def _tools_called(case: dict, row: dict) -> list[str]:
    # the plan's tools are deterministic per workflow type; a row records counts, so the called set is derived from the
    # plan the runtime executed (agent.plan), replayed without side effects
    from . import agent
    called, gen, send = [], agent.plan({**case, "request_id": row["request_id"]}, rel.load(row["release"])), None
    while True:
        try:
            op = gen.send(send)
        except StopIteration:
            break
        send = None
        if isinstance(op, agent.Tool):
            called.append(op.name)
            send = "SETTLED"
        elif isinstance(op, agent.Spawn):
            send = ["SUCCESS"] * len(op.children)
    return called


def gate(ev: dict, base: dict) -> tuple[bool, list[str]]:
    g = next(h for h in experiments("preregistration")["hypotheses"] if h["id"] == "H9")["gate"]
    reasons = []
    for k, v in ev["invariants"].items():
        if v > g["invariant_violations_max"]:
            reasons.append(f"invariant {k}: {v}")
    if ev["task_success"] < g["task_success_min"]:
        reasons.append(f"task_success {ev['task_success']} < {g['task_success_min']}")
    if ev["tool_selection"] < g["tool_selection_min"]:
        reasons.append(f"tool_selection {ev['tool_selection']} < {g['tool_selection_min']}")
    dc = 100 * (ev["cost_per_success"] / base["cost_per_success"] - 1)
    if dc > g["cost_regression_max_pct"]:
        reasons.append(f"cost regression {dc:.1f}% > {g['cost_regression_max_pct']}%")
    dl = 100 * (ev["p95_latency_ms"] / base["p95_latency_ms"] - 1)
    if dl > g["p95_regression_max_pct"]:
        reasons.append(f"p95 regression {dl:.1f}% > {g['p95_regression_max_pct']}%")
    return not reasons, reasons


def e9() -> dict:
    suite = fixture("eval_suite")
    base_rel = rel.load("R41")
    reg = rel.Registry(base_rel)
    base = evaluate(base_rel, suite)
    out = {"baseline": base, "candidates": {}, "registry": None}
    for name in S["E9"]["candidates"]:
        r = rel.load(name)
        reg.submit(r)
        ev = evaluate(r, suite)
        ok, reasons = gate(ev, base)
        reg.gate(r, ok, reasons)
        ev["gate"] = {"passed": ok, "reasons": reasons,
                      "cost_delta_pct": round(100 * (ev["cost_per_success"] / base["cost_per_success"] - 1), 2),
                      "p95_delta_pct": round(100 * (ev["p95_latency_ms"] / base["p95_latency_ms"] - 1), 2)}
        ev["canary_weight_granted"] = reg.set_weight(r, 10, "canary stage 1") and 10 or 0
        if ev["canary_weight_granted"]:
            reg.set_weight(r, 0, "gate check only: E10 runs the canary")
        out["candidates"][name] = ev
    out["registry"] = reg.log
    return out


# ---- E10 · the behavioural canary --------------------------------------------------------------------------------------------

def _window_metrics(rows: list[dict], release) -> dict:
    n = len(rows)
    succ = [r for r in rows if r["result"] == "SUCCESS"]
    errors = sum(r["result"] in ("FAILED_TOOL", "DEFERRED", "CANCELLED_DEADLINE", "HARNESS_GUARD", "UNFINISHED", "NO_ANSWER") for r in rows)
    machine = sum(sum(v for k, v in r["cost_cu"].items() if k != "escalation") for r in rows)
    viol = sum(r["data_violations"] + r["capability_violations"] for r in rows) + \
        sum(1 for r in rows if r["workflow"] == "refund-dispute" and r.get("_amount", 0) > release.delegated_limit and r["approvals_requested"] == 0)
    return {"n": n, "success_pct": 100 * len(succ) / n, "error_pct": 100 * errors / n, "cost_per_success": machine / max(len(succ), 1),
            "p95_ms": pct(sorted(r["latency_ms"] for r in rows), 95), "tool_calls_per_wf": sum(r["tool_calls"] for r in rows) / n,
            "violations": viol}


def _machine(rows: list[dict]) -> float:
    return sum(sum(v for k, v in r["cost_cu"].items() if k != "escalation") for r in rows)


def _mix_adjusted(cand_rows: list[dict], base_rows: list[dict]) -> dict:
    """Compare like with like: per workflow type, weighted by the baseline's mix in the same period. A 60-workflow
    window that happens to hold more refund disputes than the baseline is then not mistaken for a regression."""
    by = lambda rows: {w: [r for r in rows if r["workflow"] == w] for w in sorted({r["workflow"] for r in rows})}  # noqa: E731
    bc, cc = by(base_rows), by(cand_rows)
    types = [w for w in bc if w in cc]
    n = sum(len(bc[w]) for w in types)
    share = {w: len(bc[w]) / n for w in types}
    cps = lambda rows: _machine(rows) / max(sum(r["result"] == "SUCCESS" for r in rows), 1)  # noqa: E731
    tpw = lambda rows: sum(r["tool_calls"] for r in rows) / len(rows)  # noqa: E731
    out = {}
    for name, f in (("cost_per_success", cps), ("tool_calls_per_wf", tpw)):
        out[name] = (sum(share[w] * f(cc[w]) for w in types), sum(share[w] * f(bc[w]) for w in types))
    out["types"] = types
    return out


def canary(cand_name: str, comparison: str = "mix-adjusted") -> dict:
    c = S["E10"]
    g = next(h for h in experiments("preregistration")["hypotheses"] if h["id"] == "H10")["guardrails"]
    base_rel, cand = rel.load("R41"), rel.load(cand_name)
    reg = rel.Registry(base_rel)
    reg.submit(cand)
    ev_base, ev = evaluate(base_rel, fixture("eval_suite")), evaluate(cand, fixture("eval_suite"))
    ok, reasons = gate(ev, ev_base)
    reg.gate(cand, ok, reasons)
    stage = [0]
    reg.set_weight(cand, c["stages"][0], "canary stage 1")
    env, ctx, platform = build("E10", f"{cand_name}:{comparison}", Policy(admission="open", slots=32, scheduling="fifo"), ["support"])
    state = {"since": 0, "passed": 0, "decision": None, "decided_at_ms": None, "windows": [], "stage_start_ms": 0}

    def release_for(case: dict):
        w = reg.weights.get(cand.release_id, 0)
        if reg.production == cand.release_id:
            return cand
        return cand if draw(SEED, "E10", case["request_id"], "split") * 100 < w else base_rel

    done_rows: list = []

    def on_finish() -> None:
        if state["decision"] in ("ROLLBACK", "PROMOTE"):
            return
        t0 = state["stage_start_ms"]
        cand_rows = [r for r in platform.rows if r["result"] and r["release_id"] == cand.release_id and r["end_ms"] is not None and r["start_ms"] is not None
                     and r["arrival_ms"] >= t0]
        if len(cand_rows) - state["since"] < c["window"]:
            return
        win = cand_rows[state["since"]: state["since"] + c["window"]]
        lo, hi = win[0]["arrival_ms"], env.now        # the baseline over the same period, as far as it has completed
        base_rows = [r for r in platform.rows if r["result"] and r["release_id"] == base_rel.release_id and r["end_ms"] is not None
                     and r["start_ms"] is not None and lo <= r["arrival_ms"] and r["end_ms"] <= hi]
        if len(base_rows) < c["window"]:          # not enough baseline traffic in the same period to compare against yet
            return
        mc, mb = _window_metrics(win, cand), _window_metrics(base_rows, base_rel)
        raw = {"cost_per_success_pct": 100 * (mc["cost_per_success"] / mb["cost_per_success"] - 1),
               "tool_calls_pct": 100 * (mc["tool_calls_per_wf"] / mb["tool_calls_per_wf"] - 1) if mb["tool_calls_per_wf"] else 0.0}
        adj = _mix_adjusted(win, base_rows)
        mixed = {"cost_per_success_pct": 100 * (adj["cost_per_success"][0] / adj["cost_per_success"][1] - 1),
                 "tool_calls_pct": 100 * (adj["tool_calls_per_wf"][0] / adj["tool_calls_per_wf"][1] - 1) if adj["tool_calls_per_wf"][1] else 0.0}
        deltas = {**(mixed if comparison == "mix-adjusted" else raw),
                  "p95_pct": 100 * (mc["p95_ms"] / mb["p95_ms"] - 1),
                  "error_pp": mc["error_pct"] - mb["error_pct"], "success_pp": mc["success_pct"] - mb["success_pct"],
                  "violations": mc["violations"]}
        breaches = [k for k, lim in (("cost_per_success_pct", g["cost_per_success_delta_max_pct"]), ("p95_pct", g["p95_delta_max_pct"]),
                                     ("tool_calls_pct", g["tool_calls_delta_max_pct"]), ("error_pp", g["error_rate_delta_max_pp"]))
                    if deltas[k] > lim]
        if deltas["success_pp"] < g["success_delta_min_pp"]:
            breaches.append("success_pp")
        if deltas["violations"] > g["violations_max"]:
            breaches.append("violations")
        state["since"] += c["window"]
        state["windows"].append({"stage_pct": c["stages"][stage[0]], "window": len(state["windows"]) + 1, "at_ms": env.now,
                                 "candidate": {k: round(v, 3) if isinstance(v, float) else v for k, v in mc.items()},
                                 "baseline": {k: round(v, 3) if isinstance(v, float) else v for k, v in mb.items()},
                                 "deltas": {k: round(v, 3) if isinstance(v, float) else v for k, v in deltas.items()},
                                 "raw_deltas": {k: round(v, 3) for k, v in raw.items()}, "mix_adjusted_deltas": {k: round(v, 3) for k, v in mixed.items()},
                                 "breaches": breaches})
        if breaches:
            reg.rollback(cand, "guardrails breached: " + ", ".join(breaches))
            state["decision"], state["decided_at_ms"] = "ROLLBACK", env.now
            return
        state["passed"] += 1
        if state["passed"] >= c["windows_to_advance"]:
            state["passed"], state["since"] = 0, 0
            if stage[0] + 1 < len(c["stages"]) and c["stages"][stage[0] + 1] < 100:
                stage[0] += 1
                reg.set_weight(cand, c["stages"][stage[0]], f"canary stage {stage[0] + 1}")
                state["stage_start_ms"] = env.now
            else:                                 # the last step, 100 %, is the promotion itself
                reg.promote(cand)
                state["decision"], state["decided_at_ms"] = "PROMOTE", env.now

    orig = platform._finish

    def finish_hook(a, result, started):
        orig(a, result, started)
        a.row["_amount"] = a.case.get("amount", 0)
        on_finish()
    platform._finish = finish_hook
    gap = int(1000 / c["rate"])
    shipments = cfg("workflows")["mix"]["cyber-monday-shipments"]["shipments"]
    for i in range(c["n"]):
        case = support_case(SEED, "E10", i, c["mix"], shipments)
        env.at(i * gap, lambda case=case: platform.submit(case, 1, None, release_for(case)))
    env.run()
    for r in platform.rows:
        r.pop("_amount", None)
        r["client_waiting"] = None
        r.setdefault("client_gave_up_ms", None)
        r["cost_cu"] = {k: round(v, 6) for k, v in r["cost_cu"].items()}
    decided = state["decided_at_ms"]
    cand_effects = [e for e in ctx.effects if e["release_id"] == cand.release_id]
    return {"candidate": cand_name, "comparison": comparison, "candidate_id": cand.release_id, "baseline_id": base_rel.release_id, "offline_gate": {"passed": ok, "reasons": reasons},
            "decision": state["decision"] or "UNDECIDED", "decided_at_ms": decided, "windows": state["windows"], "registry": reg.log,
            "rows": platform.rows,
            "effects": {"by_candidate": len(cand_effects),
                        "by_candidate_before_decision": sum(1 for e in cand_effects if decided is None or e["at_ms"] <= decided),
                        "reverted_by_rollback": 0,
                        "note": "a rollback moves the release pointer; replies already sent under the candidate stay sent"}}


def e10() -> dict:
    return {f"{name}:{cmp}": canary(name, cmp) for name, cmp in S["E10"]["analyses"]}


# ---- NC · negative control ----------------------------------------------------------------------------------------------------

def nc() -> Arm:
    return e1("admission-removed", S["NC"]["arm"], scn="E1")
