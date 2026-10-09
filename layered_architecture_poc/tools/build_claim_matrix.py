"""Write docs/claim_evidence_matrix.md from layered_architecture_poc/docs/claims.yaml, and refuse to write a broken one.

    python3 tools/build_claim_matrix.py            # validate, then render
    python3 tools/build_claim_matrix.py --check    # validate only

The claims are data, not code, so they can be reviewed and diffed. For each one this checks, against the published
run:

- the status is SUPPORTED, QUALIFIED, CONTRADICTED or UNSUPPORTED, and a QUALIFIED claim says what qualifies it;
- every `{{fact}}` token resolves, so no number in the matrix is typed by hand;
- every facts path exists in facts.json;
- every verification check it names ran, and passed, in verification.json;
- every raw path it names exists in the run;
- every test it names exists as a file and a function;
- every invariant id it names exists in docs/invariants.yaml;
- it says both what the evidence shows and what it does not show.

A failure exits non-zero and writes nothing: a claim cannot outlive its evidence.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_docs as bd  # noqa: E402

POC = bd.ROOT / "layered_architecture_poc"
CLAIMS = POC / "docs" / "claims.yaml"
INVARIANTS = POC / "docs" / "invariants.yaml"
STATUSES = ("SUPPORTED", "QUALIFIED", "CONTRADICTED", "UNSUPPORTED")
HEADING = {
    "SUPPORTED": ("Supported", "The recorded evidence supports these as written."),
    "QUALIFIED": ("Qualified", "Supported only inside a stated limit. The limit is part of the claim."),
    "CONTRADICTED": ("Contradicted", "The evidence contradicts these. They are kept, with the number that contradicts them."),
    "UNSUPPORTED": ("Not tested here", "Claims this POC does not make. Listed so no reader assumes them."),
}
TEST_CASE = re.compile(r"\[.*\]$")


def published_run() -> Path:
    return POC / "runs" / (POC / "runs" / "PUBLISHED").read_text().strip()


def validate(claims: list[dict], facts: dict) -> list[str]:
    run = published_run()
    problems: list[str] = []
    verification = run / "verification.json"
    checks = {c["check"]: c for c in json.loads(verification.read_text())["checks"]} if verification.exists() else {}
    invariants = yaml.safe_load(INVARIANTS.read_text())
    known_invariants = set(invariants["invariants"]) | set(invariants["not_enforced"])
    seen: set[str] = set()

    for claim in claims:
        cid = claim.get("id", "?")
        if cid in seen:
            problems.append(f"{cid}: duplicate id")
        seen.add(cid)
        if claim.get("status") not in STATUSES:
            problems.append(f"{cid}: status {claim.get('status')!r} is not one of {STATUSES}")
        if claim.get("status") == "QUALIFIED" and not claim.get("qualifier"):
            problems.append(f"{cid}: QUALIFIED with no qualifier")
        for field in ("claim", "evidence", "shows", "does_not_show", "article_section"):
            if not claim.get(field):
                problems.append(f"{cid}: no {field}")
        for path in claim.get("facts") or []:
            if path not in facts:
                problems.append(f"{cid}: facts.json has no {path}")
        for name in claim.get("verification") or []:
            if name not in checks:
                problems.append(f"{cid}: verification.json has no check {name!r}")
            elif checks[name]["ok"] is False:
                problems.append(f"{cid}: check {name!r} failed in the published run")
        for pattern in claim.get("raw") or []:
            # a path inside the run, inside the POC, or a bundle document (docs/real_vs_simulated.md and friends)
            if not any((list(run.glob(pattern)), (run / pattern).exists(),
                        (POC / pattern).exists(), (bd.ROOT / pattern).exists())):
                problems.append(f"{cid}: nothing matches {pattern} in the run, the POC or the bundle")
        for node in claim.get("tests") or []:
            rel, _, name = node.partition("::")
            path = POC / rel
            if not path.exists():
                problems.append(f"{cid}: no test file {rel}")
            elif name and f"def {TEST_CASE.sub('', name)}(" not in path.read_text():
                problems.append(f"{cid}: {rel} has no {name}")
        for inv in claim.get("invariants") or []:
            if inv not in known_invariants:
                problems.append(f"{cid}: unknown invariant {inv}")
    return problems


def row(claim: dict, facts: dict, uses: dict) -> str:
    def render(text: str) -> str:
        return bd.render_facts(str(text), facts, "claim_matrix", uses).replace("\n", " ").strip()

    status = claim["status"] + (f" — {render(claim['qualifier'])}" if claim.get("qualifier") else "")
    invariants = ", ".join(claim.get("invariants") or []) or "—"
    tests = "<br>".join(f"`{n.split('::')[-1] or n}`" for n in claim.get("tests") or []) or "none"
    raw = "<br>".join(f"`{p}`" for p in claim.get("raw") or []) or "—"
    verification = "<br>".join(f"*{n}*" for n in claim.get("verification") or []) or "—"
    return (f"| **{claim['id']}** | {render(claim['claim'])}<br>{status} | {render(claim['evidence'])} "
            f"| {verification} | {raw} | {tests} | {invariants} | {claim.get('figure', 'none')} "
            f"| {render(claim['shows'])} | {render(claim['does_not_show'])} |")


def main() -> int:
    facts = bd.load_facts()
    claims = yaml.safe_load(CLAIMS.read_text())["claims"]
    problems = validate(claims, facts)
    for p in problems:
        print("FAIL", p)
    if problems:
        print(f"{len(problems)} problem(s): nothing written")
        return 1
    if "--check" in sys.argv:
        print(f"{len(claims)} claims validated")
        return 0

    run = published_run()
    uses: dict = {}
    counts = {s: sum(1 for c in claims if c["status"] == s) for s in STATUSES}
    out = [
        "# Claim and evidence matrix",
        "",
        f"Every claim the F2 publications make about this POC, what the recorded run `{run.name}` says about it, and "
        "where a reader can check. Generated by `tools/build_claim_matrix.py` from "
        "`layered_architecture_poc/docs/claims.yaml`; every number is substituted from that run's `facts.json`, and the "
        "build fails if a claim cites evidence the run does not have.",
        "",
        "| Verdict | Claims |",
        "|---|---|",
        *[f"| {HEADING[s][0]} | {counts[s]} |" for s in STATUSES],
        "",
        "Verdicts are about this POC only: one simulated incident, local models, three seeds, one machine.",
    ]
    for status in STATUSES:
        rows = [c for c in claims if c["status"] == status]
        if not rows:
            continue
        title, lede = HEADING[status]
        out += ["", f"## {title}", "", lede, "",
                "| # | Claim and verdict | Evidence (from facts.json) | Recomputed by | Raw files | Tests | Invariants | Figure | What it shows | What it does not show |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        out += [row(c, facts, uses) for c in rows]
    (bd.ROOT / "docs" / "claim_evidence_matrix.md").write_text("\n".join(out) + "\n")
    print(f"{len(claims)} claims: " + ", ".join(f"{HEADING[s][0]} {counts[s]}" for s in STATUSES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
