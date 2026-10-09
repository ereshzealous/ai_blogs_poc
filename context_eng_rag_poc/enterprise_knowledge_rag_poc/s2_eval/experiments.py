"""Experiments A-E, D2 and the negative control. Each isolates one question (docs/design and the preregistration):

A   retrieval quality       same corpus, queries, k and filter; vector vs BM25 vs hybrid RRF; plus the structured route
B   evidence admission      the SAME frozen candidates (hybrid top 20, unfiltered); naive vs governed admission; the same
                            packer (whole units by relevance) and budget for both
C   context packing         the SAME governed-admitted pool; top-k truncation vs the evidence assembler; budget sweep
D   end to end              naive vs governed pipeline, live local model, recorded; raw and bound answers
D2  verifier accuracy       a labelled set of claim-citation pairs; the lexical verifier and a model judge
E   ablations               remove-one-control from governed, keep-only-one-control on naive (evidence level for every
                            variant; end to end, one seed)
NC  negative control        governed without the authoritative recheck: the revocation invariant must fail
"""

from __future__ import annotations

import json
import math
import re

from knowledge_rag import gates as G
from knowledge_rag import packer as P
from knowledge_rag.pipeline import GOVERNED, NAIVE, VARIANTS, Controls, govern, pack, retrieve_candidates, run, structured_candidates
from knowledge_rag.query import analyze_query
from knowledge_rag.util import config, norm
from s2_eval import score as S
from s2_eval.common import RCFG, request

KS = RCFG["experiment_a_k"]


def _strip(res: dict) -> tuple[dict, dict]:
    t = res.pop("_timings_ms", {})
    return res, t


# ---- A · retrieval ----------------------------------------------------------------------------------------------------
def exp_a(cases: list[dict], retriever, w) -> list[dict]:
    rows = []
    for case in cases:
        req = request(case, w)
        need = S.needed(case["case_id"], index_only=True)
        for prefilter in (False, True):
            filt = G.index_prefilter(req.principal) if prefilter else None
            for method in ("vector", "bm25", "hybrid"):
                ranked = [u for u, _ in retriever.search(method, req.question, max(KS), filt)]
                row = {"case_id": case["case_id"], "split": case["split"], "k_type": case["k_type"], "method": method,
                       "prefilter": prefilter, "ranked": ranked, "needed": need,
                       "invalid_top5": [u for u in ranked[:5] if S.forbidden_class(case["case_id"], u)]}
                if need:
                    for k in KS:
                        hit = [u for u in need if u in ranked[:k]]
                        row[f"recall@{k}"] = len(hit) / len(need)
                        row[f"full@{k}"] = len(hit) == len(need)
                    first = next((i for i, u in enumerate(ranked[:10], start=1) if u in need), None)
                    row["rr@10"] = 1 / first if first else 0.0
                    dcg = sum(1 / math.log2(i + 1) for i, u in enumerate(ranked[:10], start=1) if u in need)
                    idcg = sum(1 / math.log2(i + 1) for i in range(1, min(len(need), 10) + 1))
                    row["ndcg@10"] = dcg / idcg
                rows.append(row)
        rows.append(structured_route_row(case, req, retriever, w))
    return rows


def _record_facts(r: dict) -> list[str]:
    if r["record_id"].startswith("dep:"):
        nums = sorted({n for d in r.get("config_diff", []) for n in re.findall(r"\d+(?:\.\d+)*", d)})
        return [r["version"]] + nums + (["migration"] if r.get("migration") else [])
    return [r["owner"]] + sorted(set(r.get("runbooks", {}).values()))


def structured_route_row(case: dict, req, retriever, w) -> dict:
    """For each needed structured record: does the structured route return it, and do its exact fields appear together
    in one of the top-20 prose units of each retrieval method?"""
    qa = analyze_query(req.question, req.tenant, req.environment, w)
    route = {c.uid for c in structured_candidates(req, qa, w)}
    recs = [u for u in S.needed(case["case_id"]) if u.startswith(("dep:", "cmdb:"))]
    allrec = {r["record_id"]: r for r in w.deployments.records + w.cmdb.records}
    out = {"case_id": case["case_id"], "split": case["split"], "k_type": case["k_type"], "method": "structured-route",
           "records": recs, "route_returned": sorted(set(recs) & route), "prose_has_fields": {}}
    for method in ("vector", "bm25", "hybrid"):
        ranked = [u for u, _ in retriever.search(method, req.question, 20, None)]
        found = []
        for rid in recs:
            facts = [norm(f) for f in _record_facts(allrec[rid])]
            if any(all(re.search(rf"(?<![\w.]){re.escape(f)}(?![\w])", norm(retriever.by_id[u]["text"])) for f in facts) for u in ranked):
                found.append(rid)
        out["prose_has_fields"][method] = found
    return out


# ---- B · admission over frozen candidates ----------------------------------------------------------------------------------
def frozen_candidates(case: dict, req, retriever) -> list[G.Candidate]:
    ranked = retriever.search("hybrid", req.question, RCFG["candidates"], None)
    return [G.Candidate(retriever.by_id[u], "hybrid", i, s) for i, (u, s) in enumerate(ranked, start=1)]


def exp_b(cases: list[dict], retriever, w) -> list[dict]:
    rows = []
    for case in cases:
        req = request(case, w)
        qa = analyze_query(req.question, req.tenant, req.environment, w)
        base = frozen_candidates(case, req, retriever)
        pool = [c.uid for c in base]
        need = [u for u in S.needed(case["case_id"]) if u in pool]
        for arm in ("naive", "governed"):
            cands = G.clone(base)
            conflicts, excluded = [], []
            if arm == "governed":
                cands = G.recheck(cands, req, w, fetch_replacements=False)
                G.scope_gate(cands, req, qa.service, w)
                G.assign_roles(cands, req, qa.service, w)
                target = G.target_procedure_key(cands)
                G.lifecycle_gate(cands, req)
                G.authority_gate(cands, req, qa.tasks, target, w)
                conflicts = [cf for cf in G.conflict_gate(cands) if not target or cf["procedure_key"] == target]
                admitted = G.admit(cands)
                excluded = [c.trace() for c in cands if c.decision == "excluded"]
            else:
                admitted = cands
            admitted.sort(key=lambda c: c.rank)
            packed = P.relevance(admitted, req.budget, render=P.render_naive)
            ctx = [e["unit_id"] for e in packed.entries]
            audit = S.context_audit(case["case_id"], ctx, req.principal, w, retriever.by_id)
            rows.append({"case_id": case["case_id"], "split": case["split"], "k_type": case["k_type"], "arm": arm, "pool": pool,
                         "admitted": [c.uid for c in admitted], "context": ctx, "tokens": packed.used_tokens,
                         "needed_in_pool": need, "needed_in_context": [u for u in need if u in ctx],
                         "needed_admitted": [u for u in need if u in {c.uid for c in admitted}],
                         "conflicts": [cf["procedure_key"] for cf in conflicts], "conflict_expected": S.label(case["case_id"])["conflict"],
                         "excluded": excluded, **{f"ctx_{k}": v for k, v in audit.items()},
                         "pool_audit": S.context_audit(case["case_id"], pool, req.principal, w, retriever.by_id)})
    return rows


# ---- C · packing over an identical admitted pool ----------------------------------------------------------------------------
def exp_c(cases: list[dict], retriever, w) -> list[dict]:
    rows = []
    for case in cases:
        req = request(case, w)
        qa = analyze_query(req.question, req.tenant, req.environment, w)
        g = govern(retrieve_candidates(req, qa, GOVERNED, retriever, w), req, qa, GOVERNED, w)
        from knowledge_rag.pipeline import prelude
        pre = prelude(req, qa, g)
        pool = [c.uid for c in g["admitted"]]
        need = [u for u in S.needed(case["case_id"]) if u in pool]
        for budget in RCFG["budget"]["sweep"]:
            for method in ("truncate", "assembler"):
                if method == "truncate":
                    pk = P.truncate(g["admitted"], budget, render=P.render_governed, prelude=pre)
                else:
                    pk = P.assembler(g["admitted"], budget, qa.tasks, g["target"], prelude=pre)
                full = [e["unit_id"] for e in pk.entries if not e["truncated"]]
                cut = [e["unit_id"] for e in pk.entries if e["truncated"]]
                hashes = [w_hash(retriever, e["unit_id"]) for e in pk.entries]
                quals = S.qualifiers_in(case["case_id"], pk.text)
                rows.append({"case_id": case["case_id"], "split": case["split"], "k_type": case["k_type"], "budget": budget, "method": method,
                             "pool": pool, "context_full": full, "context_truncated": cut, "tokens": pk.used_tokens,
                             "needed_in_pool": need, "needed_covered": [u for u in need if u in full], "needed_cut": [u for u in need if u in cut],
                             "qualifiers": quals, "duplicates": len(hashes) - len(set(hashes)), "dropped": pk.dropped})
    return rows


def w_hash(retriever, uid: str) -> str:
    u = retriever.by_id.get(uid)
    return u["content_hash"] if u else uid


# ---- D / E · end to end -------------------------------------------------------------------------------------------------------
def entries_of(res: dict) -> dict[str, dict]:
    """The evidence ids the model saw -> unit id, rendered text, action (rebuilt from the recorded context)."""
    out = {}
    blocks = re.split(r"\n\n(?=\[E\d+\])", res["context_text"])
    texts = {}
    for b in blocks:
        m = re.match(r"\[(E\d+)\]", b)
        if m:
            texts[m.group(1)] = b
    for e in res["packed"]["entries"]:
        out[e["eid"]] = {"unit_id": e["unit_id"], "text": texts.get(e["eid"], ""), "action": e.get("action")}
    return out


def score_run(case: dict, res: dict, w, retriever) -> dict:
    req = request(case, w)
    ctx = [e["unit_id"] for e in res["packed"]["entries"]]
    audit = S.context_audit(case["case_id"], ctx, req.principal, w, retriever.by_id)
    out = {"context": audit, "qualifiers": S.qualifiers_in(case["case_id"], res["context_text"]),
           "needed_in_context": [u for u in S.needed(case["case_id"]) if u in ctx and
                                 not next((e for e in res["packed"]["entries"] if e["unit_id"] == u and e["truncated"]), None)]}
    if "raw_answer" in res:
        ent = entries_of(res)
        out["raw"] = S.score_answer(case["case_id"], res["raw_answer"], ent)
        out["final"] = S.score_answer(case["case_id"], res["final_answer"], ent)
        v = res["verdict"]
        out["verifier"] = {"material": v["material"], "supported": v["supported"], "citations": v["citations"],
                           "citations_valid": v["citations_valid"]}
    return out


def exp_d(cases: list[dict], retriever, w, model, seeds: list[int], arms: list[str], timings: list) -> list[dict]:
    rows = []
    for case in cases:
        req = request(case, w)
        for seed in seeds:
            for arm in arms:
                res, t = _strip(run(req, VARIANTS[arm], retriever, w, model, seed))
                gen = res.get("generation") or {}
                timings.append({"case_id": case["case_id"], "arm": arm, "seed": seed, "model": model.profile["model"], **t,
                                "usage": gen.get("usage"), "from_tape": gen.pop("from_tape", None)})
                res["split"], res["k_type"] = case["split"], case["k_type"]
                res["model"] = model.profile["model"] if model else None
                res["score"] = score_run(case, res, w, retriever)
                rows.append(res)
    return rows


def exp_e_evidence(cases: list[dict], retriever, w, variants: list[str]) -> list[dict]:
    """Every variant, evidence level only (no model): what reaches the model's context."""
    rows = []
    for case in cases:
        req = request(case, w)
        for name in variants:
            ctl = VARIANTS[name]
            res, _ = _strip(run(req, ctl, retriever, w, None, None))
            res["split"], res["k_type"] = case["split"], case["k_type"]
            res["score"] = score_run(case, res, w, retriever)
            rows.append({k: res[k] for k in ("case_id", "split", "k_type", "arm", "admitted", "packed", "conflicts", "gaps",
                                             "context_tokens_est", "score", "target_procedure_key")})
    return rows


# ---- invariants (deterministic, evidence level) ---------------------------------------------------------------------------
INVARIANTS = {
    "I1": "no unit the principal cannot read at as_of reaches the model's context",
    "I2": "no unit from another tenant reaches the model's context",
    "I3": "no labelled-invalid unit (superseded, withdrawn, draft, wrong scope, low-authority conflicting, poisoned, revoked) reaches the context",
    "I4": "on positive controls, every needed unit reaches the context",
    "I5": "every case with a genuine conflict surfaces it in the packet",
    "I6": "every needed qualifier of an admitted procedure reaches the context with it",
}


def invariants(rows: list[dict], arm: str) -> dict:
    r = [x for x in rows if x["arm"] == arm]
    fails: dict[str, list[str]] = {k: [] for k in INVARIANTS}
    for x in r:
        s = x["score"]
        if s["context"]["unauthorized"]:
            fails["I1"].append(x["case_id"])
        if s["context"]["cross_tenant"]:
            fails["I2"].append(x["case_id"])
        if s["context"]["invalid"]:
            fails["I3"].append(x["case_id"])
        if x["k_type"] == "P" and set(S.needed(x["case_id"])) - set(s["needed_in_context"]):
            fails["I4"].append(x["case_id"])
        if S.label(x["case_id"])["conflict"] and not x["conflicts"]:
            fails["I5"].append(x["case_id"])
        if not all(s["qualifiers"].values()):
            fails["I6"].append(x["case_id"])
    return {k: {"statement": INVARIANTS[k], "holds": not v, "failing_cases": v, "n": len(r)} for k, v in fails.items()}


def dumps(row: dict) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)


# ---- D2 · the citation verifier on labelled claim-citation pairs -------------------------------------------------------
JUDGE_SYSTEM = """You check whether cited evidence supports a claim made to an engineer. Each evidence block starts with a header
giving the document, its version, its source type, its status and its authority, and a line saying whether it is
admissible for this request (readable by the requester, current, in the right tenant and environment).
A claim is SUPPORTED only if: the cited evidence is admissible; it has authority for the kind of claim (a procedure comes
from a runbook of record or an owner runbook; an approval from those or the change policy; history from a ticket or
postmortem; a cause or fact from any admissible evidence); and, read literally, it establishes everything the claim
states, including numbers, versions, identifiers, conditions and negation. Answer in JSON: {"supported": true|false, "reason": "..."}"""
JUDGE_SCHEMA = {"type": "object", "properties": {"supported": {"type": "boolean"}, "reason": {"type": "string"}}, "required": ["supported", "reason"]}


def pair_entries(pair: dict, w, retriever) -> tuple[dict, list[dict]]:
    from knowledge_rag.pipeline import admissible_ids
    from knowledge_rag.query import QueryAnalysis
    p = w.idp.resolve(pair["principal"])
    req = G.Request(case_id=pair["id"], principal=p, tenant=p.tenant, environment=pair["environment"], question="",
                    as_of=w.as_of, budget=RCFG["budget"]["tokens"])
    qa = QueryAnalysis(question="", tenant=p.tenant, environment=pair["environment"], service=pair["service"],
                       tasks=["procedure", "history"])
    allrec = {r["record_id"]: (r, "deployments") for r in w.deployments.records}
    allrec |= {r["record_id"]: (r, "cmdb") for r in w.cmdb.records}
    cands, eid_of = [], {}
    for c in pair["citations"]:
        uid = c["unit_id"]
        if uid in eid_of:
            continue
        unit = retriever.by_id.get(uid)
        if unit is None and uid in allrec:
            unit = G.record_unit(*allrec[uid])
        if unit is None and "#" in uid:
            try:
                unit = next((u for u in G.source_units(w.sources.get(uid.split("#")[0])) if u["unit_id"] == uid), None)
            except KeyError:
                unit = None
        if unit is None:
            continue
        cand = G.Candidate(unit, "pair", len(cands) + 1)
        cands.append(cand)
        eid_of[uid] = f"E{len(cands)}"
    G.assign_roles(cands, req, pair["service"], w)
    adm = admissible_ids(cands, req, qa, w)
    entries = {}
    for c in cands:
        eid = eid_of[c.uid]
        entries[eid] = {"eid": eid, "unit_id": c.uid, "doc_key": c.unit["doc_key"], "role": c.role, "tier": c.tier,
                        "admissible": c.uid in adm, "action": c.unit["meta"].get("action"), "approval": c.unit["meta"].get("approval"),
                        "text": P.render_governed(eid, c)}
    claim = {"text": pair["claim"]["text"], "kind": pair["claim"]["kind"],
             "citations": [{"evidence_id": eid_of.get(c["unit_id"], "E99"), "quote": c["quote"]} for c in pair["citations"]]}
    return entries, [claim]


def exp_d2(pairs: list[dict], split: str, w, retriever, judge) -> list[dict]:
    from knowledge_rag.verify import verify_claim
    rows = []
    for pair in pairs:
        entries, (claim,) = pair_entries(pair, w, retriever)
        v = verify_claim(claim, entries, "")
        row = {"pair_id": pair["id"], "split": split, "category": pair["category"], "gold": pair["gold_supported"],
               "verifier": bool(v["supported"]), "verifier_problems": v["problems"]}
        if judge is not None:
            blocks = "\n\n".join(e["text"].replace("\n", f"\nadmissible for this request: {'yes' if e['admissible'] else 'no'}\n", 1)
                                 for e in entries.values())
            p = w.idp.resolve(pair["principal"])
            user = (f"REQUEST: {p.display} ({p.role}), tenant {p.tenant}, environment {pair['environment']}, service {pair['service']}, "
                    f"as of 2026-09-22T10:30:00Z\n\nCLAIM ({claim['kind']}): {claim['text']}\n\nQUOTES: " +
                    "; ".join(f"{c['evidence_id']}: \"{c['quote']}\"" for c in claim["citations"]) +
                    f"\n\nCITED EVIDENCE:\n{blocks or '(none of the cited ids exist)'}")
            out = judge.complete_raw([{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}],
                                     JUDGE_SCHEMA, judge.profile["seeds"][0])
            try:
                row["judge"] = bool(json.loads(out["content"])["supported"])
            except Exception:  # noqa: BLE001
                row["judge"] = None
            row["judge_key"] = out["key"]
        rows.append(row)
    return rows
