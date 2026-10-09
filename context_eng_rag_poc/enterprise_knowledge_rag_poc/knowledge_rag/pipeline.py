"""The naive and the governed knowledge pipelines as ONE flow with switches, so every arm and every ablation differs only
by the controls it names.

    NAIVE     vector top 8 over the unfiltered index -> chunks in rank order, cut at the budget -> model -> raw answer
    GOVERNED  hybrid top 20 behind the index pre-filter + identifier lookups + structured systems of record
              -> authoritative recheck -> scope -> lifecycle -> authority -> conflict -> evidence assembler
              -> model -> citation verifier -> bound answer

Controls (experiment E removes one from GOVERNED, or adds one to NAIVE):
    retrieval            vector | bm25 | hybrid, and k
    acl_scope            index pre-filter, authoritative recheck, scope gate
    recheck              the authoritative recheck alone (removed in the negative control)
    lifecycle_authority  lifecycle and authority gates (freshness from the source needs the recheck)
    conflict             conflict detection
    structured           identifier lookups and the structured systems of record
    packer, render       truncate | relevance | assembler; naive | governed rendering
    verify               citation verification and binding
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, replace

from knowledge_rag import gates as G
from knowledge_rag import packer as P
from knowledge_rag.generate import ModelClient, messages_for
from knowledge_rag.query import QueryAnalysis, analyze_query
from knowledge_rag.retrieve import Retriever
from knowledge_rag.util import config, est_tokens, iso, ts
from knowledge_rag.verify import bind, verify_answer
from knowledge_rag.world import World

RCFG = config("retrieval.yaml")


@dataclass(frozen=True)
class Controls:
    name: str
    retrieval: str = "hybrid"
    k: int = RCFG["candidates"]
    acl_scope: bool = True
    recheck: bool = True
    lifecycle_authority: bool = True
    conflict: bool = True
    structured: bool = True
    packer: str = "assembler"
    render: str = "governed"
    verify: bool = True

    def as_dict(self) -> dict:
        return asdict(self)


GOVERNED = Controls("governed")
NAIVE = Controls("naive", retrieval="vector", k=RCFG["naive_k"], acl_scope=False, recheck=False, lifecycle_authority=False,
                 conflict=False, structured=False, packer="truncate", render="naive", verify=False)

# experiment E: remove one control from GOVERNED / keep only one control on NAIVE
REMOVE_ONE = {
    "gov-minus-hybrid": replace(GOVERNED, name="gov-minus-hybrid", retrieval="vector"),
    "gov-minus-acl-scope": replace(GOVERNED, name="gov-minus-acl-scope", acl_scope=False, recheck=False),
    "gov-minus-lifecycle-authority": replace(GOVERNED, name="gov-minus-lifecycle-authority", lifecycle_authority=False),
    "gov-minus-conflict": replace(GOVERNED, name="gov-minus-conflict", conflict=False),
    "gov-minus-structured": replace(GOVERNED, name="gov-minus-structured", structured=False),
    "gov-minus-assembler": replace(GOVERNED, name="gov-minus-assembler", packer="truncate"),
    "gov-minus-verify": replace(GOVERNED, name="gov-minus-verify", verify=False),
}
KEEP_ONE = {
    "naive-plus-hybrid": replace(NAIVE, name="naive-plus-hybrid", retrieval="hybrid"),
    "naive-plus-acl-scope": replace(NAIVE, name="naive-plus-acl-scope", acl_scope=True, recheck=True),
    "naive-plus-lifecycle-authority": replace(NAIVE, name="naive-plus-lifecycle-authority", lifecycle_authority=True),
    "naive-plus-structured": replace(NAIVE, name="naive-plus-structured", structured=True),
    "naive-plus-assembler": replace(NAIVE, name="naive-plus-assembler", packer="assembler", render="governed"),
    "naive-plus-verify": replace(NAIVE, name="naive-plus-verify", verify=True),
}
# the negative control: the recheck removed. The index's stale ACL and status then decide. The revocation invariant
# must FAIL (a withdrawn runbook or a narrowed document reaches the model).
NEGATIVE_CONTROL = replace(GOVERNED, name="nc-minus-recheck", recheck=False)
VARIANTS = {"naive": NAIVE, "governed": GOVERNED, **REMOVE_ONE, **KEEP_ONE, "nc-minus-recheck": NEGATIVE_CONTROL}


# ---- stages -------------------------------------------------------------------------------------------------------------
def retrieve_candidates(req: G.Request, qa: QueryAnalysis, ctl: Controls, retriever: Retriever, world: World) -> list[G.Candidate]:
    filt = G.index_prefilter(req.principal) if ctl.acl_scope else None
    ranked = retriever.search(ctl.retrieval, req.question, ctl.k, filt)
    cands = [G.Candidate(retriever.by_id[uid], ctl.retrieval, i, s) for i, (uid, s) in enumerate(ranked, start=1)]
    if ctl.structured:
        seen = {c.uid for c in cands}
        for doc_id in qa.doc_ids:                                   # identifier lookup against the source of record
            for doc in world.sources.by_doc_id(doc_id):
                for u in G.source_units(doc):
                    if u["unit_id"] not in seen:
                        seen.add(u["unit_id"])
                        cands.append(G.Candidate(u, "identifier", 0, 1.0))
        cands += structured_candidates(req, qa, world)
    return cands


def structured_candidates(req: G.Request, qa: QueryAnalysis, world: World) -> list[G.Candidate]:
    out, seen = [], set()
    if qa.service:
        rec = world.cmdb.lookup(req.tenant, req.environment, qa.service)
        if rec:
            out.append(G.Candidate(G.record_unit(rec, "cmdb"), "structured", 1))
        since = req.as_of.timestamp() - RCFG["recency_window_hours"] * 3600
        from datetime import datetime, timezone
        deps = world.deployments.query(req.tenant, req.environment, qa.service, since=datetime.fromtimestamp(since, timezone.utc),
                                       until=req.as_of)
        for i, r in enumerate(deps, start=1):
            out.append(G.Candidate(G.record_unit(r, "deployments"), "structured", i))
    for v in qa.versions:                                           # an exact version: the release record, this tenant/env
        for r in world.deployments.by_version(v):
            if r["tenant"] == req.tenant and r["environment"] == req.environment and ts(r["deployed_at"]) <= req.as_of:
                out.append(G.Candidate(G.record_unit(r, "deployments"), "structured", 1))
    uniq = []
    for c in out:
        if c.uid not in seen:
            seen.add(c.uid)
            uniq.append(c)
    return uniq


def govern(cands: list[G.Candidate], req: G.Request, qa: QueryAnalysis, ctl: Controls, world: World) -> dict:
    """Run the gates the controls enable. Returns the admitted candidates (in relevance order), conflicts, gaps, target."""
    if ctl.acl_scope and ctl.recheck:
        cands = G.recheck(cands, req, world)
    if ctl.acl_scope:
        G.scope_gate(cands, req, qa.service, world)
    G.assign_roles(cands, req, qa.service, world)
    target = G.target_procedure_key(cands)
    if ctl.lifecycle_authority:
        G.lifecycle_gate(cands, req)
        G.authority_gate(cands, req, qa.tasks, target, world)
    conflicts = G.conflict_gate(cands) if ctl.conflict else []
    if target:                                   # only a conflict about the question's own procedure concerns this answer
        conflicts = [cf for cf in conflicts if cf["procedure_key"] == target]
    gaps = G.gaps_for(cands, req, qa.service, target, world) if ctl.lifecycle_authority else []
    admitted = G.admit(cands)
    origin_order = {"identifier": 0, "source-replacement": 1, "hybrid": 2, "vector": 2, "bm25": 2, "structured": 3}
    admitted.sort(key=lambda c: (origin_order.get(c.origin, 2), c.rank, c.uid))
    excluded = {}
    for c in cands:
        if c.decision == "excluded" and c.gate != "authorization":
            excluded[c.gate] = excluded.get(c.gate, 0) + 1
    return {"all": cands, "admitted": admitted, "conflicts": conflicts, "gaps": gaps, "target": target, "excluded": excluded}


def admissible_ids(cands: list[G.Candidate], req: G.Request, qa: QueryAnalysis, world: World) -> set[str]:
    """What the governed gates would admit from these exact units: used by the verifier to judge any arm's citations."""
    fresh = G.clone(cands)
    for c in fresh:
        c.decision, c.gate, c.reason, c.live = "candidate", None, None, {}
    g = govern(fresh, req, qa, GOVERNED, world)
    return {c.uid for c in g["admitted"]}


def prelude(req: G.Request, qa: QueryAnalysis, g: dict) -> str:
    lines = [f"REQUEST CONTEXT: tenant {req.tenant} · environment {req.environment} · service {qa.service or 'not identified'} · "
             f"as of {iso(req.as_of)}"]
    for cf in g["conflicts"]:
        docs = "; ".join(f"{k} says {v['action']} (approval: {v['approval']})" for k, v in cf["documents"].items())
        lines.append(f"UNRESOLVED CONFLICT for {cf['procedure_key']}: {docs}. Same authority tier; the CMDB names no runbook of record.")
    for gap in g["gaps"]:
        lines.append(f"EVIDENCE GAP: {gap}")
    if g["excluded"]:
        lines.append("LEFT OUT: " + ", ".join(f"{n} by {gate}" for gate, n in sorted(g["excluded"].items())) +
                     " (out of scope, not current, or not authoritative for this request).")
    return "\n".join(lines)


def pack(admitted: list[G.Candidate], req: G.Request, qa: QueryAnalysis, ctl: Controls, g: dict) -> P.Packed:
    pre = prelude(req, qa, g) if ctl.render == "governed" else ""
    render = P.render_governed if ctl.render == "governed" else P.render_naive
    if ctl.packer == "assembler":
        return P.assembler(admitted, req.budget, qa.tasks, g["target"], prelude=pre)
    if ctl.packer == "relevance":
        return P.relevance(admitted, req.budget, render=render, prelude=pre)
    return P.truncate(admitted, req.budget, render=render, prelude=pre)


# ---- the whole flow ---------------------------------------------------------------------------------------------------
def run(req: G.Request, ctl: Controls, retriever: Retriever, world: World, model: ModelClient | None, seed: int | None) -> dict:
    t0 = time.perf_counter()
    qa = analyze_query(req.question, req.tenant, req.environment, world)
    cands = retrieve_candidates(req, qa, ctl, retriever, world)
    t1 = time.perf_counter()
    g = govern(cands, req, qa, ctl, world)
    t2 = time.perf_counter()
    packed = pack(g["admitted"], req, qa, ctl, g)
    t3 = time.perf_counter()
    msgs = messages_for(req.question, req.principal, req.tenant, req.environment, iso(req.as_of), packed.text)
    gen, raw = None, None
    if not packed.entries and ctl.verify:
        raw = {"status": "abstain", "summary": "No admissible evidence for this request.",
               "recommended_action": {"action": "none", "target": "", "approval_required": False, "approver": ""},
               "claims": [], "gaps": g["gaps"] or ["no admissible evidence"], "conflicts": []}
        gen = {"key": None, "parse_error": None, "usage": {}, "from_tape": None, "skipped": "no admissible evidence: model not called"}
    elif model is not None:
        out = model.complete(msgs, seed)
        raw = out["parsed"] or {"status": "abstain", "summary": "", "recommended_action": {"action": "none", "target": "",
                                "approval_required": False, "approver": ""}, "claims": [], "gaps": ["unparseable model output"], "conflicts": []}
        gen = {k: out[k] for k in ("key", "parse_error", "usage", "from_tape")}
    t4 = time.perf_counter()
    result = {"case_id": req.case_id, "arm": ctl.name, "controls": ctl.as_dict(), "seed": seed, "query": qa.as_dict(),
              "candidates": [c.trace() for c in g["all"]], "admitted": [c.uid for c in g["admitted"]],
              "conflicts": g["conflicts"], "gaps": g["gaps"], "target_procedure_key": g["target"], "packed": packed.summary(),
              "context_tokens_est": est_tokens(packed.text), "prompt_tokens_est": sum(est_tokens(m["content"]) for m in msgs),
              "context_text": packed.text}
    if raw is not None:
        adm = admissible_ids([c for c in g["all"] if c.uid in {e["unit_id"] for e in packed.entries}], req, qa, world)
        entries = {e["eid"]: {**e, "admissible": e["unit_id"] in adm} for e in packed.entries}
        verdict = verify_answer(raw, entries, req.question)
        owner = world.cmdb.lookup(req.tenant, req.environment, qa.service) if qa.service else None
        if ctl.verify:
            final, notes = bind(raw, verdict, entries, g["conflicts"], owner)
        else:
            final, notes = raw, []
        result.update({"generation": gen, "raw_answer": raw, "verdict": verdict, "final_answer": final, "binding_notes": notes})
    t5 = time.perf_counter()
    result["_timings_ms"] = {"retrieve": (t1 - t0) * 1e3, "govern": (t2 - t1) * 1e3, "pack": (t3 - t2) * 1e3,
                             "generate": (t4 - t3) * 1e3, "verify": (t5 - t4) * 1e3, "total": (t5 - t0) * 1e3}
    return result
