"""Admission gates: authorization recheck, fail closed, scope, lifecycle, authority, conflict, and positive controls."""

from knowledge_rag import gates as G
from knowledge_rag.query import analyze_query
from knowledge_rag.world import load_world


def cand(retr, uid, rank=1):
    return G.Candidate(retr.by_id[uid], "hybrid", rank)


def test_recheck_excludes_what_the_stale_index_acl_lets_through(retr, req, w):
    r = req("D-K11")
    c = cand(retr, "VENDOR-ACN-01@v1#escalation")
    assert G.index_prefilter(r.principal)(c.unit)                       # the index copy still says eng-all
    G.recheck([c], r, w)
    assert c.decision == "excluded" and c.gate == "authorization"


def test_recheck_fails_closed_when_the_source_is_down(retr, req):
    down = load_world(down=frozenset({"runbooks"}))
    r = req("D-K1")
    c = cand(retr, "RB-INVW-001@v1#remediation")
    G.recheck([c], r, down)
    assert c.decision == "excluded" and "fail closed" in c.reason


def test_superseded_at_source_fetches_the_current_version(retr, req, w):
    r = req("D-K12")
    out = G.recheck([cand(retr, "RB-NOT-004@v1#remediation")], r, w)
    new = [c for c in out if c.origin == "source-replacement"]
    assert new and new[0].uid == "RB-NOT-004@v2#remediation" and new[0].unit.get("fetched_from_source")


def test_scope_lifecycle_and_authority(retr, req, w):
    r = req("D-K3")
    qa = analyze_query(r.question, r.tenant, r.environment, w)
    cs = [cand(retr, u, i) for i, u in enumerate(["RB-PAY-007@v2#remediation", "RB-PAY-007@v1#remediation", "GX-RB-CHK-003@v2#remediation",
                                                   "STG-OPS-004@v3#pool-and-connection-settings", "INC-4820@v1#summary"], start=1)]
    cs = G.recheck(cs, r, w)
    G.scope_gate(cs, r, qa.service, w)
    G.assign_roles(cs, r, qa.service, w)
    G.lifecycle_gate(cs, r)
    G.authority_gate(cs, r, qa.tasks, G.target_procedure_key(cs), w)
    by = {c.uid: c for c in cs}
    assert by["RB-PAY-007@v2#remediation"].decision == "candidate" and by["RB-PAY-007@v2#remediation"].tier == 1
    assert by["RB-PAY-007@v1#remediation"].gate == "lifecycle"
    assert by["GX-RB-CHK-003@v2#remediation"].gate == "scope"
    assert by["STG-OPS-004@v3#pool-and-connection-settings"].gate == "scope"
    assert by["INC-4820@v1#summary"].gate == "authority"                # history not asked for, procedure exists


def test_draft_is_not_effective(retr, req):
    r = req("D-K14")
    c = cand(retr, "RB-CHK-007@v5#remediation")
    G.lifecycle_gate([c], r)
    assert c.gate == "lifecycle" and "draft" in c.reason


def test_unresolved_conflict_is_kept_not_ranked_away(retr, req, w):
    r = req("D-K7")
    cs = [cand(retr, "RB-SIX-002@v2#remediation", 2), cand(retr, "RB-SIX-005@v1#remediation", 1)]
    G.assign_roles(cs, r, "search-indexer", w)
    assert [c.tier for c in cs] == [2, 2]
    conflicts = G.conflict_gate(cs)
    assert conflicts and conflicts[0]["procedure_key"] == "search-indexer/indexing-lag"
    assert all(c.decision == "candidate" for c in cs)


def test_runbook_of_record_outranks_a_disagreeing_owner_runbook(retr, req, w):
    r = req("D-K7")
    a, b = cand(retr, "RB-SIX-002@v2#remediation"), cand(retr, "RB-SIX-005@v1#remediation")
    a.role, a.tier, b.role, b.tier = "procedure", 1, "procedure", 2
    assert not G.conflict_gate([a, b])
    assert b.gate == "conflict" and a.decision == "candidate"


def test_positive_control_authorized_reader(retr, w, dev_cases):
    from s2_eval.common import request
    case = {**dev_cases["D-K0"], "principal": "kavita.nair"}
    r = request(case, w)
    c = cand(retr, "SEC-PM-2207@v1#root-cause")
    G.recheck([c], r, w)
    assert c.decision == "candidate"


def test_positive_control_other_tenant_reads_its_own(retr, req, w):
    r = req("D-K4")                                   # rohan.verma, globex
    c = cand(retr, "GX-RB-INV-002@v1#remediation")
    G.recheck([c], r, w)
    G.scope_gate([c], r, "inventory-api", w)
    assert c.decision == "candidate"
