"""Every arm of a measurement side by side: the baseline, tool search and each control-plane profile.

    python -m benchmark.reports.profile_summary --split holdout2 --out benchmark/reports/<name> \\
        --arm "Baseline (all tools)=<run>:baseline" --arm "Tool search=<run>:search" \\
        --arm "Control plane v1=<run>:control_plane" --arm "Control plane v4=<run>:control_plane" ...

Rows are rescored with the current case files (benchmark/reports/build_report.py). Input tokens include a
discovery rewrite call when a profile makes one. For an arm that may ask the user, "right without asking" counts only
the cases the model got right on its own.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from benchmark.reports.build_report import AXIS, INK, INK2, LADDER, MODE_COLOR, MUTED, SIZES, _save, _style
from benchmark.reports.compare_discovery import CATALOG_ORDER, _cell, _summary, load_arm, spread

# Validated with the dataviz palette validator (light surface): violet, orange, blue, aqua. The control-plane
# profiles share the blue and differ by line style; the arm that may ask the user is aqua and always direct-labelled.
STYLES = [(MODE_COLOR["baseline"], "-"), (MODE_COLOR["search"], "-"), (MODE_COLOR["control_plane"], "--"),
          (MODE_COLOR["control_plane"], ":"), (MODE_COLOR["control_plane"], "-"), ("#1baf7a", "-")]
ROWS = (("Right capability", "capability_correct", "pct"), ("Right tool (exact)", "exact", "pct"),
        ("Valid call", "valid_call", "pct"), ("Golden tool in the prompt", "golden_in_prompt", "pct"),
        ("Mean input tokens per decision", "mean_prompt_tokens", "tokens"), ("Unsafe selections", "unsafe_selections", "int"),
        ("Unsafe calls executed", "unsafe_executions", "int"), ("Asked the user", "asked", "pct"),
        ("Right without asking", "right_without_asking", "pct"))


def parse_arm(text: str) -> tuple[str, str, str]:
    label, sep, source = text.partition("=")
    run, sep2, mode = source.rpartition(":")
    if not (sep and sep2 and label and run and mode):
        raise ValueError(f"expected LABEL=RUN:MODE, got {text!r}")
    return label, run, mode


def summarize(arms: dict[str, list[dict[str, Any]]], split: str) -> dict[str, Any]:
    arms = {label: [r for r in rows if split == "all" or r["split"] == split] for label, rows in arms.items()}
    present = {r["catalog"] for rows in arms.values() for r in rows}
    catalogs = [c for c in CATALOG_ORDER if c in present] + sorted(present - set(CATALOG_ORDER))
    out: dict[str, Any] = {"split": split, "arms": list(arms), "catalogs": {}}
    for cat in catalogs:
        out["catalogs"][cat] = {label: _summary([r for r in rows if r["catalog"] == cat])
                                for label, rows in arms.items() if any(r["catalog"] == cat for r in rows)}
    return out


def render_markdown(result: dict[str, Any], sources: dict[str, str]) -> str:
    arms = result["arms"]
    lines = ["# Tool selection by profile", "",
             f"Split: **{result['split']}**. Right capability means the golden tool or an acceptable alternative was called. "
             "Input tokens include a discovery rewrite call when a profile makes one.", ""]
    if sources:
        lines += ["Runs: " + "; ".join(f"{label}: `{src}`" for label, src in sources.items()) + ".", ""]
    lines += ["## Right capability", "", "| Catalog | Cases | " + " | ".join(arms) + " |", "|---|---:|" + "---:|" * len(arms)]
    for cat, by_arm in result["catalogs"].items():
        n = max(s["n"] for s in by_arm.values())
        lines.append(f"| {cat} | {n} | " + " | ".join(_cell(by_arm[a]["capability_correct"], "pct") if a in by_arm else "n/a"
                                                        for a in arms) + " |")
    for cat, by_arm in result["catalogs"].items():
        lines += ["", f"## {cat}", "", "| Metric | " + " | ".join(arms) + " |", "|---|" + "---:|" * len(arms)]
        for label, field, kind in ROWS:
            lines.append(f"| {label} | " + " | ".join(_cell(by_arm[a].get(field), kind) if a in by_arm else "n/a" for a in arms)
                         + " |")
    return "\n".join(lines) + "\n"


def plot(result: dict[str, Any], out_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _style(plt)
    ladder = [(c, s) for c, s in zip(LADDER, SIZES) if c in result["catalogs"]]
    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    ends = []
    for (label, (color, style)) in zip(result["arms"], STYLES):
        points = [(s, 100 * result["catalogs"][c][label]["capability_correct"]) for c, s in ladder if label in result["catalogs"][c]]
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
    ax.set_ylabel(f"{result['split'].capitalize()} cases (%)")
    ax.set_title("Right capability by discovery profile", loc="left", fontsize=13, color=INK)
    ax.spines["left"].set_color(AXIS)
    ax.legend(loc="lower left", fontsize=9.5)
    sizes = sorted({s["n"] for by_arm in result["catalogs"].values() for s in by_arm.values()})
    n = str(sizes[0]) if len(sizes) == 1 else f"{sizes[0]}–{sizes[-1]}"
    fig.text(0.02, -0.03, f"{result['split']} split · n = {n} cases per point", fontsize=9.5, color=MUTED)
    _save(fig, out_dir, "accuracy-by-profile")
    plt.close(fig)


def write_outputs(result: dict[str, Any], sources: dict[str, str], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps({"sources": sources} | result, indent=2, sort_keys=True) + "\n")
    (out_dir / "summary.md").write_text(render_markdown(result, sources))
    plot(result, out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arm", action="append", required=True, help="LABEL=RUN:MODE, in display order (up to 6)")
    parser.add_argument("--split", default="holdout2", choices=["test", "dev", "holdout", "holdout2", "all"])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    arms, sources = {}, {}
    try:
        for text in args.arm:
            label, run, mode = parse_arm(text)
            arms[label] = load_arm(run, mode)
            sources[label] = f"{run}:{mode}"
    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(f"error: {exc}") from None
    write_outputs(summarize(arms, args.split), sources, args.out)
    print(f"wrote {args.out}/summary.md, summary.json and accuracy-by-profile.png/.svg")


if __name__ == "__main__":
    main()
