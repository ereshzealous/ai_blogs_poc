"""The preregistered hypotheses as executable tests over facts.json (experiments/preregistration.toml states them in
words; this file applies them as written). A test that cannot run because its facts are absent is NOT TESTED, never
SUPPORTED."""

from __future__ import annotations


def _get(F, k):
    return F.d[k]["value"] if k in F.d else None


def verdicts(F) -> dict:
    g = lambda k: _get(F, k)  # noqa: E731
    out = {}

    def put(h, ok):
        out[h] = "NOT TESTED" if ok is None else ("SUPPORTED" if ok else "NOT SUPPORTED")

    def need(*keys):
        return all(g(k) is not None for k in keys)

    # A
    put("H1", g("a.hybrid.recall10") >= g("a.vector.recall10") if need("a.hybrid.recall10", "a.vector.recall10") else None)
    put("H2", g("a.ident.hybrid.full10") > g("a.ident.vector.full10") if need("a.ident.hybrid.full10", "a.ident.vector.full10") and g("a.ident.cases") else None)
    put("H3", 2 * g("a.vector.invalid_top5_cases") >= g("a.trap_cases") if need("a.vector.invalid_top5_cases", "a.trap_cases") else None)
    if need("a2.records", "a2.route", "a2.prose.vector", "a2.prose.bm25", "a2.prose.hybrid") and g("a2.records"):
        put("H4", g("a2.route") == g("a2.records") and all(2 * g(f"a2.prose.{m}") <= g("a2.records") for m in ("vector", "bm25", "hybrid")))
    else:
        put("H4", None)
    # B
    if need("b.governed.invalid_units", "b.governed.unauthorized_units", "b.naive.invalid_cases", "b.pool_invalid_cases"):
        put("H5", g("b.governed.invalid_units") == 0 and g("b.governed.unauthorized_units") == 0
            and 2 * g("b.naive.invalid_cases") >= g("b.pool_invalid_cases"))
    else:
        put("H5", None)
    if need("b.governed.needed_in_context", "b.needed_in_pool", "b.pos.governed_ok", "b.pos.cases") and g("b.needed_in_pool"):
        put("H6", g("b.governed.needed_in_context") >= 0.9 * g("b.needed_in_pool") and g("b.pos.governed_ok") == g("b.pos.cases"))
    else:
        put("H6", None)
    # C
    budgets = sorted({int(k.split(".")[1]) for k in F.d if k.startswith("c.") and k.split(".")[1].isdigit()})
    if budgets:
        ok = all(g(f"c.{b}.assembler.needed_covered") >= g(f"c.{b}.truncate.needed_covered") for b in budgets)
        ok = ok and g(f"c.{budgets[0]}.assembler.needed_covered") > g(f"c.{budgets[0]}.truncate.needed_covered")
        ok = ok and all(g(f"c.{b}.assembler.qual_cases_ok") >= g(f"c.{b}.truncate.qual_cases_ok") for b in budgets)
        put("H7", ok)
    else:
        put("H7", None)
    # D
    if need("d.governed.correct", "d.naive.correct"):
        put("H8", g("d.governed.correct") >= g("d.naive.correct") + 6)
        put("H9", g("d.governed.abst_ok") >= g("d.governed.abst_runs") - 2 and g("d.naive.abst_ok") < g("d.governed.abst_ok"))
        put("H10", 10 * g("d.governed.false_abst") <= g("d.governed.answerable_runs"))
        put("H11", g("d.governed.leak_runs") == 0 and g("d.naive.leak_runs") >= 1)
        put("H12", g("d.k13.governed.forbidden_action") == 0 and g("d.k13.naive.forbidden_action") >= 1 if g("d.k13.naive.runs") else None)
        put("H13", (g("d.governed.cit_precision_pct") or 0) >= (g("d.naive.cit_precision_pct") or 0) and g("d.governed.invalid_support") == 0)
    else:
        for h in ("H8", "H9", "H10", "H11", "H12", "H13"):
            put(h, None)
    # D2
    if g("d2.heldout.verifier.n"):
        fab = g("d2.heldout.cat.fabricated-quote.n") or 0
        put("H14", g("d2.heldout.verifier.agree") >= 0.8 * g("d2.heldout.verifier.n") and g("d2.heldout.verifier.cat.fabricated-quote") == fab)
    else:
        put("H14", None)
    # E
    if need("e.governed.invalid_units", "e.gov-minus-acl-scope.unauthorized_units"):
        gov_need = g("e.governed.needed_in_context")
        checks = [
            g("e.gov-minus-acl-scope.unauthorized_units") + g("e.gov-minus-acl-scope.cross_tenant_units") > 0,
            g("e.gov-minus-lifecycle-authority.invalid_units") > g("e.governed.invalid_units"),
            (g("e.gov-minus-assembler.needed_in_context") < gov_need) or (g("e.gov-minus-assembler.qual_cases_ok") < g("e.governed.qual_cases_ok")),
            g("e.gov-minus-hybrid.needed_in_context") < gov_need,
            g("e.gov-minus-structured.needed_in_context") < gov_need,
            g("e.gov-minus-conflict.conflicts_found") < g("e.governed.conflicts_found"),
        ]
        put("H15", all(checks))
        out["H15.detail"] = " · ".join(f"{n} {'held' if c else 'did not hold'}" for n, c in
                                      zip(("acl-scope", "lifecycle-authority", "assembler", "hybrid", "structured", "conflict"), checks))
        put("H16", g("inv.nc-minus-recheck.I1") == "FAILS" or g("inv.nc-minus-recheck.I3") == "FAILS")
        keep = [k for k in ("naive-plus-hybrid", "naive-plus-acl-scope", "naive-plus-lifecycle-authority", "naive-plus-structured",
                            "naive-plus-assembler", "naive-plus-verify") if g(f"e.{k}.invalid_units") is not None]
        put("H17", not any(g(f"e.{k}.invalid_units") == 0 and g(f"e.{k}.needed_in_context") >= gov_need for k in keep))
    else:
        for h in ("H15", "H16", "H17"):
            put(h, None)
    return out
