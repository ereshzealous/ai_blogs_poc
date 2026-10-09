"""The world outside the platform: who sends work, when, and how clients behave. Same in every arm of a scenario.

Cases are drawn deterministically from (seed, scenario, index): the workflow type from the day's traffic mix, the
number of shipments of an order, the refund amount. Arrivals are evenly spaced at the offered rate with a
deterministic jitter, so no two runs differ and no arm sees a different workload.

Clients (declared, config/platform.toml [client]): an interactive support client waits ``timeout_ms`` for an attempt,
then gives up and retries at once (up to ``naive_retries`` times); on an explicit capacity error it waits the
Retry-After and tries once more. Finance's batch submitter never gives up on an item.
"""

from __future__ import annotations

from .common import cfg, draw, pick
from .sim import Env, sleep

WF = cfg("workflows")
CLIENT = cfg("platform")["client"]
RETRY_AFTER = cfg("platform")["admission"]["retry_after_ms"]


def support_case(seed: int, scenario: str, i: int, mix: str = "black-friday", shipments: list | None = None) -> dict:
    wf = pick(WF["mix"][mix], seed, scenario, i, "workflow")
    ship = shipments or WF["workflows"]["order-status"]["shipments"]
    amounts = {int(k): v for k, v in WF["workflows"]["refund-dispute"]["amounts"].items()}
    return {"request_id": f"{scenario}-S{i:05d}", "tenant": "support", "workflow": wf,
            "shipments": pick(ship, seed, scenario, i, "shipments") if wf == "order-status" else 1,
            "amount": pick(amounts, seed, scenario, i, "amount") if wf == "refund-dispute" else 0}


def finance_case(scenario: str, i: int) -> dict:
    return {"request_id": f"{scenario}-F{i:05d}", "tenant": "finance", "workflow": "recon-check", "shipments": 1, "amount": 0}


def arrivals(seed: int, scenario: str, phases: list[tuple[int, float]], start_ms: int = 0, tag: str = "s") -> list[int]:
    """Arrival times for phases of (duration_ms, rate per second): evenly spaced, each nudged by up to ±40 % of the gap."""
    out, t0 = [], start_ms
    for k, (dur, rate) in enumerate(phases):
        if rate <= 0:
            t0 += dur
            continue
        gap = 1000 / rate
        n = int(dur * rate / 1000)
        for i in range(n):
            j = (draw(seed, scenario, tag, k, i, "jitter") - 0.5) * 0.8 * gap
            out.append(int(t0 + i * gap + gap / 2 + j))
        t0 += dur
    return sorted(out)


def wait_for(attempt, timeout_ms: int | None):
    """Resume with 'done' when the attempt finishes, or 'timeout' if the client's patience runs out first."""
    def req(env: Env, resume) -> None:
        if attempt.done:
            env.at(0, resume, "done")
            return
        fired = [False]

        def on_done(_r) -> None:
            if not fired[0]:
                fired[0] = True
                env.at(0, resume, "done")
        attempt.waiters.append(on_done)
        if timeout_ms is not None:
            def on_timeout() -> None:
                if not fired[0]:
                    fired[0] = True
                    resume("timeout")
            env.at(timeout_ms, on_timeout)
    return req


def support_client(env: Env, platform, case: dict, release_for, at_ms: int, record: list):
    """One customer's request: attempts until served, out of retries, or refused. Appends a request record."""
    yield sleep(at_ms - env.now)
    first = env.now
    attempt, polite_left, naive_left = 0, CLIENT["polite_retries"], CLIENT["naive_retries"]
    served, outcome = False, "GAVE_UP"
    while True:
        attempt += 1
        a = platform.submit(case, attempt, env.now + CLIENT["timeout_ms"], release_for(case))
        if a.result == "REJECTED_CAPACITY":
            if polite_left:
                polite_left -= 1
                yield sleep(RETRY_AFTER)
                continue
            outcome = "REFUSED"
            break
        w = yield wait_for(a, CLIENT["timeout_ms"])
        if w == "done":
            served = a.result == "SUCCESS"
            outcome = a.result
            break
        a.row["client_gave_up_ms"] = env.now
        if naive_left:
            naive_left -= 1
            continue
        break
    record.append({"request_id": case["request_id"], "tenant": "support", "workflow": case["workflow"], "first_ms": first,
                   "attempts": attempt, "served": served, "outcome": outcome, "end_ms": env.now})


def batch_submitter(env: Env, platform, cases: list[dict], times: list[int], release_for, record: list):
    """Finance's reconciliation run: submits every item at its time and never gives up on one."""
    for case, t in zip(cases, times):
        if t > env.now:
            yield sleep(t - env.now)
        a = platform.submit(case, 1, None, release_for(case))
        record.append({"request_id": case["request_id"], "tenant": "finance", "workflow": case["workflow"], "first_ms": t,
                       "attempts": 1, "attempt_obj": a})
