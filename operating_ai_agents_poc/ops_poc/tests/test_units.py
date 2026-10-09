"""Unit tests of the mechanisms the scenarios rest on (engine, slots, quotas, fair scheduling, envelopes, release
identity, cache scope, routing eligibility, the gate, determinism)."""

from __future__ import annotations

import json

from agentops import release as rel
from agentops import router
from agentops import scenarios as SC
from agentops.budget import Envelope, Ledger
from agentops.common import pct
from agentops.platform import Attempt, Platform, Policy
from agentops.retrieval import Cache
from agentops.sim import Env, Slots, TokenBucket, sleep


def test_engine_orders_events_by_time_then_sequence():
    env, seen = Env(), []
    for name, d in (("b", 5), ("a", 5), ("c", 1)):
        env.at(d, seen.append, name)
    env.run()
    assert seen == ["c", "b", "a"]


def test_processes_resume_in_virtual_time():
    env, out = Env(), []

    def p():
        yield sleep(250)
        out.append(env.now)
    env.process(p())
    env.run()
    assert out == [250]


def test_slots_grant_by_priority_and_expire_waits():
    env, got = Env(), []
    s = Slots(env, 1)

    def holder():
        yield s.acquire()
        yield sleep(100)
        s.release()

    def waiter(name, prio, wait):
        ok = yield s.acquire(priority=prio, max_wait=wait)
        got.append((name, ok, env.now))
        if ok:
            s.release()
    env.process(holder())
    env.process(waiter("batch", 3, None))
    env.process(waiter("interactive", 1, None))
    env.process(waiter("impatient", 1, 50))
    env.run()
    assert got[0] == ("impatient", False, 50)
    assert [g[0] for g in got[1:]] == ["interactive", "batch"]


def test_token_bucket_rate_and_outage():
    b = TokenBucket(rate=2, burst=2, outages=[(5000, 6000)])
    assert b.wait(0) == 0 and b.wait(0) == 0
    assert b.wait(0) == 500                       # 2 per second: the next token in 500 ms
    assert b.wait(5200) == 800                    # inside the outage window: wait until it ends


def test_fair_scheduling_dispatches_by_weight():
    env, ctx, platform = SC.build("UT", "fair", Policy(admission="open", slots=0, scheduling="fair"), ["support", "finance"])
    r41 = rel.load("R41")
    for i in range(8):
        for t in ("support", "finance"):
            case = {"request_id": f"{t}-{i}", "tenant": t, "workflow": "order-status" if t == "support" else "recon-check", "shipments": 1, "amount": 0}
            platform.queues[t].append(Attempt(case, 1, None, {}, r41))
    order = [platform._pick().case["tenant"][0] for _ in range(8)]
    assert "".join(order) == "sssfsssf"           # weights 3:1


def test_ledger_checks_before_the_step_and_children_share_it():
    led = Ledger(Envelope(model_calls=2, cost_cu=10.0))
    assert led.check(0, "model") is None
    led.charge(model_calls=2, cost_cu=4.0)
    assert led.check(0, "model") == "model_calls"
    shared = Ledger(Envelope(steps=3))
    shared.charge(steps=3)                         # a child charging the parent's ledger
    assert shared.check(0) == "steps"


def test_release_identity_is_content_addressed():
    a, b, e = rel.load("R41"), rel.load("R42-a"), rel.load("R42-e")
    assert a.image_digest == b.image_digest == e.image_digest
    assert len({a.release_id, b.release_id, e.release_id}) == 3
    assert rel.artifacts_changed(a, b) == ["tools.orders.lookup"]
    assert rel.load("R42-a").release_id == b.release_id   # recomputed, not assigned


def test_registry_refuses_traffic_to_an_ungated_release():
    reg = rel.Registry(rel.load("R41"))
    cand = rel.load("R42-b")
    reg.submit(cand)
    assert reg.set_weight(cand, 10, "try") is False
    reg.gate(cand, False, ["invariant data_policy"])
    assert reg.set_weight(cand, 10, "try") is False and reg.weights.get(cand.release_id, 0) == 0


def test_cache_scope_separates_principals_and_versions():
    base = {"text": "Where is my order?", "tenant": "support", "personal": True, "kb_version": "v1", "policy_version": "p1"}
    for scoped, leak in ((False, True), (True, False)):
        c = Cache(scoped)
        c.lookup({**base, "principal": "A"})
        assert c.lookup({**base, "principal": "B"})["cross_principal"] is leak
    c = Cache(True)
    shared = {**base, "personal": False, "text": "What is your return policy?"}
    c.lookup({**shared, "principal": "A"})
    assert c.lookup({**shared, "principal": "B"})["hit"] is True            # shared questions still hit
    assert c.lookup({**shared, "principal": "B", "kb_version": "v2"})["hit"] is False


def test_eligibility_contract():
    assert router.eligible("refund-dispute") == ["large-eu"]
    assert set(router.eligible("recon-check")) == {"small-eu", "large-eu"}
    assert router.violations("delivery-change", "small") == (True, False)
    assert router.violations("refund-dispute", "large") == (False, True)


def test_gate_blocks_on_an_invariant_whatever_the_averages():
    base = {"cost_per_success": 10.0, "p95_latency_ms": 1000}
    good = {"invariants": {"data_policy": 0}, "task_success": 1.0, "tool_selection": 1.0, "cost_per_success": 8.0, "p95_latency_ms": 900}
    assert SC.gate(good, base) == (True, [])
    ok, why = SC.gate({**good, "invariants": {"data_policy": 3}}, base)
    assert not ok and why == ["invariant data_policy: 3"]


def test_nearest_rank_percentile():
    xs = list(range(1, 101))
    assert (pct(xs, 50), pct(xs, 95), pct(xs, 99), pct(xs, 100)) == (50, 95, 99, 100)
    assert pct([], 95) == 0


def test_scenarios_are_deterministic():
    a = json.dumps(SC.e1("controlled").rows, sort_keys=True)
    b = json.dumps(SC.e1("controlled").rows, sort_keys=True)
    assert a == b
    assert json.dumps(SC.e6(), sort_keys=True) == json.dumps(SC.e6(), sort_keys=True)
