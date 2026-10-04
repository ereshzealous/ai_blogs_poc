"""evidence-kit command line.

    python -m evidence_kit render evidence.json [--traces traces.json] --out lab-console.html   render an evidence.json
    python -m evidence_kit example [--out example.html]        build the bundled example (illustrative data, its own spec)
    python -m evidence_kit version

A learning builds its evidence with evidence_kit.build(spec, data, facts, out) from its own exporter.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from . import __version__, render_console

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "workflow" / "make_example.py"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="evidence_kit", description="Build or render a Lab Console.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("render", help="render evidence.json (and optional traces.json) to one self-contained HTML page")
    b.add_argument("evidence", type=Path)
    b.add_argument("--traces", type=Path)
    b.add_argument("--out", type=Path, required=True)
    e = sub.add_parser("example", help="build the bundled example")
    e.add_argument("--out", type=Path, default=Path("evidence-kit-example.html"))
    sub.add_parser("version")
    ns = ap.parse_args(argv)
    if ns.cmd == "version":
        print(__version__)
        return
    if ns.cmd == "example":
        spec = importlib.util.spec_from_file_location("make_example", EXAMPLE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = mod.build(ns.out.resolve())
    else:
        ev = json.loads(ns.evidence.read_text())
        tr = json.loads(ns.traces.read_text()) if ns.traces and ns.traces.exists() else None
        res = render_console(ev, tr, ns.out)
    print(f"{res['out']} ({res['bytes'] // 1024} KB) · evidence-kit {__version__}", file=sys.stderr)


if __name__ == "__main__":
    main()
