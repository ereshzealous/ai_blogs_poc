"""evidence-kit command line.

    python -m evidence_kit build evidence.json [--traces traces.json] --out lab-console.html
    python -m evidence_kit example [--out example.html]        render the bundled example (illustrative data)
    python -m evidence_kit version
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, render_console

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "minimal"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="evidence_kit", description="Render a Lab Console from evidence.json.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="render evidence.json (and optional traces.json) to one self-contained HTML page")
    b.add_argument("evidence", type=Path)
    b.add_argument("--traces", type=Path)
    b.add_argument("--out", type=Path, required=True)
    e = sub.add_parser("example", help="render the bundled example")
    e.add_argument("--out", type=Path, default=Path("evidence-kit-example.html"))
    sub.add_parser("version")
    ns = ap.parse_args(argv)
    if ns.cmd == "version":
        print(__version__)
        return
    if ns.cmd == "example":
        ns.evidence, ns.traces = EXAMPLE / "evidence.json", EXAMPLE / "traces.json"
    ev = json.loads(ns.evidence.read_text())
    tr = json.loads(ns.traces.read_text()) if ns.traces and ns.traces.exists() else None
    res = render_console(ev, tr, ns.out)
    print(f"{res['out']} ({res['bytes'] // 1024} KB) · evidence-kit {__version__}", file=sys.stderr)


if __name__ == "__main__":
    main()
