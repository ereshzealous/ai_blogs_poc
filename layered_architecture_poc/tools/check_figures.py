#!/usr/bin/env python3
"""The figures must agree with the run they illustrate, without being re-exported to prove it.

    python3 tools/check_figures.py            # validate every figure against the published run
    python3 tools/check_figures.py --list     # also print each figure's numbers and where they come from

Re-exporting a figure changes bytes without changing meaning, so this validates the exports already on disk:

1. every figure in the manifest exists as .svg, .png and .excalidraw, under the filename the manifest states;
2. every figure a publication references exists in the manifest, and every manifest figure is referenced somewhere;
3. no figure's text names a run other than the published one;
4. every number drawn in a figure is traceable: a value in the published run's facts.json, a constant of the frozen
   simulated incident, or one of the listed structural numbers.

Point 4 is the one that matters: a figure is where a stale measurement hides longest, because nobody greps a PNG.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
POC = HERE / "layered_architecture_poc"
PREMIUM = HERE / "diagrams" / "premium"
KINDS = {"svg": "svg", "png": "png", "excalidraw": "excalidraw"}

# Numbers a figure may draw that are not measurements. Each needs a reason.
STRUCTURAL = {
    "1": "layer 1, step 1, 'one trace', 'one process'",
    "2": "layer 2, the two architectures, the two models",
    "3": "layer 3, the three agents, the three seeds, three runs per cell",
    "4": "layer 4, the four outcome classes",
    "5": "layer 5",
    "6": "layer 6, and the six logical layers",
    "7": "seed 7, and the seven policy rules",
    "8": "the eight outcome checks",
    "9": "the nine experiment families E1-E9",
    "10": "a 10-point trace score, and layer counts in the review-surface figure",
    "11": "seed 11",
    "13": "seed 13",
    "15": "the fifteen architecture invariants",
    "0": "zero, drawn as a digit",
    "20": "the model name gpt-oss:20b",
    "09": "the month in the run id",
    "28": "the day in the run id",
    "2026": "the year in the run id",
}


def facts() -> dict[str, str]:
    run = POC / "runs" / (POC / "runs" / "PUBLISHED").read_text().strip()
    data = json.loads((run / "facts.json").read_text())
    out: dict[str, str] = {}
    for key, leaf in data.items():
        value = leaf.get("value") if isinstance(leaf, dict) else leaf
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            for form in {str(value), f"{value:,}", f"{value:,.1f}", str(int(value)) if float(value).is_integer() else str(value)}:
                out.setdefault(form, key)
        elif isinstance(value, str):
            for token in re.findall(r"\d[\d,.]*", value):      # "3/3", "7.0/10", "15,956 tokens"
                out.setdefault(token.strip("."), key)
    return out


def incident_constants() -> set[str]:
    import subprocess
    paths = [str(POC / d) for d in ("simulated_enterprise", "config", "experiments/preregistration") if (POC / d).exists()]
    found = subprocess.run(["grep", "-rhoE", r"[0-9][0-9,.]*", *paths], capture_output=True, text=True).stdout
    out: set[str] = set()
    for token in found.split():
        token = token.strip(".,")
        out |= {token, token.replace(",", "")}
    return out


def sqlite_numbers(path: Path) -> str:
    """Every value in every table of a SQLite data source, as text. A figure may draw a count from a database."""
    import sqlite3

    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        rows = []
        for table in tables:
            for row in con.execute(f"SELECT * FROM {table}"):                     # noqa: S608 - names from sqlite_master
                rows.append(" ".join(str(v) for v in row))
            # aggregates a figure is likely to draw: totals, and the same totals grouped by each column
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]            # noqa: S608
            sums = [c for c in cols if c.endswith("tokens")]
            expr = "+".join(sums) if sums else None
            for group in [None, *cols]:
                select = f"SELECT COUNT(*)" + (f", SUM({expr})" if expr else "")
                query = f"{select} FROM {table}" + (f" GROUP BY {group}" if group else "")   # noqa: S608
                try:
                    rows += [" ".join(str(v) for v in r) for r in con.execute(query)]
                except sqlite3.Error:
                    continue
        return "\n".join(rows)
    except sqlite3.Error:
        return ""


def source_numbers(fig: dict) -> set[str]:
    """Every number in the raw records this figure's manifest entry names as its data source.

    A figure can legitimately draw a process id, a per-scenario wall time or a token count that is not a leaf of
    facts.json but is in the records the figure cites. Those are traceable; anything else is not.
    """
    out: set[str] = set()
    for pattern in fig.get("data_sources", []):
        rel = pattern[len("layered_architecture_poc/"):] if pattern.startswith("layered_architecture_poc/") else pattern
        for path in sorted(POC.glob(rel)) or ([POC / rel] if (POC / rel).exists() else []):
            if not path.is_file() or path.suffix in (".png", ".zip") or path.stat().st_size > 8_000_000:
                continue
            body = sqlite_numbers(path) if path.suffix == ".db" else path.read_text(errors="replace")
            for token in re.findall(r"\d[\d,.]*", body):
                token = token.strip(".")
                out |= {token, token.replace(",", "")}
                if token.replace(",", "").isdigit():
                    out.add(f"{int(token.replace(',', '')):,}")
    return out


def svg_text(path: Path) -> str:
    raw = path.read_text(errors="replace")
    return " ".join(re.sub(r"<[^>]+>", "", t) for t in re.findall(r"<text[^>]*>(.*?)</text>", raw, re.S))


def referenced() -> set[str]:
    """Figure ids any publication uses: in the body, as a cover in front matter, or inside a generated panel."""
    out: set[str] = set()
    for src in (HERE / "docs" / "source").rglob("*"):
        if src.suffix not in (".md", ".json"):
            continue
        text = src.read_text(errors="replace")
        out |= set(re.findall(r"::: figure (f\d+[a-z]?)", text))
        out |= set(re.findall(r"^cover: (f\d+[a-z]?)", text, re.M))
        out |= set(re.findall(r'"figure"\s*:\s*"(f\d+[a-z]?)"', text))
    for claims in [POC / "docs" / "claims.yaml"]:
        if claims.exists():
            for field in re.findall(r"figure: (.+)", claims.read_text()):
                out |= set(re.findall(r"f\d+[a-z]?", field))
    return out


def main() -> int:
    manifest = json.loads((HERE / "diagrams" / "manifest.json").read_text())
    figures = manifest["figures"]
    run_id = (POC / "runs" / "PUBLISHED").read_text().strip()
    measured, constants, refs = facts(), incident_constants(), referenced()
    fails: list[str] = []

    for fid, fig in figures.items():
        for kind, ext in KINDS.items():
            stated = fig.get("files", {}).get(kind)
            path = HERE / stated if stated else PREMIUM / ext / f"{fid}.{ext}"
            if not path.exists():
                fails.append(f"{fid}: missing {kind} at {path.relative_to(HERE)}")
            elif stated and Path(stated).name != f"{fid}.{ext}":
                fails.append(f"{fid}: {kind} filename is {Path(stated).name}, expected {fid}.{ext}")

    for fid in sorted(refs - set(figures)):
        fails.append(f"a publication references {fid}, which the manifest does not have")
    for fid in sorted(set(figures) - refs):
        fails.append(f"{fid} is in the manifest but no publication references it")

    counts = {"traceable": 0, "structural": 0, "incident": 0, "raw": 0}
    for fid in sorted(figures):
        svg = PREMIUM / "svg" / f"{fid}.svg"
        if not svg.exists():
            continue
        text = re.sub(r"\b\d+\.\d+(?:\.\d+)+\b", " ", svg_text(svg))   # versions: mcp 2.2.0, ORM 6.4.1
        raw_corpus = source_numbers(figures[fid])
        for other in set(re.findall(r"\b20\d\d-\d\d-\d\d[\w-]*", text)) - {run_id, f"{run_id}-replay"}:
            fails.append(f"{fid}: names run {other}, not the published {run_id}")
        for m in re.finditer(r"(?<![\w.:/-])\d[\d,]*(?:\.\d+)?", text):
            token = m.group(0).rstrip(".")
            if token in measured:
                counts["traceable"] += 1
            elif token in STRUCTURAL:
                counts["structural"] += 1
            elif token in constants or token.replace(",", "") in constants:
                counts["incident"] += 1
            elif token in raw_corpus:
                counts["raw"] += 1
            else:
                near = text[max(0, m.start() - 45):m.end() + 25].replace("\n", " ")
                fails.append(f"{fid}: {token} is not in facts.json, the frozen inputs or STRUCTURAL — …{near}…")
        if "--list" in sys.argv:
            print(f"  {fid}: {len(set(re.findall(r'\\d[\\d,.]*', text)))} distinct number(s)")

    print(f"{len(figures)} figures · {counts['traceable']} number(s) traced to facts.json, {counts['raw']} to the "
          f"raw records each figure cites, {counts['structural']} structural, {counts['incident']} from the frozen incident")
    for f in fails:
        print("FAIL", f)
    print(f"{len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
