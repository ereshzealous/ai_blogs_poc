"""Render hitl_poc/README.md from README.template.md and the published run's facts (no number is typed).

    python3 tools/render_readme.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "hitl_poc" / "evidence"
run = json.loads((EV / "published.json").read_text())["run_id"]
facts = json.loads((EV / "runs" / run / "results.json").read_text())["facts"]
src = (ROOT / "hitl_poc" / "README.template.md").read_text()


def sub(m):
    k = m.group(1)
    if k not in facts:
        raise SystemExit(f"unknown fact {k}")
    return str(facts[k].get("display", facts[k]["value"]))


(ROOT / "hitl_poc" / "README.md").write_text(re.sub(r"\{\{([A-Za-z0-9_.\-]+)\}\}", sub, src))
print("hitl_poc/README.md rendered from run", run)
