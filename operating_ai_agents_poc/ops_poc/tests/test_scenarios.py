"""The ten scenario tests: one per architectural claim of the article (E1-E10). Each runs its scenario from source,
every arm, and asserts the mechanism and the comparison the claim rests on. No recorded run is read: these tests
re-derive the evidence. The negative control lives in the proof pack (tools/proof_pack.py), not here.

Simulation units only. A pass means the mechanism behaves as claimed under the declared workload, not that any real
system will see these numbers.
"""

from __future__ import annotations

import pytest

from agentops import release as rel
from agentops import scenarios as SC
from agentops.common import cfg, experiments

PLAT = cfg("platform")
BOUND = PLAT["runtime"]["slots"] + PLAT["admission"]["queue_bound"]


def support(arm):
    return [q for q in arm.requests if q["tenant"] == "support"]


def goodput(arm) -> float:
    s = support(arm)
    return sum(q["served"] for q in s) / len(s)


@pytest.fixture(scope="module")
def e4():
    return SC.e4()


def test_01_admission_enforces_capacity_before_the_runtime():
    """Claim 1: capacity is enforced before unlimited work enters the runtime."""
    naive, ctl = SC.e1("naive"), SC.e1("controlled")
    assert ctl.stats["max"]["work_in_system"] <= BOUND                      # the operating envelope held at every event
    assert naive.stats["max"]["queued"] > PLAT["admission"]["queue_bound"]  # open admission let the queue grow past it
    refused = [r for r in ctl.rows if r["admission_result"] == "REJECTED_CAPACITY"]
    assert refused and all(r["start_ms"] is None for r in refused)          # refused explicitly, before any execution
    amp = lambda a: len(a.rows) / len(support(a))  # noqa: E731
    assert amp(naive) > amp(ctl)                                             # timeouts -> retries -> more load
    assert goodput(ctl) >= goodput(naive)


def test_02_tenant_fairness_protects_the_interactive_tenant():
    """Claim 2: multi-tenant platforms need tenant-aware controls, not only global limits."""
    naive, ctl = SC.e2("naive"), SC.e2("controlled")
    assert goodput(ctl) >= 0.99
    assert goodput(naive) < goodput(ctl)
    assert ctl.stats["max_by_tenant"]["finance"]["active"] <= PLAT["tenants"]["finance"]["max_concurrency"]
    fin = [q for q in ctl.requests if q["tenant"] == "finance"]
    assert all(q["outcome"] in ("SUCCESS", "ESCALATED") for q in fin)       # work-conserving: the batch still completes
    assert max(q["end_ms"] for q in fin) <= PLAT["tenants"]["finance"]["batch_deadline_ms"]


def test_03_concurrency_is_bounded_independently_of_demand():
    """Claim 3: concurrency must be bounded independently of incoming request volume."""
    naive, ctl = SC.e3("naive"), SC.e3("controlled")
    assert ctl.stats["max"]["active"] <= PLAT["runtime"]["slots"]
    assert naive.stats["max"]["active"] > PLAT["runtime"]["capacity"]
    assert not [r for r in ctl.rows if r["start_ms"] is not None and r["start_ms"] > r["deadline_ms"]]
    assert any(r["result"] == "SHED_DEADLINE" for r in ctl.rows)            # backpressure: dropped before execution
    assert goodput(ctl) > goodput(naive)


def test_04_workflow_budgets_stop_runaway_execution(e4):
    """Claim 4: production agents need explicit execution budgets, propagated to child workflows."""
    by = {arm: {r["request_id"]: r for r in e4[arm]} for arm in ("none", "per-agent", "envelope")}
    lim = e4["limits"]
    assert by["none"]["E4-RUNAWAY"]["result"] == "HARNESS_GUARD"            # unbounded: only the simulator stopped it
    run = by["envelope"]["E4-RUNAWAY"]
    assert run["result"] == "BUDGET_EXCEEDED" and run["steps"] <= lim["refund-dispute"]["steps"]
    assert by["envelope"]["E4-COORD"]["model_calls"] <= lim["dispute-investigation"]["model_calls"]
    assert by["per-agent"]["E4-COORD"]["model_calls"] > lim["dispute-investigation"]["model_calls"]


def test_05_routing_optimises_inside_the_contract():
    """Claim 5: routing reduces modelled cost within a declared capability/policy contract (not real model quality)."""
    arms = {a: SC.e5(a) for a in ("all-large", "all-small", "routed", "routed-any-fallback")}

    def cps(a):
        rows = arms[a].rows
        return sum(sum(v for k, v in r["cost_cu"].items() if k != "escalation") for r in rows) / sum(r["result"] == "SUCCESS" for r in rows)
    routed = arms["routed"].rows
    assert cps("routed") < cps("all-large")
    assert sum(r["capability_violations"] + r["data_violations"] for r in routed) == 0
    assert any(r["result"] == "DEFERRED" for r in routed)                    # it degraded explicitly during the throttle
    assert sum(r["data_violations"] for r in arms["routed-any-fallback"].rows) > 0
    assert sum(r["capability_violations"] for r in arms["all-small"].rows) > 0


def test_06_context_budgets_keep_required_evidence_and_scope_the_cache():
    """Claim 6: context and retrieval need resource controls; caches need a scope."""
    out = SC.e6()
    bounded = [x for x in out["retrieval"] if x["mode"] == "bounded"]
    naive = [x for x in out["retrieval"] if x["mode"] == "naive"]
    for x in bounded:                                                         # the fixture declares the required ids
        assert set(x["required"]) <= set(x["admitted"]), x["query"]
        assert x["context_tokens"] <= SC.rel.load("R41").retrieval["context_cap_tokens"] + SC.fixture("knowledge")["system_tokens"]
    assert sum(x["context_tokens"] for x in bounded) < sum(x["context_tokens"] for x in naive)
    scoped = [c for c in out["cache"] if c["cache"] == "scoped"]
    text = [c for c in out["cache"] if c["cache"] == "query-text"]
    assert not any(c["cross_principal"] or c["stale"] for c in scoped)
    assert any(c["cross_principal"] for c in text) and any(c["stale"] for c in text)
    assert any(c["hit"] for c in scoped)


def test_07_tool_gateway_governs_downstream_capacity():
    """Claim 7: tool capacity must be governed independently of model and runtime capacity."""
    naive, ctl, comp = SC.e7("naive"), SC.e7("controlled"), SC.e7("composed")
    cap = cfg("tools")["tools"]["payments.status"]["capacity"]
    for a in (ctl, comp):
        ps = a.stats["tools"]["payments.status"]
        assert ps["max_inflight"] <= cap and ps["503"] == 0
    assert naive.stats["tools"]["payments.status"]["max_inflight"] >= cfg("tools")["tools"]["payments.status"]["hard_limit"]
    attempts = lambda a: sum(r["tool_attempts"] for r in a.rows) / (sum(r["tool_calls"] for r in a.rows) + sum(r["result"] == "FAILED_TOOL" for r in a.rows))  # noqa: E731
    assert attempts(naive) > attempts(ctl)
    assert goodput(comp) >= goodput(naive)                                    # composed with fair scheduling, support is served


def test_08_a_behavioural_change_is_a_new_release():
    """Claim 8: behaviourally relevant non-code changes create a distinguishable agent release."""
    out = SC.e8()
    docs = out["releases"]
    assert len({d["image_digest"] for d in docs.values()}) == 1              # the image cannot see the change
    assert len({d["release_id"] for d in docs.values()}) == len(docs)        # the release can
    assert all(len(d["artifacts"]) == 1 for d in out["diffs"].values())
    tc = lambda n: sum(r["tool_calls"] for r in out["rows"][n])  # noqa: E731
    assert tc("R42-a") != tc("R41")                                          # a description changed behaviour, no code did
    assert all(r["release_id"] for rows in out["rows"].values() for r in rows)


def test_09_invariant_gates_block_bad_releases_before_traffic():
    """Claim 9: behavioural releases pass machine-checkable gates before receiving production traffic."""
    out = SC.e9()
    c = out["candidates"]
    blocked = {n for n, ev in c.items() if not ev["gate"]["passed"]}
    assert blocked == {"R42-b", "R42-c", "R42-d"}
    assert all(c[n]["canary_weight_granted"] == 0 for n in blocked)
    assert c["R42-b"]["task_success"] >= experiments("preregistration")["hypotheses"][8]["gate"]["task_success_min"]
    assert {n for n, ev in c.items() if ev["gate"]["passed"]} == {"R42-a", "R42-e"}


def test_10_the_canary_rolls_back_on_behaviour_not_http_status():
    """Claim 10: agent releases need behavioural canaries and rollback on operational evidence."""
    a = SC.canary("R42-a")
    assert a["decision"] == "ROLLBACK"
    assert all(abs(w["deltas"]["error_pp"]) <= 1.0 for w in a["windows"])   # it looked healthy by status code
    assert not [r for r in a["rows"] if r["release_id"] == a["candidate_id"] and r["arrival_ms"] > a["decided_at_ms"]]
    assert a["effects"]["by_candidate_before_decision"] > 0 and a["effects"]["reverted_by_rollback"] == 0
    assert SC.canary("R42-e")["decision"] == "PROMOTE"
    assert rel.load("R42-a").release_id != rel.load("R41").release_id
