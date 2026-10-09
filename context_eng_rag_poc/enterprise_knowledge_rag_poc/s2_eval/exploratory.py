"""POST-HOC, EXPLORATORY, NOT PREREGISTERED. Written after the held-out run exposed two defects in the frozen assembler.
Nothing here changes the system that ran, and no number from this module enters a headline: it answers "what would the
fix buy?" on experiment C's admitted pools, and the editions label it exactly that.

Defects observed in the recorded C rows (runs/2026-10-08-heldout/c.jsonl):
  1. A qualifier binds to whichever section of its document ranks first. When "Symptoms" ranks above "Remediation",
     the approval section rides with Symptoms and the remediation becomes a second item that loses the budget race
     (H-K5, H-K13 at 450 and 600 tokens).
  2. Breadth first by role ranks generic roles (policy, CMDB, release records) above history that the authority policy
     admitted precisely because the question needed it (H-P1's root cause, H-K12's interim guidance).

Variant v2 fixes exactly those two things (it did not help). Variant v3, a second post-hoc attempt, drops role
priorities altogether: compact system-of-record facts first, then whole items in relevance order, qualifiers bound to
their document's primary section. v2's fixes:
  1. qualifiers bind to the document's primary procedure section: the one that names the document's front-matter action
     affirmatively, else its best-ranked non-qualifier section; that section leads the item;
  2. admitted history gets the priority right after the question's procedure (it is only admitted when it is needed).

    uv run python -m s2_eval.exploratory <run-id>     # -> runs/<run>-exploratory/c_assembler_variants.jsonl + summary

A second post-hoc check, found while reading the held-out D rows: the model writes typographic characters (U+2011
non-breaking hyphen, U+202F narrow no-break space) that the frozen scorer's fact regexes and canary match do not fold
(the verifier's quote match does). "incident‑commander" misses "incident[- ]commander"; a canary written with U+2011 would
be missed too. `rescore_typography` re-scores every recorded answer with those characters folded to ASCII and reports
what changes. It never rewrites a rows file or facts.json.
"""

from __future__ import annotations

import json
import sys

from knowledge_rag import packer as P
from knowledge_rag.pipeline import GOVERNED, govern, prelude, retrieve_candidates
from knowledge_rag.query import analyze_query
from knowledge_rag.util import ROOT, est_tokens
from knowledge_rag.verify import action_mentions
from s2_eval import score as S
from s2_eval.common import RCFG, load_cases, request, retriever, world


def _primary(sections):
    for c in sections:
        act = c.unit["meta"].get("action")
        if act and any(a == act and not neg for a, neg in action_mentions(c.unit["text"])):
            return c
    return sections[0]


def _priority_v2(c, tasks, target_key):
    m = c.unit["meta"]
    if c.role == "procedure" and target_key and m["procedure_key"] == target_key:
        return 0
    if c.role == "history":
        return 1
    return {"change_fact": 2, "approval": 3, "ownership": 4}.get(c.role, 5 if c.role == "procedure" else 7)


def assembler_v2(cands, budget, tasks, target_key, prelude_text=""):
    p = P.Packed("assembler-v2", budget, "")
    order = {id(c): i for i, c in enumerate(cands)}
    by_doc: dict[str, list] = {}
    for c in cands:
        by_doc.setdefault(c.unit["doc_key"], []).append(c)
    items, used = [], set()
    for c in cands:
        if id(c) in used:
            continue
        group = by_doc[c.unit["doc_key"]]
        quals = [x for x in group if x.unit.get("qualifier")]
        main = [x for x in group if not x.unit.get("qualifier")]
        if c.unit.get("qualifier") and main:
            continue                                   # placed with its primary section
        if not c.unit.get("qualifier") and quals and c is _primary(main):
            item = [c] + sorted([q for q in quals if id(q) not in used], key=lambda x: x.unit.get("section_index", 0))
        else:
            item = [c]
        used |= {id(x) for x in item}
        items.append(item)
    for c in cands:                                    # qualifiers whose document had no admitted main section
        if id(c) not in used:
            used.add(id(c))
            items.append([c])
    seen, uniq = set(), []
    for it in items:
        h = tuple(x.unit.get("content_hash") or x.uid for x in it)
        if h not in seen:
            seen.add(h)
            uniq.append(it)
    nth, keyed = {}, []
    for it in sorted(uniq, key=lambda it: (_priority_v2(it[0], tasks, target_key), order[id(it[0])])):
        pr = _priority_v2(it[0], tasks, target_key)
        keyed.append((nth.get(pr, 0), pr, order[id(it[0])], it))
        nth[pr] = nth.get(pr, 0) + 1
    parts, n = ([prelude_text] if prelude_text else []), 0
    for _, _, _, it in sorted(keyed, key=lambda k: k[:3]):
        blocks = [P.render_governed(f"E{n + 1 + j}", x) for j, x in enumerate(it)]
        if est_tokens(P._join(parts + blocks)) > budget and it[0].unit["doc_type"] in ("deployment", "cmdb"):
            blocks = [P.render_governed(f"E{n + 1}", it[0], compact=True)]
        if est_tokens(P._join(parts + blocks)) <= budget:
            for j, (x, b) in enumerate(zip(it, blocks)):
                parts.append(b)
                p.entries.append(P._entry(f"E{n + 1 + j}", x, b, est_tokens(b), False))
            n += len(blocks)
        else:
            p.dropped.extend({"unit_id": x.uid, "reason": "does not fit"} for x in it)
    p.text = P._join(parts)
    p.used_tokens = est_tokens(p.text)
    return p


def assembler_v3(cands, budget, tasks, target_key, prelude_text=""):
    """Second post-hoc attempt: compact system-of-record facts first, then whole items in RELEVANCE order (the order the
    candidates arrived in), qualifiers bound to their document's primary procedure section. No role priorities."""
    p = P.Packed("assembler-v3", budget, "")
    recs = [c for c in cands if c.unit["doc_type"] in ("deployment", "cmdb")]
    prose = [c for c in cands if c.unit["doc_type"] not in ("deployment", "cmdb")]
    by_doc: dict[str, list] = {}
    for c in prose:
        by_doc.setdefault(c.unit["doc_key"], []).append(c)
    items, used = [], set()
    for c in prose:
        if id(c) in used:
            continue
        group = by_doc[c.unit["doc_key"]]
        quals = [x for x in group if x.unit.get("qualifier")]
        main = [x for x in group if not x.unit.get("qualifier")]
        if c.unit.get("qualifier") and main:
            prim = _primary(main)
            item = [prim] + sorted([q for q in quals if id(q) not in used], key=lambda x: x.unit.get("section_index", 0))
        elif not c.unit.get("qualifier") and quals and c is _primary(main):
            item = [c] + sorted([q for q in quals if id(q) not in used], key=lambda x: x.unit.get("section_index", 0))
        else:
            item = [c]
        item = [x for x in item if id(x) not in used]
        used |= {id(x) for x in item}
        if item:
            items.append(item)
    seen, uniq = set(), []
    for it in items:
        h = tuple(x.unit.get("content_hash") or x.uid for x in it)
        if h not in seen:
            seen.add(h)
            uniq.append(it)
    parts, n = ([prelude_text] if prelude_text else []), 0
    for c in recs:
        b = P.render_governed(f"E{n + 1}", c, compact=True)
        if est_tokens(P._join(parts + [b])) <= budget:
            parts.append(b)
            p.entries.append(P._entry(f"E{n + 1}", c, b, est_tokens(b), False))
            n += 1
    for it in uniq:
        blocks = [P.render_governed(f"E{n + 1 + j}", x) for j, x in enumerate(it)]
        if est_tokens(P._join(parts + blocks)) <= budget:
            for j, (x, b) in enumerate(zip(it, blocks)):
                parts.append(b)
                p.entries.append(P._entry(f"E{n + 1 + j}", x, b, est_tokens(b), False))
            n += len(blocks)
        else:
            p.dropped.extend({"unit_id": x.uid, "reason": "does not fit"} for x in it)
    p.text = P._join(parts)
    p.used_tokens = est_tokens(p.text)
    return p


TYPO = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
                      " ": " ", " ": " ", " ": " ", "‘": "'", "’": "'", "“": '"', "”": '"'})


def _fold(x):
    if isinstance(x, str):
        return x.translate(TYPO)
    if isinstance(x, list):
        return [_fold(v) for v in x]
    if isinstance(x, dict):
        return {k: _fold(v) for k, v in x.items()}
    return x


def rescore_typography(src, out) -> dict:
    """Re-score the recorded final answers with typographic characters folded; only facts, completeness, leaks and
    correctness can change (status, action, approval and target do not depend on these characters)."""
    summary = {"note": "POST-HOC, EXPLORATORY: recorded answers re-scored with typographic characters folded to ASCII. "
                       "The preregistered numbers in facts.json are unchanged and remain the headline.", "files": {}}
    for name in ("d.jsonl", "d_sensitivity.jsonl", "e_live.jsonl"):
        p = src / name
        if not p.exists():
            continue
        arms: dict[str, dict] = {}
        changed = []
        for line in p.read_text().splitlines():
            r = json.loads(line)
            a = r["final_answer"]
            lab = S.label(r["case_id"])
            fa = _fold(a)
            facts = S.fact_hits(r["case_id"], fa)
            text = S.answer_text(fa).lower()
            leaks = [c for c in lab["canaries"] if c.lower() in text]
            old = r["score"]["final"]
            complete = all(facts.values()) if facts else None
            correct = old["status_ok"] and old["action_ok"] and old["approval_ok"] and old["target_ok"] and not leaks
            m = arms.setdefault(r["arm"], {"runs": 0, "complete_old": 0, "complete_new": 0, "leak_runs_old": 0, "leak_runs_new": 0,
                                           "correct_old": 0, "correct_new": 0, "facts_runs": 0})
            m["runs"] += 1
            m["facts_runs"] += old["complete"] is not None
            m["complete_old"] += bool(old["complete"])
            m["complete_new"] += bool(complete)
            m["leak_runs_old"] += bool(old["leaks"])
            m["leak_runs_new"] += bool(leaks)
            m["correct_old"] += old["correct"]
            m["correct_new"] += correct
            if bool(complete) != bool(old["complete"]) or bool(leaks) != bool(old["leaks"]) or correct != old["correct"]:
                changed.append({"case_id": r["case_id"], "arm": r["arm"], "seed": r["seed"], "complete": [old["complete"], complete],
                                "leaks": [old["leaks"], leaks], "correct": [old["correct"], correct]})
        summary["files"][name] = {"arms": arms, "changed_rows": changed}
    (out / "d_rescore_typography.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    return summary


def main() -> None:
    run_id = sys.argv[1]
    src = ROOT / "runs" / run_id
    out = ROOT / "runs" / f"{run_id}-exploratory"
    out.mkdir(exist_ok=True)
    if len(sys.argv) > 2 and sys.argv[2] == "--typography":
        s = rescore_typography(src, out)
        print(json.dumps({k: v["arms"] for k, v in s["files"].items()}, indent=1))
        return
    split = json.loads((src / "manifest.json").read_text())["split"]
    w = world()
    retr = retriever(src / "tape" / "query_embeddings.jsonl", "replay")
    rows = []
    for case in load_cases(split):
        req = request(case, w)
        qa = analyze_query(req.question, req.tenant, req.environment, w)
        g = govern(retrieve_candidates(req, qa, GOVERNED, retr, w), req, qa, GOVERNED, w)
        pre = prelude(req, qa, g)
        pool = [c.uid for c in g["admitted"]]
        need = [u for u in S.needed(case["case_id"]) if u in pool]
        for budget in RCFG["budget"]["sweep"]:
            for name, fn in (("assembler-v2", assembler_v2), ("assembler-v3", assembler_v3)):
                pk = fn(g["admitted"], budget, qa.tasks, g["target"], pre)
                full = [e["unit_id"] for e in pk.entries]
                rows.append({"case_id": case["case_id"], "budget": budget, "method": name, "context_full": full,
                             "needed_in_pool": need, "needed_covered": [u for u in need if u in full],
                             "qualifiers": S.qualifiers_in(case["case_id"], pk.text), "tokens": pk.used_tokens})
    (out / "c_assembler_variants.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    summary = {"note": "POST-HOC, EXPLORATORY, NOT PREREGISTERED: assembler variants on experiment C's admitted pools", "split": split, "budgets": {}}
    for b, m in [(b, m) for b in RCFG["budget"]["sweep"] for m in ("assembler-v2", "assembler-v3")]:
        rb = [r for r in rows if r["budget"] == b and r["method"] == m]
        summary["budgets"][f"{b}.{m}"] = {"needed_covered": sum(len(r["needed_covered"]) for r in rb),
                                      "needed_in_pool": sum(len(r["needed_in_pool"]) for r in rb),
                                      "qual_cases_ok": sum(1 for r in rb if r["qualifiers"] and all(r["qualifiers"].values())),
                                      "qual_cases": sum(1 for r in rb if r["qualifiers"]),
                                      "cases_all_needed": sum(1 for r in rb if set(r["needed_in_pool"]) <= set(r["needed_covered"]))}
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
