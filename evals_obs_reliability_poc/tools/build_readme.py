"""recovery_poc/README.md from recovery_poc/README.template.md: every {{fact}} substituted from the published run.

    python3 tools/build_readme.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "recovery_poc"


def main() -> None:
    run = (POC / "runs" / "PUBLISHED").read_text().strip()
    facts = {k: v["value"] for k, v in json.loads((POC / "runs" / run / "facts.json").read_text()).items()}
    facts.update({k: v["value"] for k, v in json.loads((ROOT / "docs" / "derived-facts.json").read_text()).items()})
    src = (POC / "README.template.md").read_text()

    def sub(m):
        if m.group(1) not in facts:
            sys.exit(f"README: unknown fact {m.group(1)}")
        return str(facts[m.group(1)])
    out = re.sub(r"\{\{([\w.@\-]+)\}\}", sub, src)
    (POC / "README.md").write_text(out)
    print("recovery_poc/README.md rendered")


if __name__ == "__main__":
    main()
