"""Tools + Actions (P1 layer G): the downstream systems the tools call, a naive tool client, and a tool gateway.

Downstream model (declared, config/tools.toml): up to ``capacity`` concurrent calls run at the base latency; above it
every call slows by inflight / capacity; at ``hard_limit`` concurrent calls the connection pool is exhausted and a new
call fails at once with 503; the downstream's own rate limit answers 429 when exceeded.

The tool gateway governs a tool's capacity independently of the model runtime: per-tool concurrency equal to the
downstream's capacity, a token bucket at its rate limit, a bounded, priority-ordered wait (interactive before batch),
and a circuit breaker on consecutive 503s. When it cannot admit a call it answers TOOL_BUSY: backpressure the runtime
turns into a delayed retry of the step, not an immediate hammering of the downstream.
"""

from __future__ import annotations

from dataclasses import dataclass

from .common import cfg
from .sim import Env, Slots, TokenBucket, sleep, value


@dataclass
class ToolResult:
    status: str          # 200 | 503 | 429 | TOOL_BUSY
    latency_ms: int
    attempts: int        # calls that reached the downstream


class Downstream:
    def __init__(self, env: Env, name: str, relaxed: bool):
        t = cfg("tools")["tools"][name]
        r = cfg("tools")["relaxed"]
        self.env, self.name = env, name
        self.base = t["base_ms"]
        self.capacity = r["capacity"] if relaxed else t["capacity"]
        self.hard = r["hard_limit"] if relaxed else t["hard_limit"]
        self.bucket = TokenBucket(r["rps"] if relaxed else t["rps"])
        self.inflight = 0
        self.max_inflight = 0
        self.counts = {"200": 0, "503": 0, "429": 0}

    def call(self):
        """One request to the downstream. A generator: ``res = yield from ds.call()`` -> (status, latency)."""
        if self.inflight >= self.hard:
            self.counts["503"] += 1
            yield sleep(20)                       # connection refused, fast
            return "503", 20
        if self.bucket.wait(self.env.now):
            self.counts["429"] += 1
            yield sleep(10)
            return "429", 10
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        lat = int(round(self.base * max(1.0, self.inflight / self.capacity)))
        yield sleep(lat)
        self.inflight -= 1
        self.counts["200"] += 1
        return "200", lat


class ToolLayer:
    """Every tool call of a scenario goes through here. ``gateway=False`` is the naive client: call, and on 503/429
    retry after a short pause; ``gateway=True`` is the tool gateway."""

    def __init__(self, env: Env, relaxed: bool = True, gateway: bool = False, constrained: tuple[str, ...] = ()):
        self.env, self.gateway = env, gateway
        names = cfg("tools")["tools"]
        self.ds = {n: Downstream(env, n, relaxed or n not in constrained) for n in names}
        g = cfg("tools")["gateway"]
        self.max_wait, self.queue_bound = g["max_wait_ms"], g["queue_bound"]
        self.breaker_threshold, self.breaker_open = g["breaker_threshold"], g["breaker_open_ms"]
        self.slots = {n: Slots(env, d.capacity) for n, d in self.ds.items()}
        self.rate = {n: TokenBucket(cfg("tools")["tools"][n]["rps"] if not (relaxed or n not in constrained) else 100000)
                     for n in names}
        self.consecutive_503 = {n: 0 for n in names}
        self.open_until = {n: -1 for n in names}
        self.busy = {n: 0 for n in names}
        self.breaker_opened = {n: 0 for n in names}

    def call(self, name: str, priority: int = 1):
        ds = self.ds[name]
        if not self.gateway:
            nv = cfg("tools")["naive"]
            attempts, total = 0, 0
            for i in range(1 + nv["retries"]):
                attempts += 1
                status, lat = yield from ds.call()
                total += lat
                if status == "200":
                    return ToolResult("200", total, attempts)
                yield sleep(nv["retry_pause_ms"])
                total += nv["retry_pause_ms"]
            return ToolResult(status, total, attempts)
        # ---- the gateway ---------------------------------------------------------------------------------------
        if self.env.now < self.open_until[name]:
            self.busy[name] += 1
            yield value(None)
            return ToolResult("TOOL_BUSY", 0, 0)
        slots = self.slots[name]
        if slots.waiting() >= self.queue_bound:
            self.busy[name] += 1
            yield value(None)
            return ToolResult("TOOL_BUSY", 0, 0)
        t0 = self.env.now
        ok = yield slots.acquire(priority=priority, max_wait=self.max_wait)
        if not ok:
            self.busy[name] += 1
            return ToolResult("TOOL_BUSY", self.env.now - t0, 0)
        try:
            w = self.rate[name].wait(self.env.now)
            while w:
                yield sleep(w)
                w = self.rate[name].wait(self.env.now)
            status, _ = yield from ds.call()
        finally:
            slots.release()
        if status == "503":
            self.consecutive_503[name] += 1
            if self.consecutive_503[name] >= self.breaker_threshold:
                self.open_until[name] = self.env.now + self.breaker_open
                self.breaker_opened[name] += 1
                self.consecutive_503[name] = 0
        else:
            self.consecutive_503[name] = 0
        return ToolResult(status if status == "200" else "TOOL_BUSY", self.env.now - t0, 1)

    def stats(self) -> dict:
        return {n: {"max_inflight": d.max_inflight, **d.counts, "busy": self.busy[n], "breaker_opened": self.breaker_opened[n],
                    "capacity": d.capacity, "hard_limit": d.hard} for n, d in self.ds.items()}
