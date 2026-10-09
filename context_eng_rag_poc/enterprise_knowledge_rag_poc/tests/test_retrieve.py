"""Candidate retrieval: tokenization, the pre-filter before ranking, RRF."""

from knowledge_rag.gates import index_prefilter
from knowledge_rag.retrieve import analyze


def test_compound_identifiers_survive_tokenization():
    t = analyze("What does RB-SRCH-040 say about 4.17.0 and threeds2.eu?")
    assert {"rb-srch-040", "4.17.0", "threeds2.eu", "040", "srch"} <= set(t)


def test_bm25_separates_near_identical_ids(retr):
    top = [u for u, _ in retr.search("bm25", "RB-SRCH-040", 3)]
    assert top[0].startswith("RB-SRCH-040@")


def test_prefilter_applies_before_ranking(retr, w, req):
    r = req("D-K1")
    filt = index_prefilter(r.principal)
    ranked = [u for u, _ in retr.search("hybrid", r.question, 20, filt)]
    units = retr.by_id
    assert all(units[u]["meta"]["tenant"] in ("acme", "*") for u in ranked)
    assert all(set(units[u]["meta"]["acl"]) & set(r.principal.groups) for u in ranked)
    assert len(ranked) == 20          # a rejected unit does not take a slot


def test_rrf_is_rank_based(retr):
    q = "checkout-api latency after a deploy"
    fused = dict(retr.hybrid(q))
    vec = [u for u, _ in retr.vector(q)[:50]]
    lex = [u for u, s in retr.bm25(q) if s > 0][:50]
    u = vec[0]
    expect = 1 / (60 + 1) + (1 / (60 + lex.index(u) + 1) if u in lex else 0)
    assert abs(fused[u] - expect) < 1e-12
