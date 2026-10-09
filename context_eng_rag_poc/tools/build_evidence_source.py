"""docs/source/evidence.src.md: the Evidence Check, every claim traced to its proof, generated (never typed by hand).

    python3 tools/build_evidence_source.py

Reads research/claims.toml (the claims, their class, experiments and facts) and the frozen
enterprise_knowledge_rag_poc/experiments/preregistration.toml (each hypothesis's statement and mechanical test). Every
observed value is a {{fact}} token that build_docs.py substitutes from the published run, so this page cannot drift from
the run; a fact's source is copied from facts.json (or docs/derived-facts.json for post-hoc `x.` keys).
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POC = ROOT / "enterprise_knowledge_rag_poc"

# The rows file each experiment's facts come from (raw evidence pointers, relative to the run directory).
ROWS = {"A": "a.jsonl", "B": "b.jsonl", "C": "c.jsonl", "D": "d.jsonl", "D2": "d2.jsonl", "E": "e_evidence.jsonl, e_live.jsonl"}
CLASSES = [
    ("SUPPORTED", "the preregistered test passed on the held-out run"),
    ("NOT SUPPORTED", "the preregistered test failed; the editions say so where the claim is discussed"),
    ("NEGATIVE CONTROL", "a safeguard removed on purpose, and the property it protects broke, as designed"),
    ("POST-HOC", "measured after the run, not preregistered; never a headline"),
    ("ARGUED", "architecture or synthesis, supported by sources and design; the facts listed are the closest measurements"),
]


def main() -> None:
    run = (POC / "runs" / "PUBLISHED").read_text().strip()
    facts = json.loads((POC / "runs" / run / "facts.json").read_text())
    facts.update(json.loads((ROOT / "docs" / "derived-facts.json").read_text()))
    claims = tomllib.loads((ROOT / "research" / "claims.toml").read_text())["claims"]
    hyps = {h["id"]: h for h in tomllib.loads((POC / "experiments" / "preregistration.toml").read_text())["hypotheses"]}

    out = ["---", "title: Evidence Check: every claim, traced to its proof",
           "subtitle: Each claim of the S2 editions, the experiment that tests it, the preregistered test, what the run observed, and the class a reader should give it.",
           "byline: S2 · Production AI Engineering", "kicker: Production AI Engineering · S2 · Evidence Check", "filed: 2026-10-08",
           "run: Recorded run {{run.id}}", "---", "", "## How to read this", "",
           "Every claim is stated without its numbers. The numbers are the facts the editions print for it, substituted at build time "
           "from `enterprise_knowledge_rag_poc/runs/{{run.id}}/facts.json`; post-hoc numbers (keys starting `x.`) come from "
           "`docs/derived-facts.json` and are labelled so. A verdict is computed by `s2_eval/hypotheses.py` from the test written in "
           "`experiments/preregistration.toml` before the held-out run, never chosen afterwards.", ""]
    out += [f"- **{c}**: {d};" if i < len(CLASSES) - 1 else f"- **{c}**: {d}." for i, (c, d) in enumerate(CLASSES)]
    out += ["", "## The proof pack", "",
            "| Check | Result |", "|---|---|",
            "| preregistered hypotheses | {{hyp.supported}} of {{hyp.total}} supported; not supported: {{hyp.not_supported.list}} |",
            "| frozen inputs unchanged since the freeze | {{frozen.unchanged}} of {{frozen.files}} files |",
            "| independent recomputation of the headline numbers from the rows | {{evcheck.pass}} pass, {{evcheck.fail}} fail, of {{evcheck.total}} |",
            "| replay from the tapes, no model | {{replay.verdict}}: {{replay.identical}} files byte-identical, {{replay.different}} different, {{replay.model_calls_from_tape}} model calls served from tape |",
            "| tests | {{tests.passed}} of {{tests.total}} passed |", "",
            "The failure in the recomputation is a result, not a defect: it checks that every governed invariant holds, and "
            "{{inv.governed.holding}} of {{inv.governed.total}} do (I4 fails on {{inv.governed.I4.failing}}, I6 on {{inv.governed.I6.failing}}; "
            "technical edition §16.2). The output is `verification/evidence-check.txt`.", ""]

    for c in claims:
        out += [f"## {c['id']} · {c['class']}", "", f"**{c['statement']}**", ""]
        out.append(f"*Experiment:* {', '.join(c['experiments'])}.")
        h = hyps.get(c.get("hypothesis", ""))
        if h:
            out += ["", f"*Preregistered ({h['id']}):* {h['statement']} Test: `{h['test']}`. Verdict: **{{{{{h['id']}}}}}**."]
        out += ["", "| Fact | Observed | Source |", "|---|---|---|"]
        for k in c["facts"]:
            if k not in facts:
                raise SystemExit(f"{c['id']}: unknown fact {k}")
            src = facts[k]["source"].split(" (")[0]
            out.append(f"| `{k}` | {{{{{k}}}}} | {src} |")
        rows = sorted({ROWS[e.split(" ")[0]] for e in c["experiments"] if e.split(" ")[0] in ROWS})
        out += ["", f"*Where in the editions:* {'; '.join(c['article'])}."]
        if rows:
            out.append(f"*Raw evidence:* `runs/{{{{run.id}}}}/` {'; '.join(rows)}; `python -m s2_eval.cli explain <case>` replays any case stage by stage.")
        out.append("")

    out += ["The same mapping with every fact's value is `research/claims-matrix.md`, generated by `tools/build_claims_matrix.py`, "
            "which refuses a claim whose class contradicts its hypothesis's verdict."]
    (ROOT / "docs" / "source" / "evidence.src.md").write_text("\n".join(out) + "\n")
    print(f"docs/source/evidence.src.md written ({len(claims)} claims)")


if __name__ == "__main__":
    main()
