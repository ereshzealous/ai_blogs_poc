"""Render README.md and redteam_poc/README.md from templates, substituting {{facts}} from the published run.

    python3 tools/render_readme.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_docs import subst  # noqa: E402  (reuses the same fact map and {{token}} lint)

PAIRS = [("docs/templates/README.template.md", "README.md"),
         ("docs/templates/poc-README.template.md", "redteam_poc/README.md")]


def main() -> None:
    for tpl, out in PAIRS:
        src = (ROOT / tpl).read_text()
        (ROOT / out).write_text(subst(src))
        print(f"rendered {out}")


if __name__ == "__main__":
    main()
