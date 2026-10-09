"""Export the numbers the data-driven scenes (04, 12) and the article need, from ONE recorded run.

    python3 tools/export_diagram_data.py 2026-09-18-recorded

Reads memory-context-state-poc/runs/<run>/summary.json, the M0 audit manifests and labels.yaml; writes
diagrams/generator/data/run-facts.json and article/article-numbers.json. Numbers are never typed by hand.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent.parent
POC = HERE / "memory-context-state-poc"


def main(run_id: str) -> None:
    run = POC / "runs" / run_id
    s = json.loads((run / "summary.json").read_text())
    labels = yaml.safe_load((POC / "scenarios" / "labels.yaml").read_text())
    corpus = yaml.safe_load((POC / "scenarios" / "corpus.yaml").read_text())
    content = {r["id"]: " ".join(r["content"].split()) for r in corpus["base"] + [x for g in corpus["injections"].values() for x in g]}
    naive = {c["id"]: c for c in json.loads((run / "audit" / "M0-naive.json").read_text())["candidates"]}
    gov = {c["id"]: c for c in json.loads((run / "audit" / "M0-governed.json").read_text())["candidates"]}
    k5 = {c["id"]: c for c in json.loads((run / "audit" / "M0-naive_k5.json").read_text())["candidates"]}
    m0 = []
    ordered = sorted(naive.items(), key=lambda kv: (-kv[1]["similarity"], kv[0]))
    rank_of = {cid: i + 1 for i, (cid, _) in enumerate(ordered)}
    for cid, c in ordered[:12]:
        g = gov[cid]
        m0.append({"id": cid, "similarity": c["similarity"], "failure": labels[cid]["failure"], "useful": labels[cid]["useful"],
                   "text": content[cid], "rank": rank_of[cid], "naive": c["outcome"], "naive_k5": k5[cid]["outcome"], "governed": g["outcome"],
                   "governed_reason": g["reason"], "tier": g["tier"]})
    rows = []
    for eid, e in s["experiments"].items():
        if "arms" not in e:
            continue
        r = {"exp": eid, "title": e["title"], "correct_action": e["correct_action"]}
        for arm in ("naive", "naive_k5", "governed"):
            a = e["arms"][arm]
            m = a["admission"]
            r[arm] = {"invalid": m["invalid_admitted_total"], "contradicted_unmarked": m["contradicted_unmarked"],
                      "contradicted_marked": m["contradicted_marked"], "runbook": m["authoritative_present"],
                      "recall": m["useful_recall"], "precision": m["context_precision"], "tokens": m["evidence_tokens"]}
            if "outcome" in a:
                r[arm] |= {"correct": a["outcome"]["correct"], "runs": a["outcome"]["runs"], "forbidden": a["outcome"]["forbidden"],
                           "actions": a["outcome"]["actions"]}
            if "invariants" in a:
                r[arm]["invariants_pass"] = all(a["invariants"].values())
        rows.append(r)
    facts = {
        "placeholder": False, "run_id": s["run_id"], "model": s["model"], "embedding_model": s["embedding_model"],
        "seeds": s["seeds"], "budget": s["evidence_budget_tokens"], "candidates_n": s["candidates_n"],
        "frozen_digest": s["frozen_digest"], "invariants_passed": s["invariants_passed"], "invariants_total": s["invariants_total"],
        "m0_candidates": m0, "m0_runbook_rank": rank_of["kb-rb-chk-007"], "rows": rows,
        "m9_naive_rationale": next(json.loads(l)["rationale"] for l in (run / "results.jsonl").read_text().splitlines()
                                   if json.loads(l)["experiment"] == "M9" and json.loads(l)["arm"] == "naive" and json.loads(l)["seed"] == 7), "m6a": s["experiments"]["M6A"]["writes"],
        "totals": {arm: {k: sum(r[arm].get(k, 0) for r in rows if r["exp"] != "M6B") for k in ("invalid", "correct", "runs", "forbidden")}
                   for arm in ("naive", "governed")},
    }
    out = HERE / "diagrams" / "generator" / "data" / "run-facts.json"
    out.write_text(json.dumps(facts, indent=1) + "\n")
    (HERE / "article").mkdir(exist_ok=True)
    (HERE / "article" / "article-numbers.json").write_text(json.dumps(facts, indent=1) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2026-09-18-recorded")
