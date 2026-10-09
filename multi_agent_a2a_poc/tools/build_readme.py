"""coordination_poc/README.md from coordination_poc/README.template.md: every {{fact}} substituted from the published run.

    python3 tools/build_readme.py

Ported from R1+R2 (evals_obs_reliability/tools/build_readme.py).  Facts: coordination_poc/runs/<PUBLISHED>/facts.json
plus docs/derived-facts.json when it exists (a key defined in both is a failure, as in tools/build_docs.py).  An unknown
{{key}} is a failure.  Until the template exists there is nothing to render, and the tool says so and exits 0.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "coordination_poc"


def main() -> None:
    template = POC / "README.template.md"
    if not template.exists():
        print("coordination_poc/README.template.md not written yet: README not rendered")
        return
    pointer = POC / "runs" / "PUBLISHED"
    if not pointer.exists():
        sys.exit("README: no published run (coordination_poc/runs/PUBLISHED is missing)")
    run = pointer.read_text().strip()
    facts = {k: v["value"] for k, v in json.loads((POC / "runs" / run / "facts.json").read_text()).items()}
    dp = ROOT / "docs" / "derived-facts.json"
    derived = {k: v["value"] for k, v in json.loads(dp.read_text()).items()} if dp.exists() else {}
    clash = set(facts) & set(derived)
    if clash:
        sys.exit(f"README: fact defined twice: {sorted(clash)}")
    facts.update(derived)

    def sub(m):
        if m.group(1) not in facts:
            sys.exit(f"README: unknown fact {m.group(1)}")
        return str(facts[m.group(1)])
    out = re.sub(r"\{\{([\w.@\-]+)\}\}", sub, template.read_text())
    (POC / "README.md").write_text(out)
    print("coordination_poc/README.md rendered")


if __name__ == "__main__":
    main()
