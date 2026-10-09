"""Rows -> facts.json: every measured value the editions may quote, each with the file and rule it came from.

    uv run python -m s2_eval.analysis runs/<id>

facts.json is deterministic given the rows (replay compares it byte for byte). Wall-clock latency comes from
timings.jsonl, which a replay cannot reproduce, so it goes to timing-facts.json instead and is never compared.
Hypothesis verdicts are computed here from the preregistered tests (experiments/preregistration.toml), as written.
"""

from __future__ import annotations

import json
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

from s2_eval import score as S

ARMS_D = {"naive": ("naive", "final"), "governed_raw": ("governed", "raw"), "governed": ("governed", "final")}


def rows(run: Path, name: str) -> list[dict]:
    p = run / name
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


class Facts:
    def __init__(self) -> None:
        self.d: dict[str, dict] = {}

    def put(self, key: str, value, source: str) -> None:
        if isinstance(value, float):
            value = round(value, 4)
        self.d[key] = {"value": value, "source": source}

    def v(self, key: str):
        return self.d[key]["value"]


def pct(a: int, b: int) -> float | None:
    return round(100 * a / b, 1) if b else None


def med(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return float(st.median(xs)) if xs else None


# ---- A ------------------------------------------------------------------------------------------------------------------
def facts_a(F: Facts, A: list[dict]) -> None:
    src = "a.jsonl"
    ret = [r for r in A if r["method"] != "structured-route"]
    with_need = [r for r in ret if r["needed"]]
    cases = sorted({r["case_id"] for r in with_need})
    F.put("a.cases", len(cases), f"{src}: cases with at least one needed index unit")
    F.put("a.needed_units", sum(len(r["needed"]) for r in with_need if r["method"] == "vector" and not r["prefilter"]), src)
    traps = sorted({r["case_id"] for r in ret if S.label(r["case_id"])["forbidden"]})
    F.put("a.trap_cases", len(traps), f"{src}: cases with at least one labelled-invalid unit")
    ident = sorted({r["case_id"] for r in ret if _identifier(r["case_id"]) and r["needed"]})
    F.put("a.ident.cases", len(ident), f"{src}: cases whose question names a version or a document id")
    for pf in (False, True):
        pre = "a.pf" if pf else "a"
        for m in ("vector", "bm25", "hybrid"):
            rs = [r for r in with_need if r["method"] == m and r["prefilter"] == pf]
            for k in (5, 10, 20):
                F.put(f"{pre}.{m}.recall{k}", 100 * st.mean(r[f"recall@{k}"] for r in rs), f"{src}: macro mean Recall@{k}, %")
                F.put(f"{pre}.{m}.full{k}", sum(r[f"full@{k}"] for r in rs), f"{src}: cases with every needed unit in the top {k}")
            F.put(f"{pre}.{m}.mrr10", f"{st.mean(r['rr@10'] for r in rs):.2f}", f"{src}: mean reciprocal rank of the first needed unit, top 10 (2 decimals)")
            F.put(f"{pre}.{m}.ndcg10", f"{st.mean(r['ndcg@10'] for r in rs):.2f}", f"{src}: mean nDCG@10, binary gains on needed units (2 decimals)")
            if not pf:
                ri = [r for r in rs if r["case_id"] in ident]
                F.put(f"a.ident.{m}.recall10", 100 * st.mean(r["recall@10"] for r in ri) if ri else None, f"{src}: identifier cases, macro Recall@10, %")
                F.put(f"a.ident.{m}.full10", sum(r["full@10"] for r in ri), f"{src}: identifier cases with every needed unit in the top 10")
                rt = [r for r in ret if r["method"] == m and not r["prefilter"] and r["case_id"] in traps]
                F.put(f"a.{m}.invalid_top5_cases", sum(1 for r in rt if r["invalid_top5"]), f"{src}: trap cases with a labelled-invalid unit in the top 5")
                F.put(f"a.{m}.invalid_top5_units", sum(len(r["invalid_top5"]) for r in rt), src)
    sr = [r for r in A if r["method"] == "structured-route" and r["records"]]
    F.put("a2.cases", len(sr), f"{src}: cases needing a structured record")
    F.put("a2.records", sum(len(r["records"]) for r in sr), src)
    F.put("a2.route", sum(len(r["route_returned"]) for r in sr), f"{src}: needed records the structured route returned")
    for m in ("vector", "bm25", "hybrid"):
        F.put(f"a2.prose.{m}", sum(len(r["prose_has_fields"][m]) for r in sr), f"{src}: needed records whose exact fields appear together in one top-20 prose unit")


def _identifier(case_id: str) -> bool:
    import re
    from s2_eval.common import load_cases
    q = {c["case_id"]: c["question"] for c in load_cases("all")}[case_id]
    return bool(re.search(r"(?<![\w.])\d+\.\d+\.\d+(?![\w.])|\b[A-Z]{2,}(?:-[A-Z0-9.]+)+-\d+\b", q))


# ---- B ------------------------------------------------------------------------------------------------------------------
def facts_b(F: Facts, B: list[dict]) -> None:
    src = "b.jsonl"
    cases = sorted({r["case_id"] for r in B})
    F.put("b.cases", len(cases), src)
    gov = {r["case_id"]: r for r in B if r["arm"] == "governed"}
    nai = {r["case_id"]: r for r in B if r["arm"] == "naive"}
    pool_inv = [c for c in cases if nai[c]["pool_audit"]["invalid"]]
    F.put("b.pool_invalid_cases", len(pool_inv), f"{src}: cases whose frozen top-20 pool holds a labelled-invalid unit")
    F.put("b.pool_invalid_units", sum(nai[c]["pool_audit"]["invalid"] for c in cases), src)
    F.put("b.pool_unauthorized_units", sum(nai[c]["pool_audit"]["unauthorized"] for c in cases), src)
    for arm, rs in (("naive", nai), ("governed", gov)):
        F.put(f"b.{arm}.invalid_units", sum(r["ctx_invalid"] for r in rs.values()), f"{src}: labelled-invalid units in the packed context")
        F.put(f"b.{arm}.invalid_cases", sum(1 for r in rs.values() if r["ctx_invalid"]), src)
        F.put(f"b.{arm}.unauthorized_units", sum(r["ctx_unauthorized"] for r in rs.values()), f"{src}: units the principal cannot read at as_of")
        F.put(f"b.{arm}.cross_tenant_units", sum(r["ctx_cross_tenant"] for r in rs.values()), src)
        F.put(f"b.{arm}.tokens_median", med([r["tokens"] for r in rs.values()]), src)
        classes = defaultdict(int)
        for r in rs.values():
            for k, v in r["ctx_invalid_by_class"].items():
                classes[k] += v
        for k in ("unauthorized", "revoked-acl", "wrong-tenant", "wrong-environment", "wrong-service", "wrong-document", "superseded",
                  "withdrawn", "draft", "stale-copy", "low-authority-conflicting", "poisoned"):
            F.put(f"b.{arm}.class.{k}", classes.get(k, 0), src)
        F.put(f"b.{arm}.needed_in_context", sum(len(r["needed_in_context"]) for r in rs.values()), src)
    F.put("b.needed_in_pool", sum(len(r["needed_in_pool"]) for r in gov.values()), f"{src}: needed units present in the frozen pool")
    F.put("b.governed.needed_admitted", sum(len(r["needed_admitted"]) for r in gov.values()), src)
    conf = [c for c in cases if gov[c]["conflict_expected"]]
    F.put("b.conflict_cases", len(conf), src)
    F.put("b.governed.conflicts_found", sum(1 for c in conf if gov[c]["conflicts"]), src)
    F.put("b.governed.false_conflicts", sum(1 for c in cases if gov[c]["conflicts"] and not gov[c]["conflict_expected"]), src)
    for gate in ("authorization", "scope", "lifecycle", "authority", "conflict"):
        F.put(f"b.governed.excluded.{gate}", sum(1 for r in gov.values() for x in r["excluded"] if x["gate"] == gate),
              f"{src}: units the governed gates excluded from the frozen pools, by gate")
    pos = [c for c in cases if c.split("-")[1].startswith("P")]
    F.put("b.pos.cases", len(pos), src)
    F.put("b.pos.governed_ok", sum(1 for c in pos if set(gov[c]["needed_in_pool"]) <= set(gov[c]["needed_in_context"])), src)


# ---- C ------------------------------------------------------------------------------------------------------------------
def facts_c(F: Facts, C: list[dict]) -> None:
    src = "c.jsonl"
    for b in sorted({r["budget"] for r in C}):
        rb = [r for r in C if r["budget"] == b]
        any_m = [r for r in rb if r["method"] == "truncate"]
        F.put(f"c.{b}.needed_in_pool", sum(len(r["needed_in_pool"]) for r in any_m), src)
        qcases = [r for r in any_m if r["qualifiers"]]
        F.put(f"c.qual_cases", len(qcases), f"{src}: cases with a labelled qualifier")
        F.put(f"c.qual_total", sum(len(r["qualifiers"]) for r in any_m), src)
        for m in ("truncate", "assembler"):
            rm = [r for r in rb if r["method"] == m]
            F.put(f"c.{b}.{m}.needed_covered", sum(len(r["needed_covered"]) for r in rm), f"{src}: needed units fully present in the context")
            F.put(f"c.{b}.{m}.needed_cut", sum(len(r["needed_cut"]) for r in rm), f"{src}: needed units cut mid-text")
            F.put(f"c.{b}.{m}.qual_retained", sum(sum(r["qualifiers"].values()) for r in rm), src)
            F.put(f"c.{b}.{m}.qual_cases_ok", sum(1 for r in rm if r["qualifiers"] and all(r["qualifiers"].values())), src)
            F.put(f"c.{b}.{m}.tokens_median", med([r["tokens"] for r in rm]), src)
            F.put(f"c.{b}.{m}.truncated_units", sum(len(r["context_truncated"]) for r in rm), src)
            F.put(f"c.{b}.{m}.duplicates", sum(r["duplicates"] for r in rm), src)
            F.put(f"c.{b}.{m}.cases_all_needed", sum(1 for r in rm if set(r["needed_in_pool"]) <= set(r["needed_covered"])), src)


# ---- D / E ---------------------------------------------------------------------------------------------------------------
def d_metrics(rs: list[dict], which: str) -> dict:
    sc = [r["score"][which] for r in rs]
    abst = [s for s in sc if not s["answerable"]]
    ans = [s for s in sc if s["answerable"]]
    withf = [s for s in sc if s["complete"] is not None]
    acts = [s for s in sc if s["recommendation_grounded"] is not None]
    out = {"runs": len(sc), "correct": sum(s["correct"] for s in sc), "complete": sum(1 for s in withf if s["complete"]),
           "facts_runs": len(withf), "abst_runs": len(abst), "abst_ok": sum(1 for s in abst if s["status_ok"] and s["action_ok"]),
           "answerable_runs": len(ans), "false_abst": sum(1 for s in ans if s["false_abstention"]),
           "leak_runs": sum(1 for s in sc if s["leaks"]), "forbidden_action_runs": sum(1 for s in sc if s["forbidden_action"]),
           "cit_total": sum(s["citations"] for s in sc), "cit_valid": sum(s["citations_valid"] for s in sc),
           "invalid_support": sum(s["invalid_support_citations"] for s in sc),
           "action_runs": len(acts), "grounded": sum(1 for s in acts if s["recommendation_grounded"]),
           "status_ok": sum(s["status_ok"] for s in sc), "action_ok": sum(s["action_ok"] for s in sc),
           "approval_ok": sum(s["approval_ok"] for s in sc)}
    out["cit_precision_pct"] = pct(out["cit_valid"], out["cit_total"])
    return out


def facts_d(F: Facts, D: list[dict], pre: str, src: str) -> None:
    if not D:
        return
    for arm, (row_arm, which) in ARMS_D.items():
        rs = [r for r in D if r["arm"] == row_arm]
        m = d_metrics(rs, which)
        for k, v in m.items():
            F.put(f"{pre}.{arm}.{k}", v, f"{src}: arm {row_arm}, {which} answer")
        F.put(f"{pre}.{arm}.ctx_unauthorized_runs", sum(1 for r in rs if r["score"]["context"]["unauthorized"]), src)
        F.put(f"{pre}.{arm}.ctx_invalid_runs", sum(1 for r in rs if r["score"]["context"]["invalid"]), src)
        F.put(f"{pre}.{arm}.parse_errors", sum(1 for r in rs if (r.get("generation") or {}).get("parse_error")), src)
        F.put(f"{pre}.{arm}.model_calls", sum(1 for r in rs if (r.get("generation") or {}).get("key")), src)
        F.put(f"{pre}.{arm}.prompt_tokens_median", med([((r.get("generation") or {}).get("usage") or {}).get("prompt_eval_count") for r in rs]),
              f"{src}: the model server's prompt token count, median")
        F.put(f"{pre}.{arm}.context_tokens_est_median", med([r["context_tokens_est"] for r in rs]), src)
        mat = sum(r["score"]["verifier"]["material"] for r in rs)
        sup = sum(r["score"]["verifier"]["supported"] for r in rs)
        F.put(f"{pre}.{arm}.verifier_material", mat, src)
        F.put(f"{pre}.{arm}.verifier_supported", sup, src)
        F.put(f"{pre}.{arm}.verifier_supported_pct", pct(sup, mat), src)
        by_case = defaultdict(list)
        for r in rs:
            by_case[r["case_id"]].append(r["score"][which]["correct"])
        F.put(f"{pre}.{arm}.cases_majority_correct", sum(1 for v in by_case.values() if sum(v) * 2 > len(v)), src)
        F.put(f"{pre}.{arm}.cases_all_correct", sum(1 for v in by_case.values() if all(v)), src)
        for cid, v in sorted(by_case.items()):
            F.put(f"{pre}.case.{cid}.{arm}", sum(v), src)
        k13 = [r for r in rs if r["k_type"] == "K13"]
        F.put(f"{pre}.k13.{arm}.forbidden_action", sum(1 for r in k13 if r["score"][which]["forbidden_action"]), src)
        F.put(f"{pre}.k13.{arm}.runs", len(k13), src)
    F.put(f"{pre}.cases", len({r["case_id"] for r in D}), src)
    F.put(f"{pre}.seeds", len({r["seed"] for r in D}), src)
    gov = [r for r in D if r["arm"] == "governed"]
    F.put(f"{pre}.governed.binding_changed", sum(1 for r in gov if r["binding_notes"]), f"{src}: governed runs where binding changed the raw answer")
    F.put(f"{pre}.governed.no_model_call", sum(1 for r in gov if (r.get("generation") or {}).get("skipped")), f"{src}: governed runs with no admissible evidence (model not called)")
    F.put(f"{pre}.governed.binding_rescued", sum(1 for r in gov if r["score"]["final"]["correct"] and not r["score"]["raw"]["correct"]), src)
    F.put(f"{pre}.governed.binding_broke", sum(1 for r in gov if r["score"]["raw"]["correct"] and not r["score"]["final"]["correct"]), src)


FLAGSHIP = {"heldout": "H-K9", "dev": "D-K9"}


def facts_flagship(F: Facts, D: list[dict], split: str) -> None:
    """The flagship case (INC-4917 on held-out), first seed: what each arm put in front of the model, and what it answered."""
    cid = FLAGSHIP.get(split)
    rs = [r for r in D if r["case_id"] == cid]
    if not rs:
        return
    seed = min(r["seed"] for r in rs)
    src = f"d.jsonl: {cid}, seed {seed}"
    F.put("flag.case", cid, src)
    F.put("flag.seed", seed, src)
    for arm, key in (("naive", "naive"), ("governed", "gov")):
        r = next(x for x in rs if x["arm"] == arm and x["seed"] == seed)
        units = [e["unit_id"] for e in r["packed"]["entries"]]
        need = set(S.needed(cid))
        F.put(f"flag.{key}.units", [f"{u}|{S.forbidden_class(cid, u) or ''}|{'cut' if e['truncated'] else ''}|{'needed' if u in need else ''}"
                                    for u, e in zip(units, r["packed"]["entries"])], src)
        F.put(f"flag.{key}.invalid", r["score"]["context"]["invalid"], src)
        F.put(f"flag.{key}.unauthorized", r["score"]["context"]["unauthorized"], src)
        a = r["final_answer"]
        ra = a["recommended_action"]
        F.put(f"flag.{key}.status", a["status"], src)
        F.put(f"flag.{key}.action", ra["action"], src)
        F.put(f"flag.{key}.target", ra.get("target", ""), src)
        F.put(f"flag.{key}.approval", bool(ra.get("approval_required")), src)
        F.put(f"flag.{key}.correct", r["score"]["final"]["correct"], src)
        s = r["score"]["final"]
        failed = [lab for ok, lab in ((s["status_ok"], "status"), (s["action_ok"], "action"), (s["approval_ok"], "approval"),
                                      (s["target_ok"], "target"), (not s["leaks"], "leak")) if not ok]
        F.put(f"flag.{key}.failed", ", ".join(failed) or "none", f"{src}: the checks of the correctness rule that failed")
        F.put(f"flag.{key}.needed_in_context", sum(1 for u in units if u in need), src)
        F.put(f"flag.needed_total", len(need), src)
        F.put(f"flag.{key}.summary", a.get("summary", ""), src)
        F.put(f"flag.{key}.tokens", r["context_tokens_est"], src)
        if arm == "governed":
            F.put("flag.gov.raw_action", r["raw_answer"]["recommended_action"]["action"], src)
            F.put("flag.gov.binding_notes", r["binding_notes"], src)
    nr = [x for x in rs if x["arm"] == "naive"]
    gr = [x for x in rs if x["arm"] == "governed"]
    F.put("flag.naive.correct_runs", sum(x["score"]["final"]["correct"] for x in nr), f"d.jsonl: {cid}, all seeds")
    F.put("flag.gov.correct_runs", sum(x["score"]["final"]["correct"] for x in gr), f"d.jsonl: {cid}, all seeds")
    F.put("flag.runs", len(nr), f"d.jsonl: {cid}, all seeds")


def facts_d2(F: Facts, D2: list[dict]) -> None:
    src = "d2.jsonl"
    for sp in ("dev", "heldout"):
        rs = [r for r in D2 if r["split"] == sp]
        F.put(f"d2.{sp}.pairs", len(rs), src)
        F.put(f"d2.{sp}.gold_supported", sum(r["gold"] for r in rs), src)
        for m in ("verifier", "judge"):
            got = [r for r in rs if r.get(m) is not None]
            F.put(f"d2.{sp}.{m}.n", len(got), src)
            F.put(f"d2.{sp}.{m}.agree", sum(1 for r in got if r[m] == r["gold"]), src)
            F.put(f"d2.{sp}.{m}.false_support", sum(1 for r in got if r[m] and not r["gold"]), f"{src}: said supported, gold unsupported")
            F.put(f"d2.{sp}.{m}.false_reject", sum(1 for r in got if not r[m] and r["gold"]), f"{src}: said unsupported, gold supported")
            F.put(f"d2.{sp}.{m}.agree_pct", pct(sum(1 for r in got if r[m] == r["gold"]), len(got)), src)
            for cat in sorted({r["category"] for r in rs}):
                rc = [r for r in got if r["category"] == cat]
                F.put(f"d2.{sp}.{m}.cat.{cat}", sum(1 for r in rc if r[m] == r["gold"]), src)
        for cat in sorted({r["category"] for r in rs}):
            F.put(f"d2.{sp}.cat.{cat}.n", sum(1 for r in rs if r["category"] == cat), src)


def facts_e(F: Facts, E: list[dict], EL: list[dict], INV: dict) -> None:
    src = "e_evidence.jsonl"
    for v in sorted({r["arm"] for r in E}):
        rs = [r for r in E if r["arm"] == v]
        F.put(f"e.{v}.invalid_units", sum(r["score"]["context"]["invalid"] for r in rs), src)
        F.put(f"e.{v}.invalid_cases", sum(1 for r in rs if r["score"]["context"]["invalid"]), src)
        F.put(f"e.{v}.unauthorized_units", sum(r["score"]["context"]["unauthorized"] for r in rs), src)
        F.put(f"e.{v}.cross_tenant_units", sum(r["score"]["context"]["cross_tenant"] for r in rs), src)
        F.put(f"e.{v}.needed_in_context", sum(len(r["score"]["needed_in_context"]) for r in rs), src)
        F.put(f"e.{v}.qual_cases_ok", sum(1 for r in rs if r["score"]["qualifiers"] and all(r["score"]["qualifiers"].values())), src)
        F.put(f"e.{v}.conflicts_found", sum(1 for r in rs if S.label(r["case_id"])["conflict"] and r["conflicts"]), src)
        F.put(f"e.{v}.tokens_median", med([r["context_tokens_est"] for r in rs]), src)
        for cls in ("unauthorized", "revoked-acl", "wrong-tenant", "wrong-environment", "superseded", "superseded-at-source", "withdrawn",
                    "draft", "low-authority-conflicting", "poisoned", "wrong-service", "wrong-document", "stale-copy"):
            F.put(f"e.{v}.class.{cls}", sum(r["score"]["context"]["invalid_by_class"].get(cls, 0) for r in rs), src)
    if E:
        any_v = [r for r in E if r["arm"] == "governed"]
        F.put("e.needed_total", sum(len(S.needed(r["case_id"])) for r in any_v), src)
        F.put("e.qual_cases", sum(1 for r in any_v if r["score"]["qualifiers"]), src)
        F.put("e.conflict_cases", sum(1 for r in any_v if S.label(r["case_id"])["conflict"]), src)
        F.put("e.cases", len(any_v), src)
    for v in sorted({r["arm"] for r in EL}):
        m = d_metrics([r for r in EL if r["arm"] == v], "final")
        for k in ("runs", "correct", "abst_ok", "abst_runs", "false_abst", "answerable_runs", "leak_runs", "forbidden_action_runs",
                  "cit_precision_pct", "invalid_support"):
            F.put(f"el.{v}.{k}", m[k], "e_live.jsonl")
    for arm, inv in (INV or {}).items():
        for k, x in inv.items():
            F.put(f"inv.{arm}.{k}", "HOLDS" if x["holds"] else "FAILS", "invariants.json")
            F.put(f"inv.{arm}.{k}.failing", ", ".join(x["failing_cases"]) or "none", "invariants.json")
        F.put(f"inv.{arm}.holding", sum(1 for x in inv.values() if x["holds"]), "invariants.json")
        F.put(f"inv.{arm}.total", len(inv), "invariants.json")


def write(run: Path) -> dict:
    F = Facts()
    m = json.loads((run / "manifest.json").read_text()) if (run / "manifest.json").exists() else {}
    F.put("run.id", m.get("run_id", run.name), "manifest.json (a replay keeps the id of the run it replays)")
    F.put("run.split", m.get("split"), "manifest.json")
    F.put("run.mode", m.get("mode"), "manifest.json")
    F.put("run.model", m.get("models", {}).get("primary", {}).get("model"), "manifest.json")
    F.put("run.sens_model", m.get("models", {}).get("sensitivity", {}).get("model"), "manifest.json")
    F.put("run.judge_model", m.get("models", {}).get("judge", {}).get("model"), "manifest.json")
    facts_a(F, rows(run, "a.jsonl")) if (run / "a.jsonl").exists() else None
    facts_b(F, rows(run, "b.jsonl")) if (run / "b.jsonl").exists() else None
    facts_c(F, rows(run, "c.jsonl")) if (run / "c.jsonl").exists() else None
    facts_d(F, rows(run, "d.jsonl"), "d", "d.jsonl")
    facts_d(F, rows(run, "d_sensitivity.jsonl"), "ds", "d_sensitivity.jsonl")
    facts_flagship(F, rows(run, "d.jsonl"), m.get("split"))
    facts_d2(F, rows(run, "d2.jsonl")) if (run / "d2.jsonl").exists() else None
    inv = json.loads((run / "invariants.json").read_text()) if (run / "invariants.json").exists() else {}
    facts_e(F, rows(run, "e_evidence.jsonl"), rows(run, "e_live.jsonl"), inv)
    # the end-to-end ablations ran on one seed; the governed and naive baselines on that same seed come from d.jsonl
    seed = m.get("models", {}).get("ablation_seed")
    if seed is None:
        from knowledge_rag.util import load_yaml, ROOT as POCROOT
        seed = load_yaml(POCROOT / "config" / "models.yaml")["ablation_seed"]
    D = rows(run, "d.jsonl")
    for arm in ("governed", "naive"):
        ms = d_metrics([r for r in D if r["arm"] == arm and r["seed"] == seed], "final")
        for k in ("runs", "correct", "abst_ok", "abst_runs", "false_abst", "answerable_runs", "leak_runs", "forbidden_action_runs",
                  "cit_precision_pct", "invalid_support"):
            F.put(f"el.{arm}.{k}", ms[k], f"d.jsonl: arm {arm}, seed {seed} (the ablation seed), bound answer")
    F.put("el.seed", seed, "config/models.yaml ablation_seed")
    from s2_eval.hypotheses import verdicts
    vs = verdicts(F)
    for k, v in vs.items():
        F.put(k, v, "experiments/preregistration.toml tests applied to facts.json")
    vs = {k: v for k, v in vs.items() if re.fullmatch(r"H\d+", k)}
    for label in ("SUPPORTED", "NOT SUPPORTED", "NOT TESTED"):
        F.put(f"hyp.{label.lower().replace(' ', '_')}", sum(1 for v in vs.values() if v == label), "count of the verdicts above")
        F.put(f"hyp.{label.lower().replace(' ', '_')}.list", ", ".join(k for k, v in vs.items() if v == label) or "none", "the verdicts above")
    F.put("hyp.total", len(vs), "experiments/preregistration.toml")
    (run / "facts.json").write_text(json.dumps(F.d, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    timing_facts(run)
    return F.d


def timing_facts(run: Path) -> None:
    T = rows(run, "timings.jsonl")
    out = {}
    prim = json.loads((run / "manifest.json").read_text()).get("models", {}).get("primary", {}).get("model")
    for arm in sorted({t["arm"] for t in T}):
        tt = [t for t in T if t["arm"] == arm and t.get("model") == prim]
        if not tt:
            continue
        live = [t for t in tt if t.get("from_tape") is False]
        out[arm] = {"n": len(tt), "retrieve_ms_median": med([t["retrieve"] for t in tt]), "govern_ms_median": med([t["govern"] for t in tt]),
                    "pack_ms_median": med([t["pack"] for t in tt]), "verify_ms_median": med([t["verify"] for t in tt]),
                    "generate_s_median_live_calls": (med([t["generate"] for t in live]) or 0) / 1000 if live else None,
                    "live_calls": len(live),
                    "model_server_s_median": med([(t.get("usage") or {}).get("total_duration_ns") and t["usage"]["total_duration_ns"] / 1e9 for t in tt])}
    (run / "timing-facts.json").write_text(json.dumps({"note": "wall-clock on one machine, serial; not replayable, never compared", "arms": out},
                                                     indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    d = write(Path(sys.argv[1]))
    print(f"{len(d)} facts")
