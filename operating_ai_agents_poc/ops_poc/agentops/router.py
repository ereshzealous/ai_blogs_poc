"""Model services (P1 layer F): model profiles, the eligibility contract, routing, provider quotas and fallback.

Routing modes (E5 compares them; every other scenario uses ``routed``):
  routed               the cheapest ELIGIBLE profile (tier >= the task's min_tier and allowed to process its data class),
                       unless the release's routing table overrides it; on a provider throttle, fall back only to another
                       eligible profile, wait for quota up to a bound, then defer explicitly
  routed-any-fallback  the same primary route, but on a throttle fall back to any profile with enough capability,
                       whatever data it may process (the unsafe fallback)
  all-large            the cheapest tier-3 profile allowed to process the data class, for every task
  all-small            the cheapest tier-1 profile allowed to process the data class, for every task

Profiles, quotas, prices and latencies are synthetic (config/models.toml). Nothing here describes a real model.
"""

from __future__ import annotations

from dataclasses import dataclass

from .common import cfg
from .sim import Env, TokenBucket, sleep, value

MODES = ("routed", "routed-any-fallback", "all-large", "all-small")


@dataclass
class CallResult:
    status: str                 # OK | DEFERRED
    profile: str | None
    in_tokens: int
    out_tokens: int
    cost_cu: float
    latency_ms: int
    throttles: int
    fallback: bool
    capability_violation: bool
    data_violation: bool


def profiles() -> dict:
    return cfg("models")["profiles"]


def contract(task: str) -> dict:
    return cfg("models")["contract"][task]


def unit_cost(p: dict) -> float:
    return p["in_cu_per_1k"] + p["out_cu_per_1k"]


def eligible(task: str) -> list[str]:
    """Profiles inside the contract for this task, cheapest first."""
    c, P = contract(task), profiles()
    ok = [n for n, p in P.items() if p["tier"] >= c["min_tier"] and c["data"] in p["data"]]
    return sorted(ok, key=lambda n: (unit_cost(P[n]), n))


def capable(task: str) -> list[str]:
    """Profiles with enough capability, ignoring the data class (what an unsafe fallback considers)."""
    c, P = contract(task), profiles()
    return sorted((n for n, p in P.items() if p["tier"] >= c["min_tier"]), key=lambda n: (unit_cost(P[n]), n))


def violations(task: str, profile: str) -> tuple[bool, bool]:
    c, p = contract(task), profiles()[profile]
    return p["tier"] < c["min_tier"], c["data"] not in p["data"]


def primary(task: str, mode: str, overrides: dict) -> str:
    P, c = profiles(), contract(task)
    if mode in ("routed", "routed-any-fallback"):
        if task in overrides:
            return overrides[task]
        return eligible(task)[0]
    tier = 3 if mode == "all-large" else 1
    opts = [n for n, p in P.items() if p["tier"] == tier and c["data"] in p["data"]]
    return sorted(opts, key=lambda n: (unit_cost(P[n]), n))[0]


class ModelService:
    def __init__(self, env: Env, mode: str = "routed", overrides: dict | None = None, outages: dict | None = None,
                 contention=lambda: 1.0):
        assert mode in MODES, mode
        self.env, self.mode, self.overrides = env, mode, overrides or {}
        self.contention = contention
        g = cfg("models")["gateway"]
        self.quota_wait = g["quota_wait_ms"]
        outages = outages or {}
        self.req = {n: TokenBucket(p["rps"], outages=outages.get(n)) for n, p in profiles().items()}
        self.tok = {n: TokenBucket(p["itps"], outages=outages.get(n)) for n, p in profiles().items()}
        self.calls = {n: 0 for n in profiles()}
        self.throttled = 0

    def _quota(self, profile: str, in_tokens: int) -> int:
        """0 if the provider accepts the call now; otherwise the provider's 429 retry-after, in ms."""
        w = self.req[profile].wait(self.env.now)
        if w:
            return w
        w = self.tok[profile].wait(self.env.now, in_tokens)
        if w:
            self.req[profile].tokens += 1000      # give the request token back: the call did not go out
        return w

    def call(self, task: str, in_tokens: int, out_tokens: int):
        """A generator (use with ``yield from``): route, respect quotas, fall back as the mode allows, then run the call."""
        P = profiles()
        first = primary(task, self.mode, self.overrides)
        throttles, waited, fallback = 0, 0, False
        if self.mode == "routed":
            order = [first] + [n for n in eligible(task) if n != first]
        elif self.mode == "routed-any-fallback":
            order = [first] + [n for n in capable(task) if n != first]
        else:
            order = [first]
        chosen = None
        while chosen is None:
            best_wait = None
            for n in order:
                w = self._quota(n, in_tokens)
                if w == 0:
                    chosen = n
                    break
                throttles += 1
                self.throttled += 1
                best_wait = w if best_wait is None else min(best_wait, w)
            if chosen is None:
                if waited + best_wait > self.quota_wait:
                    yield value(None)
                    return CallResult("DEFERRED", None, 0, 0, 0.0, waited, throttles, False, False, False)
                yield sleep(best_wait)
                waited += best_wait
        fallback = chosen != first
        p = P[chosen]
        base = p["base_ms"] + p["ms_per_1k_in"] * in_tokens / 1000 + p["ms_per_out"] * out_tokens
        lat = int(round(base * self.contention()))
        yield sleep(lat)
        self.calls[chosen] += 1
        cost = in_tokens * p["in_cu_per_1k"] / 1000 + out_tokens * p["out_cu_per_1k"] / 1000
        cap_v, data_v = violations(task, chosen)
        return CallResult("OK", chosen, in_tokens, out_tokens, cost, lat + waited, throttles, fallback, cap_v, data_v)


def outcome_probability(task: str, profile: str) -> float:
    gap = contract(task)["min_tier"] - profiles()[profile]["tier"]
    o = cfg("models")["outcome"]
    return o["gap_0"] if gap <= 0 else o["gap_1"] if gap == 1 else o["gap_2"]
