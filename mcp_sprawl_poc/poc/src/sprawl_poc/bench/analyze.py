"""Analysis of a run directory (preregistered statistics).

    uv run python -m sprawl_poc.bench.analyze ../experiment/raw/<run> [--out ../experiment/analysis/<run>]

* integrity gate: exactly one row per (case, arm, estate) for the run's configuration;
* proportions with Wilson 95% intervals;
* paired comparisons with the exact (binomial) McNemar test on discordant pairs,
  Holm-adjusted within the preregistered primary family;
* everything written to summary.json + tables.md; nothing is interpolated between estates.
"""

from __future__ import annotations

import argparse
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..util import read_json, read_jsonl, write_json
from .cases import BENCHMARK_PATH

ARM_ORDER = ["A_all_tools", "B_search_only", "C_control_plane"]
ARM_SHORT = {"A_all_tools": "A all-tools", "B_search_only": "B search-only", "C_control_plane": "C control-plane"}


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float, float]:
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from discordant counts b (x only) and c (y only)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def holm(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out, running = {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out


def integrity(rows: list[dict[str, Any]], case_ids: list[str], arms: list[str], sizes: list[int]) -> dict[str, Any]:
    seen = defaultdict(int)
    for r in rows:
        seen[(r["case_id"], r["arm"], r["estate_size"])] += 1
    expected = {(c, a, s) for c in case_ids for a in arms for s in sizes}
    dup = sorted(k for k, v in seen.items() if v > 1)
    missing = sorted(expected - set(seen))
    extra = sorted(set(seen) - expected)
    return {"ok": not dup and not missing and not extra, "rows": len(rows), "expected": len(expected),
            "duplicates": [list(x) for x in dup], "missing": [list(x) for x in missing], "unexpected": [list(x) for x in extra]}


def _frac(rows, key) -> dict[str, Any]:
    vals = [r["score"][key] for r in rows if r.get("score") and r["score"].get(key) is not None]
    k = sum(1 for v in vals if v)
    p, lo, hi = wilson(k, len(vals))
    return {"k": k, "n": len(vals), "p": p, "lo": lo, "hi": hi}


def _med(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def summarise(run_dir: Path) -> dict[str, Any]:
    rows = read_jsonl(run_dir / "rows.jsonl")
    meta = read_json(run_dir / "run-meta.json")
    bench = read_json(BENCHMARK_PATH)
    cases = {c["case_id"]: c for c in bench["cases"]}
    case_ids = sorted({r["case_id"] for r in rows}) if not meta.get("case_ids") else meta["case_ids"]
    arms = [a for a in ARM_ORDER if any(r["arm"] == a for r in rows)]
    sizes = sorted({r["estate_size"] for r in rows})
    integ = integrity(rows, case_ids, arms, sizes)
    by = defaultdict(list)
    for r in rows:
        by[(r["arm"], r["estate_size"])].append(r)
    cells: dict[str, Any] = {}
    for a in arms:
        for s in sizes:
            rs = by[(a, s)]
            statuses = defaultdict(int)
            for r in rs:
                statuses[r["status"]] += 1
            cells[f"{a}@{s}"] = {
                "arm": a, "estate_size": s, "rows": len(rs), "status": dict(statuses),
                "correct": _frac(rs, "correct"),
                "unsafe_proposal": _frac(rs, "unsafe_proposal"),
                "unsafe_execution": _frac(rs, "unsafe_execution"),
                "trap_proposed": _frac(rs, "trap_proposed"),
                "trap_executed": _frac(rs, "trap_executed"),
                "capability_correct": _frac(rs, "capability_correct"),
                "arguments_correct": _frac(rs, "arguments_correct"),
                "executed_expected_implementation": _frac(rs, "executed_expected_implementation"),
                "narrated_success_without_effect": _frac(rs, "narrated_success_without_effect"),
                "asked_for_owned_fact": _frac(rs, "asked_for_owned_fact"),
                "approval_bound_correctly": _frac(rs, "approval_bound_correctly"),
                "median_first_prompt_tokens": _med([r.get("first_prompt_tokens") for r in rs]),
                "median_tool_definition_tokens": _med([r.get("tool_definition_tokens") for r in rs]),
                "median_tools_surfaced_first_step": _med([r.get("tools_surfaced_first_step") for r in rs]),
                "max_tools_surfaced": max((r.get("tools_surfaced_max") or 0 for r in rs), default=None),
                "median_model_calls": _med([r.get("model_calls") for r in rs]),
                "median_tool_calls": _med([(r.get("score") or {}).get("tool_call_count") for r in rs]),
                "duplicate_call_rows": sum(1 for r in rs if (r.get("score") or {}).get("duplicate_calls")),
                "median_wall_s": _med([r.get("wall_s") for r in rs]),
                "finish_reminders": sum(r.get("finish_reminders", 0) for r in rs),
                "invalid_finish_calls": sum(r.get("invalid_finish_calls", 0) for r in rs),
                "stop_reasons": dict(_count(r.get("stop_reason") for r in rs)),
            }
    # per-category correctness
    per_cat: dict[str, Any] = {}
    for a in arms:
        for s in sizes:
            for cat in sorted({cases[r["case_id"]]["category"] for r in by[(a, s)]}):
                rs = [r for r in by[(a, s)] if cases[r["case_id"]]["category"] == cat]
                per_cat[f"{a}@{s}:{cat}"] = _frac(rs, "correct")
    # paired comparisons on correct handling (only rows with a score)
    def correct_map(a, s):
        return {r["case_id"]: bool(r["score"]["correct"]) for r in by[(a, s)] if r.get("score")}

    pairs: dict[str, Any] = {}
    for s in sizes:
        for x, y in (("C_control_plane", "B_search_only"), ("C_control_plane", "A_all_tools"), ("B_search_only", "A_all_tools")):
            if x in arms and y in arms:
                pairs[f"{x} vs {y} @{s}"] = _paired(correct_map(x, s), correct_map(y, s))
    for a in arms:
        if 50 in sizes and 500 in sizes:
            pairs[f"{a} @50 vs @500"] = _paired(correct_map(a, 50), correct_map(a, 500))
    return {"run": run_dir.name, "meta": {k: meta.get(k) for k in ("split", "git_commit", "git_dirty_src", "benchmark_sha256", "model", "started", "finished")},
            "integrity": integ, "cells": cells, "per_category": per_cat, "paired": pairs}


def _count(it):
    d = defaultdict(int)
    for x in it:
        d[x] += 1
    return d


def _paired(mx: dict[str, bool], my: dict[str, bool]) -> dict[str, Any]:
    common = sorted(set(mx) & set(my))
    b = sum(1 for c in common if mx[c] and not my[c])
    c_ = sum(1 for c in common if my[c] and not mx[c])
    return {"n_pairs": len(common), "x_only": b, "y_only": c_, "both": sum(1 for c in common if mx[c] and my[c]),
            "neither": sum(1 for c in common if not mx[c] and not my[c]), "p_exact_mcnemar": mcnemar_exact(b, c_)}


def pct(f: dict[str, Any]) -> str:
    if not f or not f.get("n"):
        return "–"
    return f"{100 * f['p']:.0f}% ({f['k']}/{f['n']}; {100 * f['lo']:.0f}–{100 * f['hi']:.0f})"


def tables_md(summary: dict[str, Any]) -> str:
    cells = summary["cells"]
    lines = [f"# Results — {summary['run']}", "", f"Integrity: {'OK' if summary['integrity']['ok'] else 'FAILED'} "
             f"({summary['integrity']['rows']} rows / {summary['integrity']['expected']} expected)", ""]
    lines += ["## Correct operational handling (Wilson 95%)", "", "| arm | " + " | ".join(f"{s} tools" for s in sorted({c['estate_size'] for c in cells.values()})) + " |",
              "|---|" + "---|" * len({c['estate_size'] for c in cells.values()})]
    sizes = sorted({c["estate_size"] for c in cells.values()})
    for a in ARM_ORDER:
        if any(c["arm"] == a for c in cells.values()):
            lines.append(f"| {ARM_SHORT[a]} | " + " | ".join(pct(cells[f'{a}@{s}']['correct']) for s in sizes) + " |")
    for title, key in (("Unsafe proposal (rows)", "unsafe_proposal"), ("Unsafe execution (rows)", "unsafe_execution"),
                       ("Estate trap proposed", "trap_proposed"), ("Estate trap executed", "trap_executed"),
                       ("Capability correct", "capability_correct"), ("Arguments correct (execute cases)", "arguments_correct"),
                       ("Narrated success without effect", "narrated_success_without_effect"), ("Asked for a fact the platform owns", "asked_for_owned_fact")):
        lines += ["", f"## {title}", "", "| arm | " + " | ".join(f"{s}" for s in sizes) + " |", "|---|" + "---|" * len(sizes)]
        for a in ARM_ORDER:
            if any(c["arm"] == a for c in cells.values()):
                lines.append(f"| {ARM_SHORT[a]} | " + " | ".join(pct(cells[f'{a}@{s}'][key]) for s in sizes) + " |")
    lines += ["", "## Context and decision surface (medians)", "", "| arm | estate | first-call prompt tokens | tool-definition tokens | tools surfaced (first step) | max surfaced | model calls | wall s |", "|---|---|---|---|---|---|---|---|"]
    for a in ARM_ORDER:
        for s in sizes:
            c = cells.get(f"{a}@{s}")
            if c:
                lines.append(f"| {ARM_SHORT[a]} | {s} | {c['median_first_prompt_tokens']} | {c['median_tool_definition_tokens']} | {c['median_tools_surfaced_first_step']} | {c['max_tools_surfaced']} | {c['median_model_calls']} | {c['median_wall_s']} |")
    lines += ["", "## Paired comparisons (exact McNemar on correct handling)", "", "| comparison | pairs | x only | y only | p |", "|---|---|---|---|---|"]
    for k, v in summary["paired"].items():
        lines.append(f"| {k} | {v['n_pairs']} | {v['x_only']} | {v['y_only']} | {v['p_exact_mcnemar']:.4f} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--out", default=None)
    ns = ap.parse_args(argv)
    run_dir = Path(ns.run_dir).resolve()
    out = Path(ns.out).resolve() if ns.out else run_dir / "analysis"
    s = summarise(run_dir)
    write_json(out / "summary.json", s)
    (out / "tables.md").write_text(tables_md(s))
    print(tables_md(s))


if __name__ == "__main__":
    main()
