"""Orchestration (P1 layer C): admission, queues, scheduling, bounded concurrency, deadlines and cancellation.

Policies (each scenario arm picks one per dimension; everything else is held constant):
  admission   "open"      every attempt is admitted into an unbounded queue
              "bounded"   admitted only while work in system (queued + running) < slots + queue_bound; otherwise an
                          explicit capacity error with Retry-After (never a silent drop)
  slots       an int (bounded concurrency) or None (every admitted attempt starts at once)
  scheduling  "fifo"      one global first-come-first-served queue
              "fair"      a queue per tenant, weighted deficit round robin, and a per-tenant concurrency cap (a bulkhead)
  deadlines   False       queued work runs whenever it reaches the head, even if its client gave up long ago
              True        a queued attempt that cannot finish before its client gives up is dropped at dequeue
                          (SHED_DEADLINE), and a running attempt is cancelled at its deadline (CANCELLED_DEADLINE)

Exact maxima (running, queued, work in system) are updated at every change, not sampled, so "never exceeded" is a
statement about every event of the run. A once-per-second timeline is kept for figures.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .common import cfg
from .runtime import Ctx, new_row, run_workflow
from .sim import Env

PLAT = cfg("platform")
EXPECTED = {k: v["expected_ms"] for k, v in cfg("workflows")["workflows"].items()}


@dataclass
class Attempt:
    case: dict
    attempt: int
    deadline_ms: int | None
    row: dict
    release: object
    done: bool = False
    result: str | None = None
    waiters: list = field(default_factory=list)
    proc: object = None


@dataclass
class Policy:
    admission: str = "open"
    slots: int | None = None
    scheduling: str = "fifo"
    deadlines: bool = False
    queue_bound: int | None = None          # defaults to platform.toml admission.queue_bound when admission is bounded


class Platform:
    def __init__(self, env: Env, ctx: Ctx, policy: Policy, tenants: list[str]):
        self.env, self.ctx, self.p = env, ctx, policy
        self.tenants = tenants
        self.queues = {t: deque() for t in tenants}
        self.fifo: deque = deque()
        self.active = 0
        self.active_t = {t: 0 for t in tenants}
        self.weight = {t: PLAT["tenants"][t]["weight"] for t in tenants}
        self.cap = {t: PLAT["tenants"][t]["max_concurrency"] if policy.scheduling == "fair" else None for t in tenants}
        self.deficit = {t: 0 for t in tenants}
        self.ptr = 0
        self.qbound = policy.queue_bound if policy.queue_bound is not None else PLAT["admission"]["queue_bound"]
        self.max = {"active": 0, "queued": 0, "work_in_system": 0}
        self.max_t = {t: {"active": 0, "queued": 0} for t in tenants}
        self.timeline: list[dict] = []
        self.rows: list[dict] = []
        ctx.contention = self.contention

    # ---- shared-resource contention (the processor-sharing model) ------------------------------------------------------
    def contention(self) -> float:
        return max(1.0, self.active / PLAT["runtime"]["capacity"])

    def queued(self) -> int:
        return len(self.fifo) if self.p.scheduling == "fifo" else sum(len(q) for q in self.queues.values())

    def _note(self) -> None:
        q = self.queued()
        self.max["active"] = max(self.max["active"], self.active)
        self.max["queued"] = max(self.max["queued"], q)
        self.max["work_in_system"] = max(self.max["work_in_system"], self.active + q)
        for t in self.tenants:
            qt = sum(1 for a in self.fifo if a.case["tenant"] == t) if self.p.scheduling == "fifo" else len(self.queues[t])
            self.max_t[t]["active"] = max(self.max_t[t]["active"], self.active_t[t])
            self.max_t[t]["queued"] = max(self.max_t[t]["queued"], qt)

    def sample(self, every_ms: int, until_ms: int) -> None:
        def tick() -> None:
            snap = {"t_ms": self.env.now, "active": self.active, "queued": self.queued()}
            for t in self.tenants:
                snap[f"active.{t}"] = self.active_t[t]
            ds = self.ctx.tools.ds.get("payments.status")
            if ds is not None:
                snap["payments_inflight"] = ds.inflight
            self.timeline.append(snap)
            if self.env.now + every_ms <= until_ms:
                self.env.at(every_ms, tick)
        self.env.at(0, tick)

    # ---- admission ---------------------------------------------------------------------------------------------------
    def submit(self, case: dict, attempt: int, deadline_ms: int | None, release) -> Attempt:
        row = new_row(case, attempt, release, self.ctx.arm)
        row["arrival_ms"], row["deadline_ms"] = self.env.now, deadline_ms
        a = Attempt(case, attempt, deadline_ms, row, release)
        self.rows.append(row)
        if self.p.admission == "bounded":
            limit = (self.p.slots or 0) + self.qbound
            if self.active + self.queued() >= limit:
                row["admission_result"] = "REJECTED_CAPACITY"
                row["result"] = "REJECTED_CAPACITY"
                row["end_ms"] = self.env.now
                a.done, a.result = True, "REJECTED_CAPACITY"
                return a
        row["admission_result"] = "ADMITTED"
        if self.p.scheduling == "fifo":
            self.fifo.append(a)
        else:
            self.queues[case["tenant"]].append(a)
        self._note()
        self._dispatch()
        return a

    # ---- scheduling --------------------------------------------------------------------------------------------------
    def _free(self) -> bool:
        return self.p.slots is None or self.active < self.p.slots

    def _pick(self) -> Attempt | None:
        if self.p.scheduling == "fifo":
            return self.fifo.popleft() if self.fifo else None
        n, skipped = len(self.tenants), 0
        while skipped < n:
            t = self.tenants[self.ptr]
            q = self.queues[t]
            if not q or (self.cap[t] is not None and self.active_t[t] >= self.cap[t]):
                if not q:
                    self.deficit[t] = 0
                self.ptr = (self.ptr + 1) % n
                skipped += 1
                continue
            if self.deficit[t] < 1:
                self.deficit[t] += self.weight[t]
            self.deficit[t] -= 1
            if self.deficit[t] < 1:
                self.ptr = (self.ptr + 1) % n
            return q.popleft()
        return None

    def _dispatch(self) -> None:
        while self._free():
            a = self._pick()
            if a is None:
                break
            if self.p.deadlines and a.deadline_ms is not None and self.env.now + EXPECTED[a.case["workflow"]] > a.deadline_ms:
                self._finish(a, "SHED_DEADLINE", started=False)
                continue
            self._start(a)
        self._note()

    def _start(self, a: Attempt) -> None:
        self.active += 1
        self.active_t[a.case["tenant"]] += 1
        a.row["start_ms"] = self.env.now
        a.row["queue_delay_ms"] = self.env.now - a.row["arrival_ms"]
        self._note()

        def done(result: str) -> None:
            self.active -= 1
            self.active_t[a.case["tenant"]] -= 1
            self._finish(a, result, started=True)
            self._dispatch()
        holder: dict = {}

        def body():                       # runs on the first engine step, after holder["p"] is set
            return (yield from run_workflow(self.ctx, a.case, a.row, a.release, holder["p"]))
        a.proc = holder["p"] = self.env.process(body(), on_done=done)
        if self.p.deadlines and a.deadline_ms is not None:
            proc = a.proc
            self.env.at(max(0, a.deadline_ms - self.env.now), lambda: (not proc.done) and proc.cancel())

    def _finish(self, a: Attempt, result: str, started: bool) -> None:
        r = a.row
        r["result"] = result
        r["end_ms"] = self.env.now
        if started:
            r["latency_ms"] = self.env.now - r["arrival_ms"]
        else:
            r["queue_delay_ms"] = self.env.now - r["arrival_ms"]
        r["deadline_met"] = None if a.deadline_ms is None else self.env.now <= a.deadline_ms
        a.done, a.result = True, result
        for w in a.waiters:
            w(result)
