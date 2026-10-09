#!/usr/bin/env python3
"""No measured number may be typed by hand into a publication source.

    python3 tools/check_numbers.py            # every source under docs/source/
    python3 tools/check_numbers.py --list     # also print what each allowed number is

`build_docs.py` already fails on an unknown `{{fact}}` token. That stops a wrong key, not a hand-typed value: a
number written as prose looks fine to it and goes stale the next time the run changes. This closes that gap.

Every numeral left in a source after tokens, code, links and list numbering are removed must be one of:

- **measured** — it matches a value in the published run's facts.json. That is a failure: use the token.
- **a constant of the simulated incident** — it appears in the frozen scenario, policy or capability files, so the
  prose and the simulated world cannot drift apart.
- **structural** — it describes the article or the design rather than the run. Every one of these is listed in
  ALLOWED with the reason it is not a measurement.

Anything else fails as unexplained.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
POC = HERE / "layered_architecture_poc"
SOURCES = sorted((HERE / "docs" / "source").rglob("*.md")) + [HERE / "layered_architecture_poc" / "README.template.md"]
# These two are written by tools/build_evidence_check.py and tools/build_run_report.py, which resolve facts
# themselves and record every use in docs/evidence-uses.json.  A number there is traceable if it is a recorded use.
GENERATED = {"evidence.src.md", "report.src.md"}
FROZEN_DIRS = ("simulated_enterprise", "config", "experiments/preregistration")

# Numbers that describe the architecture or the article, never a measurement. Each needs a reason.
ALLOWED = {
    "1": "layer 1, and 'one process', 'one incident', 'one trace', 'one request'",
    "2": "layer 2, the two architectures, the two models",
    "3": "layer 3, the three agents, the three seeds, the three publications",
    "4": "layer 4, and the four outcome classes (SUCCESS, FAILURE, ERROR, NOT_EXPOSED)",
    "5": "layer 5",
    "6": "layer 6, and the six logical layers this article proposes",
    "7": "seed 7 of the preregistered seeds 7/11/13, and the seven policy rules",
    "8": "the eight deterministic outcome checks, listed before any count is given",
    "9": "the nine experiment families E1–E9",
    "11": "seed 11 of the preregistered seeds",
    "13": "seed 13 of the preregistered seeds",
    "15": "the fifteen architecture invariants L1–L15",
    "0": "'zero' written as a digit in prose about a property, never as a measured count",
    "500": "the HTTP 500 in the quoted model-service error, and F1's 500-tool catalogue cited as series context",
}


def facts() -> dict[str, str]:
    """Published values, formatted the way a document would print them, mapped back to their token."""
    run = POC / "runs" / (POC / "runs" / "PUBLISHED").read_text().strip()
    data = json.loads((run / "facts.json").read_text())
    out: dict[str, str] = {}
    for key, leaf in data.items():
        value = leaf.get("value") if isinstance(leaf, dict) else leaf
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            for form in ({f"{value:,}", str(value)} if isinstance(value, int) else {f"{value:,.1f}", str(value)}):
                out.setdefault(form, key)
    return out


def incident_constants() -> set[str]:
    """Numbers that exist in the frozen inputs: the scenario, the policy, the capabilities, the plan."""
    paths = [str(POC / d) for d in FROZEN_DIRS if (POC / d).exists()]
    found = subprocess.run(["grep", "-rhoE", r"[0-9][0-9,.]*", *paths], capture_output=True, text=True).stdout
    out: set[str] = set()
    for token in found.split():
        token = token.strip(".,")
        out |= {token, token.replace(",", "")}
    return out


def prose(text: str) -> list[tuple[int, str]]:
    """Lines with code, tokens, links, dates, versions and list numbering removed."""
    text = re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("|---", "---")):
            continue
        line = re.sub(r"\{\{[^}]+\}\}", " ", line)          # a fact token: the whole point
        line = re.sub(r"`[^`]*`", " ", line)                # inline code: ids, paths, settings
        line = re.sub(r"\]\([^)]*\)", "] ", line)           # link targets
        line = re.sub(r"\d{4}-\d{2}-\d{2}", " ", line)      # dates, including run ids
        line = re.sub(r"\bv?\d+\.\d+(\.\d+)*\b", " ", line)  # versions: 2.14.0, 6.4, rel ids handled below
        line = re.sub(r"^\s{0,3}#{1,6}\s*\d+[.)]?\s", " ", line)  # numbered headings
        line = re.sub(r"^\s*\d+[.)]\s", " ", line)          # ordered list markers
        line = re.sub(r"\brel-\d+\b|\bE\d\b|\bL\d+\b|\bN\d\b|\bC\d+\b|\bf\d+[a-z]?\b|\bP\d\b|\br\d\b", " ", line)  # ids
        out.append((i, line))
    return out


def recorded_uses() -> set[str]:
    """Values the generators resolved from facts and recorded in docs/evidence-uses.json."""
    path = HERE / "docs" / "evidence-uses.json"
    if not path.exists():
        return set()
    out: set[str] = set()
    for use in json.loads(path.read_text()).values():
        value = use.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out |= {str(value), f"{value:,}"}
    return out


def main() -> int:
    measured, constants = facts(), incident_constants()
    resolved = recorded_uses()
    fails: list[str] = []
    counts = {"structural": 0, "incident": 0, "resolved": 0}
    for source in SOURCES:
        for lineno, line in prose(source.read_text()):
            for m in re.finditer(r"(?<![\w.:/-])\d[\d,]*(?:\.\d+)?", line):
                token = m.group(0).rstrip(".")
                if token in ALLOWED:
                    counts["structural"] += 1
                elif token in constants or token.replace(",", "") in constants:
                    counts["incident"] += 1
                elif source.name in GENERATED and (token in resolved or token.replace(",", "") in resolved):
                    counts["resolved"] += 1
                elif token in measured:
                    fails.append(f"{source.relative_to(HERE)}:{lineno}: {token} is a measured value "
                                 f"(facts.json → {measured[token]}); write {{{{{measured[token]}}}}} instead")
                else:
                    fails.append(f"{source.relative_to(HERE)}:{lineno}: {token} is not in the run, the frozen "
                                 f"inputs or ALLOWED — {line.strip()[:70]}")
    print(f"{len(SOURCES)} source file(s): {counts['structural']} structural number(s), "
          f"{counts['incident']} constant(s) of the simulated incident, "
          f"{counts['resolved']} resolved from facts by a generator and recorded in evidence-uses.json")
    if "--list" in sys.argv:
        for token, why in sorted(ALLOWED.items(), key=lambda kv: int(kv[0])):
            print(f"  allowed {token:>3}  {why}")
    for f in fails:
        print("FAIL", f)
    print(f"{len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
