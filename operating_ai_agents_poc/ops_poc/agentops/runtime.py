"""The agent runtime (P1 layer D): executes a workflow's plan step by step under the platform's controls.

Before every step it checks, in order: cooperative cancellation (orchestration cancelled the attempt at its deadline),
the workflow resource envelope (the ledger), and the simulator's harness guard (not a platform control: it only keeps
an uncontrolled run finite). Each step is then executed through the layer that owns it: retrieval (context), the model
service (routing, quotas, fallback), the tool layer (naive client or gateway), or child workflows (fan-out).

At the decisive answer the declared outcome model decides whether the answer is right (agentops/router.py
outcome_probability; hash-based draw). A wrong answer is caught by a deterministic validator: the workflow is re-run
once on the same route, then escalated to a person. Everything a workflow consumes lands on its telemetry row.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import agent
from .budget import Envelope, Ledger
from .common import cfg, draw
from .retrieval import Retriever
from .router import ModelService, outcome_probability
from .sim import Env, Process, join, sleep
from .tools import ToolLayer

PLAT = cfg("platform")
WF = cfg("workflows")
OUTCOME = cfg("models")["outcome"]


@dataclass
class Ctx:
    """Everything one scenario arm runs on. ``contention`` is the processor-sharing factor of the shared resources."""
    env: Env
    scenario: str
    arm: str
    models: ModelService
    tools: ToolLayer
    retriever: Retriever
    contention: object = lambda: 1.0
    budget_mode: str = "none"             # none | per-agent | envelope
    envelopes: dict = field(default_factory=dict)   # workflow type -> Envelope
    include_escalation_cost: bool = False
    tool_backoff: bool = False            # the runtime retries a TOOL_BUSY step after backoff (with the gateway)
    payments_stuck: set = field(default_factory=set)  # request ids whose payment stays PENDING (E4)
    effects: list = field(default_factory=list)       # committed external effects (replies sent), for E10
    child_rows: list = field(default_factory=list)    # every sub-agent's own row (rolled into its parent's row too)


def new_row(case: dict, attempt: int, release, arm: str) -> dict:
    return {"request_id": case["request_id"], "attempt": attempt, "tenant": case["tenant"], "workflow": case["workflow"],
            "release": release.name, "release_id": release.release_id, "arm": arm, "admission_result": None,
            "arrival_ms": None, "start_ms": None, "end_ms": None, "queue_delay_ms": None, "latency_ms": None,
            "deadline_ms": None, "deadline_met": None, "client_waiting": None, "steps": 0, "model_calls": 0,
            "model_routes": {}, "input_tokens": 0, "output_tokens": 0,
            "cost_cu": {"model": 0.0, "retrieval": 0.0, "tool": 0.0, "platform": 0.0, "escalation": 0.0},
            "retrieval_calls": 0, "retrieved_chunks": 0, "context_tokens": 0, "tool_calls": 0, "tool_attempts": 0,
            "tool_busy": 0, "throttles": 0, "fallbacks": 0, "capability_violations": 0, "data_violations": 0,
            "approvals_requested": 0, "children": 0, "workflow_attempts": 0, "tool_result_tokens": 0,
            "time_ms": {"model": 0, "retrieval": 0, "tool": 0, "overhead": 0, "wait": 0},
            "result": None, "budget_reason": None, "rollback_reason": None}


def envelope_for(ctx: Ctx, workflow: str, release) -> Envelope:
    if ctx.budget_mode == "none" or not release.envelope_enforced:
        return Envelope.none()
    return ctx.envelopes.get(workflow, Envelope.none())


def run_workflow(ctx: Ctx, case: dict, row: dict, release, proc: Process | None, ledger: Ledger | None = None):
    """A generator: run one workflow attempt to a result. Returns the result string; fills ``row``."""
    env = ctx.env
    ledger = ledger or Ledger(envelope_for(ctx, case["workflow"], release), started_ms=env.now)
    task = agent.task_of(case)
    result = None
    for wf_attempt in range(1, OUTCOME["max_workflow_attempts"] + 1):
        row["workflow_attempts"] = wf_attempt
        status = yield from _run_plan(ctx, case, row, release, proc, ledger, task, wf_attempt)
        if status in ("SUCCESS",) or status != "WRONG_ANSWER":
            result = status
            break
    else:
        result = "ESCALATED"
        if ctx.include_escalation_cost:
            row["cost_cu"]["escalation"] += OUTCOME["escalation_cu"]
    if result == "SUCCESS" and case["tenant"] == "support" and case["workflow"] != "child":
        ctx.effects.append({"request_id": case["request_id"], "release_id": release.release_id, "at_ms": env.now})
    if ledger.exceeded and row["budget_reason"] is None and result == "BUDGET_EXCEEDED":
        row["budget_reason"] = ledger.exceeded
    return result


def _run_plan(ctx, case, row, release, proc, ledger, task, wf_attempt):
    env = ctx.env
    gen = agent.plan(case, release)
    send = None
    tool_tokens = 0                                       # tool results carried into later model calls (this run of the plan)
    guard = PLAT["runtime"]["harness_guard_steps"]
    while True:
        try:
            op = gen.send(send)
        except StopIteration:
            return "SUCCESS" if case["workflow"] == "child" else "NO_ANSWER"
        if proc is not None and proc.cancelled:
            return "CANCELLED_DEADLINE"
        kind = "model" if isinstance(op, agent.Model) else "tool" if isinstance(op, agent.Tool) else \
            "fanout" if isinstance(op, agent.Spawn) else None
        reason = ledger.check(env.now, kind)
        if reason:
            row["budget_reason"] = row["budget_reason"] or reason
            return "BUDGET_EXCEEDED"
        if row["steps"] >= guard:
            return "HARNESS_GUARD"
        # orchestration overhead of the step
        oh = int(round(PLAT["runtime"]["step_overhead_ms"] * ctx.contention()))
        yield sleep(oh)
        row["time_ms"]["overhead"] += oh
        row["steps"] += 1
        row["cost_cu"]["platform"] += PLAT["costs"]["platform_step_cu"]
        ledger.charge(steps=1, cost_cu=PLAT["costs"]["platform_step_cu"])
        send = None
        if isinstance(op, agent.Retrieve):
            calls, chunks, tokens, lat, cost = yield from ctx.retriever.fetch(op.sources, release.retrieval)
            row["retrieval_calls"] += calls
            row["retrieved_chunks"] += chunks
            row["context_tokens"] = max(row["context_tokens"], tokens)
            row["time_ms"]["retrieval"] += lat
            row["cost_cu"]["retrieval"] += cost
            ledger.charge(cost_cu=cost)
        elif isinstance(op, agent.Model):
            history = WF["common"]["history_tokens"] if case["tenant"] == "support" else 0
            in_tokens = release.system_tokens + row["context_tokens"] + history + tool_tokens
            res = yield from ctx.models.call(task, in_tokens, op.out)
            row["throttles"] += res.throttles
            if res.status == "DEFERRED":
                row["time_ms"]["wait"] += res.latency_ms
                return "DEFERRED"
            row["model_calls"] += 1
            row["model_routes"][res.profile] = row["model_routes"].get(res.profile, 0) + 1
            row["input_tokens"] += res.in_tokens
            row["output_tokens"] += res.out_tokens
            row["cost_cu"]["model"] += res.cost_cu
            row["time_ms"]["model"] += res.latency_ms
            row["fallbacks"] += int(res.fallback)
            row["capability_violations"] += int(res.capability_violation)
            row["data_violations"] += int(res.data_violation)
            ledger.charge(model_calls=1, input_tokens=res.in_tokens, output_tokens=res.out_tokens, cost_cu=res.cost_cu)
            if op.decisive:
                p = outcome_probability(task, res.profile)
                if draw(ctx.scenario, case["request_id"], row["attempt"], wf_attempt, "outcome") >= p:
                    return "WRONG_ANSWER"
                return "SUCCESS"
        elif isinstance(op, agent.Tool):
            status = yield from _tool(ctx, case, row, op.name)
            ledger.charge(tool_calls=1)
            if status not in ("200", "PENDING"):
                return "FAILED_TOOL"
            tool_tokens += cfg("tools")["tools"][op.name]["result_tokens"]
            send = "PENDING" if status == "PENDING" else "SETTLED"
        elif isinstance(op, agent.Approval):
            row["approvals_requested"] += 1             # approval waits are not modelled in the load scenarios
        elif isinstance(op, agent.Spawn):
            ledger.charge(fanout=len(op.children))
            send = yield from _children(ctx, case, row, release, proc, ledger, op.children)


def _tool(ctx: Ctx, case: dict, row: dict, name: str):
    """One logical tool call, with the runtime's backoff on TOOL_BUSY when the gateway is on."""
    backoffs = cfg("tools")["gateway"]["step_backoff_ms"] if ctx.tool_backoff else []
    prio = cfg("platform")["tenants"][case["tenant"] if case["tenant"] in cfg("platform")["tenants"] else "support"]["priority"]
    tries = 0
    while True:
        res = yield from ctx.tools.call(name, priority=prio)
        row["tool_attempts"] += res.attempts
        row["time_ms"]["tool"] += res.latency_ms
        row["cost_cu"]["tool"] += cfg("tools")["tools"][name]["cu"] * res.attempts
        if res.status == "200":
            row["tool_calls"] += 1
            row["tool_result_tokens"] += cfg("tools")["tools"][name]["result_tokens"]
            if name == "payments.status" and case["request_id"] in ctx.payments_stuck:
                return "PENDING"
            return "200"
        if res.status == "TOOL_BUSY":
            row["tool_busy"] += 1
            if tries < len(backoffs):
                yield sleep(backoffs[tries])
                row["time_ms"]["wait"] += backoffs[tries]
                tries += 1
                continue
        return res.status


def _children(ctx: Ctx, case: dict, row: dict, release, proc, ledger: Ledger, kids: list[dict]):
    procs, rows = [], []
    for i, k in enumerate(kids):
        child_case = {"request_id": f"{case['request_id']}/{k['role']}", "tenant": case["tenant"], "workflow": "child",
                      "role": k["role"], "shipments": 1, "amount": 0}
        if k.get("stuck"):
            ctx.payments_stuck.add(child_case["request_id"])
        crow = new_row(child_case, row["attempt"], release, row["arm"])
        if ctx.budget_mode == "envelope":
            cl = ledger                                   # the propagated envelope: children draw from the parent
        elif ctx.budget_mode == "per-agent":
            cl = Ledger(ctx.envelopes.get("child", Envelope.none()), started_ms=ctx.env.now)
        else:
            cl = Ledger(Envelope.none(), started_ms=ctx.env.now)
        procs.append(ctx.env.process(run_workflow(ctx, child_case, crow, release, proc, cl), on_done=lambda res, crow=crow: crow.update(result=res)))
        rows.append(crow)
        ctx.child_rows.append(crow)
    results = yield join(procs)
    row["children"] += len(kids)
    for c in rows:                                        # roll the children's consumption into the parent's row
        for k in ("steps", "model_calls", "input_tokens", "output_tokens", "retrieval_calls", "retrieved_chunks", "tool_calls", "tool_result_tokens",
                  "tool_attempts", "tool_busy", "throttles", "fallbacks", "capability_violations", "data_violations"):
            row[k] += c[k]
        for k in row["cost_cu"]:
            row["cost_cu"][k] += c["cost_cu"][k]
        for k in row["time_ms"]:
            row["time_ms"][k] += c["time_ms"][k]
        for p, n in c["model_routes"].items():
            row["model_routes"][p] = row["model_routes"].get(p, 0) + n
        if ctx.budget_mode == "per-agent":                # per-agent ledgers: the parent's ledger never sees this spend
            pass
        elif ctx.budget_mode == "none":
            ledger.charge(model_calls=c["model_calls"], tool_calls=c["tool_calls"], cost_cu=sum(c["cost_cu"].values()))
    return results
