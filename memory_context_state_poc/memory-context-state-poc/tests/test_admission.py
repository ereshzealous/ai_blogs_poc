"""Admission: authority ranking, conflicts, budget, determinism, and the fairness of the two arms."""

import random

from governed_memory.context.assembler import governed_admission, naive_admission
from governed_memory.context.budget import tokens
from governed_memory.retrieval.semantic import Candidate

from .conftest import rec

RUNBOOK = dict(memory_type="knowledge", source={"type": "runbook", "id": "RB-CHK-007"},
               provenance={"created_by": "checkout-team", "evidence_refs": ["RB-CHK-007@v4"]},
               scope={"tenant": "acme", "environment": "all", "entities": ["checkout-api"]},
               trust={"source_class": "source-owned"}, claim_type="procedure", expires_at=None)


def cands(*pairs):
    return [Candidate(r, s) for r, s in pairs]


def test_authoritative_runbook_ranked_above_more_similar_episode(query, policy):
    rb = rec("kb-rb", "roll back through the release pipeline", **RUNBOOK)
    ep = rec("ep", "restart pods fixed checkout latency")
    a = governed_admission(cands((ep, 0.95), (rb, 0.70)), query, policy, budget=1000)
    assert [c.record.id for c in a.admitted] == ["kb-rb", "ep"]


def test_contradicted_memory_is_marked_kept_and_placed_after_evidence(query, policy):
    rb = rec("kb-rb", "roll back through the release pipeline", **RUNBOOK)
    old = rec("ep-old", "restart pods first", contradicts=["kb-rb"])
    a = governed_admission(cands((old, 0.95), (rb, 0.70)), query, policy, budget=1000, corpus={"kb-rb": rb, "ep-old": old})
    assert [c.record.id for c in a.admitted] == ["kb-rb"]
    assert [c.record.id for c in a.historical] == ["ep-old"]
    d = {x.record_id: x for x in a.decisions}
    assert d["ep-old"].outcome == "historical" and d["ep-old"].reason == "contradicted_by:kb-rb"


def test_contradicted_memory_dropped_when_no_budget_left(query, policy):
    rb = rec("kb-rb", "roll back " * 20, **RUNBOOK)
    old = rec("ep-old", "restart pods first " * 5, contradicts=["kb-rb"])
    a = governed_admission(cands((old, 0.95), (rb, 0.70)), query, policy, budget=tokens(rb.content) + 2, corpus={"kb-rb": rb, "ep-old": old})
    assert [c.record.id for c in a.admitted] == ["kb-rb"] and a.historical == []


def test_budget_respected_in_both_arms(query, policy):
    items = cands(*[(rec(f"e{i:02d}", "checkout latency episode " * 6), 0.9 - i / 100) for i in range(20)])
    for a in (naive_admission(items, budget=200), governed_admission(items, query, policy, budget=200)):
        assert a.tokens <= 200 and a.admitted


def test_naive_fills_by_similarity_and_ignores_metadata(query):
    bad = rec("bad", scope={"tenant": "globex", "environment": "staging", "entities": ["checkout-api"]}, expires_at="2020-01-01T00:00:00Z")
    good = rec("good")
    a = naive_admission(cands((bad, 0.9), (good, 0.8)), budget=1000)
    assert [c.record.id for c in a.admitted] == ["bad", "good"]


def test_naive_k_cap(query):
    items = cands(*[(rec(f"e{i}"), 0.9 - i / 100) for i in range(8)])
    assert len(naive_admission(items, budget=10_000, k=5).admitted) == 5


def test_ranking_is_deterministic_under_input_order(query, policy):
    items = cands(*[(rec(f"e{i:02d}", created_at="2026-08-01T00:00:00Z"), 0.8) for i in range(10)])
    ref = [c.record.id for c in governed_admission(items, query, policy, budget=150).admitted]
    for seed in range(5):
        shuffled = items[:]
        random.Random(seed).shuffle(shuffled)
        assert [c.record.id for c in governed_admission(shuffled, query, policy, budget=150).admitted] == ref
        assert [c.record.id for c in naive_admission(shuffled, budget=150).admitted] == [c.record.id for c in naive_admission(items, budget=150).admitted]


def test_every_candidate_gets_one_decision(query, policy):
    items = cands((rec("a"), 0.9), (rec("b", expires_at="2020-01-01T00:00:00Z"), 0.8),
                  (rec("c", scope={"tenant": "globex", "environment": "production", "entities": ["checkout-api"]}), 0.7))
    a = governed_admission(items, query, policy, budget=1000)
    assert sorted(d.record_id for d in a.decisions) == ["a", "b", "c"]
    assert {d.record_id: d.reason for d in a.decisions if d.outcome == "excluded"} == {"b": "expired", "c": "wrong_tenant"}


def test_scope_filter_runs_before_ranking(query, policy):
    """A wrong-tenant record never takes a ranking slot, however similar or authoritative it looks."""
    foreign_rb = rec("kb-globex", **{**RUNBOOK, "scope": {"tenant": "globex", "environment": "all", "entities": ["checkout-api"]}})
    a = governed_admission(cands((foreign_rb, 0.99), (rec("ep"), 0.5)), query, policy, budget=1000)
    assert [d.rank for d in a.decisions if d.record_id == "kb-globex"] == [None]


def test_contradicted_but_crowded_out_keeps_its_mark(query, policy):
    rb = rec("kb-rb", "roll back " * 20, **RUNBOOK)
    old = rec("ep-old", "restart pods first " * 5, contradicts=["kb-rb"])
    a = governed_admission(cands((old, 0.95), (rb, 0.70)), query, policy, budget=tokens(rb.content) + 2, corpus={"kb-rb": rb, "ep-old": old})
    assert {d.record_id: d.reason for d in a.decisions}["ep-old"] == "over_budget:contradicted_by:kb-rb"
