"""The discrete-event engine: a virtual clock in integer simulated milliseconds, an event heap ordered by
(time, sequence), and processes written as generators that yield requests.

No threads, no sleeping, no wall clock: two runs of the same scenario produce the same events in the same order, so
every file a run writes is byte-identical on a rerun.

A request is any callable ``req(env, resume)``. The engine calls it when the process yields it; whatever the request
waits for (a slot, a quota, a delay, a child) eventually calls ``resume(value)``.
"""

from __future__ import annotations

import heapq
import itertools
from typing import Any, Callable, Generator


class Cancelled(Exception):
    """Raised inside a workflow at its next resume after orchestration cancelled it (cooperative cancellation)."""


class Env:
    def __init__(self) -> None:
        self.now = 0
        self._q: list = []
        self._seq = itertools.count()

    def at(self, delay: float, fn: Callable, *args: Any) -> None:
        heapq.heappush(self._q, (self.now + max(0, int(round(delay))), next(self._seq), fn, args))

    def run(self, until: int | None = None) -> None:
        while self._q:
            t = self._q[0][0]
            if until is not None and t > until:
                break
            _, _, fn, args = heapq.heappop(self._q)
            self.now = t
            fn(*args)

    def process(self, gen: Generator, on_done: Callable | None = None) -> "Process":
        return Process(self, gen, on_done)


class Process:
    def __init__(self, env: Env, gen: Generator, on_done: Callable | None = None):
        self.env, self.gen, self.on_done = env, gen, on_done
        self.done = False
        self.cancelled = False
        self.value: Any = None
        self.waiters: list[Callable] = []
        env.at(0, self._step, None, None)

    def cancel(self) -> None:
        """Cooperative: the flag is read by the workflow at its next step boundary (agentops/runtime.py), so a slot
        or a downstream call in progress is never abandoned half-way."""
        self.cancelled = True

    def _step(self, value: Any, exc: BaseException | None) -> None:
        if self.done:
            return
        try:
            if exc is not None:
                req = self.gen.throw(exc)
            else:
                req = self.gen.send(value)
        except StopIteration as stop:
            self._finish(stop.value)
            return
        req(self.env, self._resume)

    def _resume(self, value: Any = None) -> None:
        self.env.at(0, self._step, value, None)

    def _finish(self, value: Any) -> None:
        self.done, self.value = True, value
        if self.on_done:
            self.on_done(value)
        for w in self.waiters:
            w(value)


# ---- requests --------------------------------------------------------------------------------------------------------

def sleep(ms: float):
    def req(env: Env, resume: Callable) -> None:
        env.at(ms, resume, None)
    return req


def value(v: Any):
    """Resume at once with a value (lets a component answer synchronously through the same interface)."""
    def req(env: Env, resume: Callable) -> None:
        env.at(0, resume, v)
    return req


def join(procs: list[Process]):
    """Resume when every process has finished, with their values in order (children run concurrently)."""
    def req(env: Env, resume: Callable) -> None:
        pending = [p for p in procs if not p.done]
        if not pending:
            env.at(0, resume, [p.value for p in procs])
            return
        left = [len(pending)]

        def one(_v: Any) -> None:
            left[0] -= 1
            if left[0] == 0:
                env.at(0, resume, [p.value for p in procs])
        for p in pending:
            p.waiters.append(one)
    return req


class Slots:
    """A counting semaphore with an ordered wait queue: (priority, arrival sequence). Lower priority value first.
    acquire(max_wait=...) resumes True when a slot is granted, False if the wait expired first."""

    def __init__(self, env: Env, capacity: int | None):
        self.env, self.capacity = env, capacity
        self.used = 0
        self.max_used = 0
        self._q: list = []
        self._seq = itertools.count()

    def acquire(self, priority: int = 0, max_wait: int | None = None):
        def req(env: Env, resume: Callable) -> None:
            if self.capacity is None or (self.used < self.capacity and not self._q):
                self._grant()
                env.at(0, resume, True)
                return
            entry = [priority, next(self._seq), resume, True]
            heapq.heappush(self._q, entry)
            if max_wait is not None:
                def expire() -> None:
                    if entry[3]:
                        entry[3] = False
                        resume(False)
                env.at(max_wait, expire)
        return req

    def waiting(self) -> int:
        return sum(1 for e in self._q if e[3])

    def _grant(self) -> None:
        self.used += 1
        self.max_used = max(self.max_used, self.used)

    def release(self) -> None:
        self.used -= 1
        while self._q:
            entry = heapq.heappop(self._q)
            if entry[3]:
                entry[3] = False
                self._grant()
                self.env.at(0, entry[2], True)
                return


class TokenBucket:
    """A rate limit in integer milli-tokens: ``rate`` tokens per second, burst = ``burst`` tokens. ``wait(n)`` takes n
    tokens and returns 0, or returns how long until n tokens will be available (and takes nothing). Outage windows
    [(start_ms, end_ms)] hold the bucket empty."""

    def __init__(self, rate: int, burst: int | None = None, outages: list[tuple[int, int]] | None = None):
        self.rate = int(rate)
        self.cap = int(burst if burst is not None else rate) * 1000
        self.tokens = self.cap
        self.last = 0
        self.outages = outages or []

    def _refill(self, now: int) -> None:
        if now > self.last:
            self.tokens = min(self.cap, self.tokens + (now - self.last) * self.rate)
            self.last = now

    def wait(self, now: int, n: int = 1) -> int:
        for a, b in self.outages:
            if a <= now < b:
                self.tokens, self.last = 0, b
                return b - now
        self._refill(now)
        need = n * 1000
        if need > self.cap:          # a request bigger than the burst: allow it once the bucket is full
            need = self.cap
        if self.tokens >= need:
            self.tokens -= need
            return 0
        return -(-(need - self.tokens) // self.rate)   # ceil, in ms
