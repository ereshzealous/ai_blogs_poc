"""ops_poc/README.md from ops_poc/README.template.md: every {{fact}} substituted from the published run.

    python3 tools/build_readme.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "ops_poc"


def fmt(v):
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:,.1f}".rstrip("0").rstrip(".") if v != int(v) else f"{int(v):,}"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, list):
        return ", ".join(map(str, v))
    return str(v)


def main() -> None:
    run = (POC / "runs" / "PUBLISHED").read_text().strip()
    facts = {k: v["value"] for k, v in json.loads((POC / "runs" / run / "facts.json").read_text()).items()}
    facts.update({k: v["value"] for k, v in json.loads((ROOT / "docs" / "derived-facts.json").read_text()).items()})
    for name in ("README", ):
        src = (POC / f"{name}.template.md").read_text() if name == "README" else ""

        def sub(m):
            if m.group(1) not in facts:
                sys.exit(f"README: unknown fact {m.group(1)}")
            return fmt(facts[m.group(1)])
        (POC / "README.md").write_text(re.sub(r"\{\{([\w.@\-]+)\}\}", sub, src))
    tpl = ROOT / "README.template.md"
    if tpl.exists():
        (ROOT / "README.md").write_text(re.sub(r"\{\{([\w.@\-]+)\}\}", lambda m: fmt(facts[m.group(1)]) if m.group(1) in facts
                                               else sys.exit(f"package README: unknown fact {m.group(1)}"), tpl.read_text()))
    print("README.md rendered (POC and package)")


if __name__ == "__main__":
    main()
