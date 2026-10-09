"""Packing: truncation cuts, the assembler never does, qualifiers travel with their procedure, the budget holds."""

from knowledge_rag import gates as G
from knowledge_rag import packer as P
from knowledge_rag.util import est_tokens


def cands(retr, uids):
    out = []
    for i, u in enumerate(uids, start=1):
        c = G.Candidate(retr.by_id[u], "hybrid", i)
        c.role, c.tier = ("procedure", 1) if retr.by_id[u]["doc_type"] == "runbook" else (G.ROLE[retr.by_id[u]["doc_type"]], None)
        out.append(c)
    return out


UIDS = ["RB-CHK-007@v4#remediation", "RB-CHK-007@v4#symptoms", "RB-CHK-007@v4#diagnose", "CP-12@v3#approvals",
        "RB-CHK-007@v4#approval-and-exceptions", "RB-GEN-012@v1#rollbacks"]


def test_truncation_cuts_mid_unit(retr):
    p = P.truncate(cands(retr, UIDS), 120)
    assert p.entries[-1]["truncated"] and p.used_tokens <= 121


def test_assembler_never_cuts_and_respects_the_budget(retr):
    for b in (120, 200, 300, 600):
        p = P.assembler(cands(retr, UIDS), b, ["procedure"], "checkout-api/latency-after-deploy")
        assert not any(e["truncated"] for e in p.entries)
        assert p.used_tokens <= b


def test_qualifier_travels_with_its_procedure(retr):
    p = P.assembler(cands(retr, UIDS), 300, ["procedure"], "checkout-api/latency-after-deploy")
    ids = [e["unit_id"] for e in p.entries]
    assert ids[:2] == ["RB-CHK-007@v4#remediation", "RB-CHK-007@v4#approval-and-exceptions"]


def test_identical_content_is_kept_once(retr):
    cs = cands(retr, ["RB-CHK-007@v4#remediation", "RB-CHK-007@v4#remediation"])
    p = P.assembler(cs, 600, ["procedure"], None)
    assert len(p.entries) == 1 and p.dropped[0]["reason"] == "duplicate content"


def test_structured_record_falls_back_to_compact(w):
    r = w.deployments.query("acme", "production", "checkout-api", version="4.17.0")[0]
    c = G.Candidate(G.record_unit(r, "deployments"), "structured", 1)
    c.role = "change_fact"
    full = est_tokens(P.render_governed("E1", c))
    p = P.assembler([c], full - 5, ["change"], None)
    assert p.entries and "compact" not in p.entries[0]["text"] and est_tokens(p.entries[0]["text"]) < full
