"""report.md: a readable table generated from summary.json (never typed by hand)."""

from __future__ import annotations

from typing import Any

CLASSES = ["expired", "wrong_tenant", "wrong_environment", "poisoned", "superseded", "workflow_claim", "speculation"]


def _frac(p: list[int]) -> str:
    return f"{p[0]}/{p[1]}"


def render(s: dict[str, Any]) -> str:
    out = [f"# S1 run `{s['run_id']}` ({s['mode']})", "",
           f"Model `{s['model']}` · embeddings `{s['embedding_model']}` · seeds {s['seeds']} · top-N {s['candidates_n']} · "
           f"evidence budget {s['evidence_budget_tokens']} tokens · clock {s['clock']} · frozen digest `{s['frozen_digest']}`", "",
           f"Governed invariants passed: **{s['invariants_passed']}/{s['invariants_total']}** experiments", "",
           "| Exp | Arm | Invalid admitted | Contradicted (unmarked / marked) | Useful recall | Precision | RB-CHK-007 | Tokens | Correct action |",
           "|---|---|---|---|---|---|---|---|---|"]
    for eid, e in s["experiments"].items():
        if "arms" not in e:
            continue
        for arm, a in e["arms"].items():
            m = a["admission"]
            inv = ", ".join(f"{k}={v}" for k, v in m["invalid_admitted"].items() if v) or "0"
            o = a.get("outcome")
            out.append(f"| {eid} | {arm} | {inv} | {m['contradicted_unmarked']} / {m['contradicted_marked']} | {_frac(m['useful_recall'])} | "
                       f"{_frac(m['context_precision'])} | {'yes' if m['authoritative_present'] else 'no'} | {m['evidence_tokens']} | "
                       f"{f'{o['correct']}/{o['runs']}' if o else '—'} |")
    out += ["", "## Governed invariants", ""]
    for eid, e in s["experiments"].items():
        inv = e.get("arms", {}).get("governed", {}).get("invariants")
        if inv:
            out.append(f"- **{eid}** " + ", ".join(f"{k}: {'PASS' if v else 'FAIL'}" for k, v in inv.items()))
    out += ["", "## Actions chosen (all seeds)", ""]
    for eid, e in s["experiments"].items():
        for arm, a in e.get("arms", {}).items():
            if "outcome" in a:
                out.append(f"- {eid} {arm}: {a['outcome']['actions']} (forbidden {a['outcome']['forbidden']}, cited RB-CHK-007 {a['outcome']['cited_runbook']}, errors {a['outcome']['errors']})")
    if "M6A" in s["experiments"]:
        out += ["", "## M6A · memory write path", "", "| Event | Kind | Naive persisted | Governed | Tier | Scope |", "|---|---|---|---|---|---|"]
        for w in s["experiments"]["M6A"]["writes"]:
            sc = w["governed_scope"] or {}
            out.append(f"| {w['event']} | {w['kind']} | yes | {w['governed_reason']} | {w['governed_tier'] or '—'} | "
                       f"{sc.get('session') or sc.get('environment') or '—'} |")
    return "\n".join(out) + "\n"
