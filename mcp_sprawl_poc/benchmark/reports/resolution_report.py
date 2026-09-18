"""Capability-resolution report for held-out set 3: every arm side by side, from saved rows only.

    python -m benchmark.reports.resolution_report --split holdout3 --out benchmark/reports/<name> \\
        --arm "Baseline (all tools)=<run>:baseline" --arm "Search, 7 tools=<run>:search" \\
        --arm "Control plane v4=<run>:control_plane" --arm "Control plane v5=<run>:control_plane" ...

Rows are rescored with the current case files, then scored as in docs/CAPABILITY_RESOLUTION_V5.md, section 6.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from benchmark.evaluator.metrics import load_all_cases
from benchmark.evaluator.resolution import resolution_scores, summarize_resolution
from benchmark.reports.build_report import AXIS, INK, INK2, LADDER, MUTED, SIZES, _save, _style
from benchmark.reports.compare_discovery import CATALOG_ORDER, load_arm, spread
from benchmark.reports.profile_summary import arm_styles, parse_arm
from control_plane.registry.registry import CapabilityRegistry

ROWS = (
    ("Overall capability resolution (clear + ambiguous)", "overall_resolution", "pct"),
    ("Clear requests resolved", "clear_resolution", "pct"),
    ("Ambiguous requests resolved", "ambiguous_resolution", "pct"),
    ("Right tool shown", "right_tool_shown", "pct"),
    ("Automatic coverage", "automatic_coverage", "pct"),
    ("Automatic precision", "automatic_precision", "pct"),
    ("Wrongly confident", "wrongly_confident", "pct"),
    ("Asked the user", "ask_rate", "pct"),
    ("Resolved after asking", "resolved_after_asking", "pct"),
    ("Ambiguous requests asked about", "ambiguous_asked", "pct"),
    ("Lucky guesses on ambiguous requests", "lucky_guesses", "pct"),
    ("Abstentions", "abstentions", "pct"),
    ("Exact tool", "exact_tool", "pct"),
    ("Valid call", "valid_call", "pct"),
    ("Trap requests refused or redirected", "trap_success", "pct"),
    ("Unsafe selections / sent", "unsafe", "pair"),
    ("Wrongly confident, by tier", "wrongly_confident_by_tier", "tiers"),
    ("Mean input tokens per decision", "mean_input_tokens", "int"),
    ("Mean seconds per decision", "mean_case_seconds", "float"),
)


def scored_rows(rows: list[dict[str, Any]], registry: CapabilityRegistry) -> list[dict[str, Any]]:
    cases = {c.id: c for c in load_all_cases()}
    return [r | resolution_scores(r, cases[r["case_id"]], registry=registry) for r in rows]


def summarize(arms: dict[str, list[dict[str, Any]]], split: str, catalogs: list[str] | None = None) -> dict[str, Any]:
    arms = {label: [r for r in rows if (split == "all" or r["split"] == split) and (catalogs is None or r["catalog"] in catalogs)]
            for label, rows in arms.items()}
    present = {r["catalog"] for rows in arms.values() for r in rows}
    catalogs = [c for c in CATALOG_ORDER if c in present] + sorted(present - set(CATALOG_ORDER))
    out: dict[str, Any] = {"split": split, "arms": list(arms), "catalogs": {}}
    for cat in catalogs:
        out["catalogs"][cat] = {label: summarize_resolution([r for r in rows if r["catalog"] == cat])
                                for label, rows in arms.items() if any(r["catalog"] == cat for r in rows)}
    return out


def _cell(summary: dict[str, Any], field: str, kind: str) -> str:
    if kind == "pair":
        return f"{summary['unsafe_selections']} / {summary['unsafe_sent']}"
    value = summary.get(field)
    if kind == "tiers":
        return ", ".join(f"{t.split('_')[0].lower()} {n}" for t, n in value.items()) if value else "none"
    if kind in ("int", "float"):
        return "n/a" if value is None else (f"{value:,}" if kind == "int" else f"{value:.1f}")
    if not value or value["value"] is None:
        return "n/a"
    hits, n = value["count"]
    return f"{100 * value['value']:.1f}% ({hits}/{n})"


def render_markdown(result: dict[str, Any], sources: dict[str, str]) -> str:
    arms = result["arms"]
    lines = ["# Capability resolution by arm", "",
             f"Split: **{result['split']}**. Definitions: `docs/CAPABILITY_RESOLUTION_V5.md`, section 6. Counts are "
             "(hits/decisions); intervals are in `summary.json`.", ""]
    if sources:
        lines += ["Runs: " + "; ".join(f"{label}: `{src}`" for label, src in sources.items()) + ".", ""]
    lines += ["## Overall capability resolution", "", "| Catalog | " + " | ".join(arms) + " |", "|---|" + "---:|" * len(arms)]
    for cat, by_arm in result["catalogs"].items():
        lines.append(f"| {cat} | " + " | ".join(_cell(by_arm[a], "overall_resolution", "pct") if a in by_arm else "n/a"
                                               for a in arms) + " |")
    for cat, by_arm in result["catalogs"].items():
        n = next(iter(by_arm.values()))["n"]
        lines += ["", f"## {cat}", "", f"{n['clear']} clear, {n['ambiguous']} ambiguous and {n['trap']} trap requests.", "",
                  "| Metric | " + " | ".join(arms) + " |", "|---|" + "---:|" * len(arms)]
        for label, field, kind in ROWS:
            lines.append(f"| {label} | " + " | ".join(_cell(by_arm[a], field, kind) if a in by_arm else "n/a" for a in arms) + " |")
    return "\n".join(lines) + "\n"


def plot(result: dict[str, Any], out_dir: Path, sources: dict[str, str]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _style(plt)
    ladder = [(c, s) for c, s in zip(LADDER, SIZES) if c in result["catalogs"]]
    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    ends = []
    for label, (color, style) in zip(result["arms"], arm_styles(result["arms"], sources)):
        points = [(s, 100 * result["catalogs"][c][label]["overall_resolution"]["value"]) for c, s in ladder
                  if label in result["catalogs"][c] and result["catalogs"][c][label]["overall_resolution"]["value"] is not None]
        if not points:
            continue
        xs, ys = zip(*points)
        ax.plot(xs, ys, color=color, linestyle=style, linewidth=2, solid_capstyle="round", label=label, zorder=3)
        ax.scatter(xs, ys, s=46, color=color if style == "-" else "white", edgecolors=color if style != "-" else "white",
                   linewidths=2, zorder=4)
        ends.append((label, xs[-1], ys[-1]))
    for (label, x, y), y_label in zip(ends, spread([y for _, _, y in ends], gap=4.2)):
        ax.annotate(f"{y:.0f}% {label}", (x, y), xytext=(x * 1.12, y_label), textcoords="data", va="center", fontsize=10, color=INK2)
    ax.set_xscale("log")
    ax.set_xticks([s for _, s in ladder])
    ax.set_xticklabels([str(s) for _, s in ladder])
    ax.minorticks_off()
    ax.set_xlim(min((s for _, s in ladder), default=10) * 0.8, max((s for _, s in ladder), default=500) * 4.5)
    ax.set_ylim(0, 104)
    ax.set_xlabel("Tools in catalog (log scale)")
    ax.set_ylabel("Clear and ambiguous requests resolved (%)")
    ax.set_title("Capability resolution by arm", loc="left", fontsize=13, color=INK)
    ax.spines["left"].set_color(AXIS)
    ax.legend(loc="lower left", fontsize=9.5)
    fig.text(0.02, -0.03, f"{result['split']} split · a request counts once, after at most one question", fontsize=9.5, color=MUTED)
    _save(fig, out_dir, "resolution-by-arm")
    plt.close(fig)


def write_outputs(result: dict[str, Any], sources: dict[str, str], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps({"sources": sources} | result, indent=2, sort_keys=True) + "\n")
    (out_dir / "summary.md").write_text(render_markdown(result, sources))
    plot(result, out_dir, sources)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arm", action="append", required=True, help="LABEL=RUN:MODE, in display order")
    parser.add_argument("--split", default="holdout3")
    parser.add_argument("--catalogs", default=None, help="comma-separated catalogs to report (default: every catalog present)")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    registry = CapabilityRegistry.load()
    arms, sources = {}, {}
    try:
        for text in args.arm:
            label, run, mode = parse_arm(text)
            arms[label] = scored_rows(load_arm(run, mode), registry)
            sources[label] = f"{run}:{mode}"
    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(f"error: {exc}") from None
    write_outputs(summarize(arms, args.split, args.catalogs.split(",") if args.catalogs else None), sources, args.out)
    print(f"wrote {args.out}/summary.md, summary.json and resolution-by-arm.png/.svg")


if __name__ == "__main__":
    main()
