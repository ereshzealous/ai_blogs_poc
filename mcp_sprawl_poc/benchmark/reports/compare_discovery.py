"""Compare control-plane discovery profiles (v1, v2) on saved selection rows.

    python -m benchmark.reports.compare_discovery --published gpt-oss-20b-2026-09-15 \
        --v1 selection-test-v1-2026-09-16 --v2 selection-test-v2-2026-09-16 [--split test] [--out DIR]

Baseline and tool search come from the published run: the discovery profile does not change what they show. Control
plane v1 and v2 come from runs made in the same session with the same model, so that pair differs only in the discovery
profile; the published control-plane rows are shown alongside as a reproducibility check. Every row is rescored with the
current cases.yaml (benchmark/reports/build_report.py). Discovery v2 was tuned on the dev split, so report the test split.
"""

from __future__ import annotations

import argparse
import json
from math import comb
from pathlib import Path
from typing import Any

from benchmark.evaluator.metrics import wilson
from benchmark.reports.build_report import (AXIS, INK, INK2, LADDER, MODE_COLOR, MUTED, REPORTS_DIR, RUNS_DIR, SIZES, _pct,
                                            _read_jsonl, _save, _style, rescore_selection)

ARMS = ("baseline", "search", "control_plane_v1", "control_plane_v2")
REFERENCE_ARM = "control_plane_v1_published"
ARM_LABEL = {"baseline": "Baseline (all tools)", "search": "Tool search", REFERENCE_ARM: "Control plane v1, published run",
             "control_plane_v1": "Control plane, discovery v1", "control_plane_v2": "Control plane, discovery v2"}
# The two profiles share the control plane's validated blue and differ by line style; no new hue is introduced.
ARM_STYLE = {"baseline": (MODE_COLOR["baseline"], "-"), "search": (MODE_COLOR["search"], "-"),
             "control_plane_v1": (MODE_COLOR["control_plane"], "--"), "control_plane_v2": (MODE_COLOR["control_plane"], "-")}
ARM_SHORT = {"baseline": "all tools", "search": "search", "control_plane_v1": "v1", "control_plane_v2": "v2"}
CATALOG_ORDER = LADDER + ["low_overlap_100", "high_overlap_100"]


def load_arm(run_id: str, mode: str, runs_dir: Path | None = None) -> list[dict[str, Any]]:
    rows = [r for r in _read_jsonl(Path(runs_dir or RUNS_DIR) / run_id / "selection.jsonl") if r["mode"] == mode]
    rescore_selection(rows)
    return rows


def _rate(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [bool(r[field]) for r in rows if r.get(field) is not None]
    return round(sum(values) / len(values), 4) if values else None


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    right = sum(bool(r["capability_correct"]) for r in rows)
    low, high = wilson(right, n)
    return {
        "n": n,
        "exact": _rate(rows, "exact"),
        "capability_correct": _rate(rows, "capability_correct"),
        "capability_ci": [round(low, 4), round(high, 4)],
        "valid_call": _rate(rows, "valid_call"),
        "golden_in_prompt": _rate(rows, "golden_in_prompt"),
        "mean_prompt_tokens": round(sum(r.get("prompt_tokens") or 0 for r in rows) / n, 1) if n else None,
        "unsafe_selections": sum(bool(r["unsafe_selection"]) for r in rows),
        "unsafe_executions": sum(bool(r["unsafe_execution"]) for r in rows),
    }


def _mcnemar_exact(fixed: int, broke: int) -> float:
    n = fixed + broke
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(min(fixed, broke) + 1)) / 2 ** n
    return round(min(1.0, 2 * tail), 4)


def _paired(v1: list[dict[str, Any]], v2: list[dict[str, Any]]) -> dict[str, Any]:
    a, b = {r["case_id"]: r for r in v1}, {r["case_id"]: r for r in v2}
    common = sorted(set(a) & set(b))
    outcome = {(False, True): "fixed", (True, False): "broke", (True, True): "both_right", (False, False): "both_wrong"}
    out: dict[str, Any] = {}
    for field, key in (("capability_correct", "capability"), ("exact", "exact")):
        counts = {"n": len(common), "fixed": 0, "broke": 0, "both_right": 0, "both_wrong": 0}
        for case in common:
            counts[outcome[(bool(a[case][field]), bool(b[case][field]))]] += 1
        out[key] = counts
        out[f"{key}_mcnemar_p"] = _mcnemar_exact(counts["fixed"], counts["broke"])
    out["fixed_cases"] = [c for c in common if not a[c]["capability_correct"] and b[c]["capability_correct"]]
    out["broken_cases"] = [c for c in common if a[c]["capability_correct"] and not b[c]["capability_correct"]]
    return out


def compare(arms: dict[str, list[dict[str, Any]]], split: str = "test") -> dict[str, Any]:
    arms = {name: [r for r in rows if split == "all" or r["split"] == split] for name, rows in arms.items()}
    profiled = [name for name in ("control_plane_v1", "control_plane_v2") if name in arms]
    present = {r["catalog"] for name in (profiled or list(arms)) for r in arms[name]}
    catalogs = [c for c in CATALOG_ORDER if c in present] + sorted(present - set(CATALOG_ORDER))
    result: dict[str, Any] = {"split": split, "catalogs": {}, "paired": {}, "ladder": {}}
    for cat in catalogs:
        by_arm = {name: [r for r in arms[name] if r["catalog"] == cat] for name in (*ARMS, REFERENCE_ARM) if name in arms}
        result["catalogs"][cat] = {name: _summary(rows) for name, rows in by_arm.items() if rows}
        if by_arm.get("control_plane_v1") and by_arm.get("control_plane_v2"):
            result["paired"][cat] = _paired(by_arm["control_plane_v1"], by_arm["control_plane_v2"])
        if cat in LADDER:
            # cases whose golden tool is in every catalog, so points at different sizes compare the same cases
            common = {name: [r for r in rows if r.get("ladder_subset")] for name, rows in by_arm.items()}
            result["ladder"][cat] = {name: _summary(rows) for name, rows in common.items() if rows}
    return result


def spread(values: list[float], gap: float) -> list[float]:
    """Label positions at least `gap` apart, moving lower labels down; the order of `values` is kept."""
    out = list(values)
    previous = None
    for i in sorted(range(len(values)), key=lambda i: -values[i]):
        if previous is not None and out[i] > previous - gap:
            out[i] = round(previous - gap, 4)
        previous = out[i]
    return out


def _cell(value: Any, kind: str) -> str:
    if value is None:
        return "n/a"
    if kind == "pct":
        return _pct(value)
    if kind == "ci":
        return f"[{100 * value[0]:.0f}, {100 * value[1]:.0f}]"
    if kind == "tokens":
        return f"{value:,.0f}"
    return str(value)


METRIC_ROWS = (("Right tool (exact)", "exact", "pct"), ("Right capability", "capability_correct", "pct"),
               ("Right capability, 95% interval", "capability_ci", "ci"), ("Valid call", "valid_call", "pct"),
               ("Golden tool in the prompt", "golden_in_prompt", "pct"), ("Mean input tokens", "mean_prompt_tokens", "tokens"),
               ("Unsafe selections", "unsafe_selections", "int"), ("Unsafe calls executed", "unsafe_executions", "int"))


def _paired_line(p: dict[str, Any]) -> str:
    cap, exact = p["capability"], p["exact"]
    return (f"Paired on the same {cap['n']} cases, v2 against v1: right capability fixed {cap['fixed']} · broke {cap['broke']} "
            f"(both right {cap['both_right']}, both wrong {cap['both_wrong']}; exact McNemar p = {p['capability_mcnemar_p']:.2f}); "
            f"exact tool fixed {exact['fixed']} · broke {exact['broke']} (p = {p['exact_mcnemar_p']:.2f}). "
            f"Fixed: {', '.join(p['fixed_cases']) or 'none'}. Broken: {', '.join(p['broken_cases']) or 'none'}.")


def render_markdown(result: dict[str, Any], run_ids: dict[str, str]) -> str:
    runs = " ".join(f"{ARM_LABEL[a]}: `{run_ids[a]}`." for a in (*ARMS, REFERENCE_ARM) if a in run_ids)
    if result["split"] == "test":
        split_note = ("Discovery v2 was tuned on the dev split only; the test split was run once, after the profile was fixed.")
    else:
        split_note = ("This split includes the dev cases that were used to tune discovery v2, so it shows the tuning evidence, "
                      "not an unbiased estimate.")
    lines = [
        "# Discovery v2 comparison", "",
        f"Split: **{result['split']}**. {split_note} Every row is rescored with the current `cases.yaml`.", "",
        f"Runs. {runs}", "",
        "Control plane v1 and v2 ran in the same session with the same model and settings, so they differ only in the discovery "
        "profile. Baseline and tool search come from the published run; the discovery profile does not change them.", "",
    ]
    if result["paired"]:
        lines += ["## Summary", "", "| Catalog | Cases | Baseline | Tool search | Control plane v1 | Control plane v2 | v2 against v1 |",
                  "|---|---:|---:|---:|---:|---:|---|"]
        for cat, p in result["paired"].items():
            arms = result["catalogs"][cat]
            cells = [_cell(arms[a]["capability_correct"], "pct") if a in arms else "n/a" for a in ARMS]
            lines.append(f"| {cat} | {p['capability']['n']} | {' | '.join(cells)} | "
                         f"fixed {p['capability']['fixed']} · broke {p['capability']['broke']} |")
        lines += ["", "Right capability: the golden tool or an acceptable alternative was called.", ""]
    for cat, arms in result["catalogs"].items():
        names = [a for a in (*ARMS, REFERENCE_ARM) if a in arms]
        lines += [f"## {cat}", "", "| Metric | " + " | ".join(ARM_LABEL[a] for a in names) + " |",
                  "|---|" + "---:|" * len(names)]
        for label, field, kind in METRIC_ROWS:
            lines.append(f"| {label} | " + " | ".join(_cell(arms[a][field], kind) for a in names) + " |")
        n_note = ", ".join(f"{ARM_LABEL[a]} {arms[a]['n']}" for a in names)
        lines += ["", f"Rows: {n_note}."]
        if cat in result["paired"]:
            lines += ["", _paired_line(result["paired"][cat])]
        lines.append("")
    lines += [
        "## Limits", "",
        "- One model at temperature 0, one run per case: the paired counts show where the two profiles differ, and the "
        "McNemar p-values are per catalog; catalogs share cases, so they are not independent tests.",
        "- The v2 signals (scope, write intent, operation verb, named identifier) were chosen from dev-split misses. They are "
        "general registry and schema signals, but a different estate may need different weights.",
        "- Discovery v2 changes only what the model is shown. Policy and the gateway are unchanged.",
    ]
    return "\n".join(lines) + "\n"


def plot(result: dict[str, Any], out_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _style(plt)
    ladder = [(c, s) for c, s in zip(LADDER, SIZES) if c in result["ladder"]]
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8), sharey=True)
    for ax, field, title in ((axes[0], "exact", "Exact tool accuracy"), (axes[1], "capability_correct", "Capability accuracy")):
        ends = []
        for arm in ARMS:
            points = [(s, 100 * result["ladder"][c][arm][field]) for c, s in ladder
                      if arm in result["ladder"][c] and result["ladder"][c][arm][field] is not None]
            if not points:
                continue
            xs, ys = zip(*points)
            color, style = ARM_STYLE[arm]
            ax.plot(xs, ys, color=color, linestyle=style, linewidth=2, solid_capstyle="round", label=ARM_LABEL[arm], zorder=3)
            ax.scatter(xs, ys, s=46, color=color if style == "-" else "white", edgecolors=color if style != "-" else "white",
                       linewidths=2, zorder=4)
            ends.append((arm, xs[-1], ys[-1]))
        for (arm, x, y), y_label in zip(ends, spread([y for _, _, y in ends], gap=4.5)):
            ax.annotate(f"{y:.0f}% {ARM_SHORT[arm]}", (x, y), xytext=(x * 1.12, y_label), textcoords="data", va="center",
                        fontsize=10.5, color=INK2)
        ax.set_xscale("log")
        ax.set_xticks([s for _, s in ladder])
        ax.set_xticklabels([str(s) for _, s in ladder])
        ax.minorticks_off()
        ax.set_xlim(min((s for _, s in ladder), default=10) * 0.8, max((s for _, s in ladder), default=500) * 2.6)
        ax.set_ylim(0, 104)
        ax.set_xlabel("Tools in catalog (log scale)")
        ax.set_title(title, loc="left", fontsize=13, color=INK)
        ax.spines["left"].set_color(AXIS)
    axes[0].set_ylabel(f"{result['split'].capitalize()} cases (%)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", ncol=4, bbox_to_anchor=(0.06, 1.04), fontsize=10.5)
    sizes = {arms[a]["n"] for arms in result["ladder"].values() for a in arms}
    n = f"n = {sizes.pop()}" if len(sizes) == 1 else f"n = {min(sizes)}–{max(sizes)}"
    fig.text(0.06, -0.04, f"{result['split']} split · cases evaluable at every size, {n} per point · "
             "discovery v2 tuned on the dev split only", fontsize=9.5, color=MUTED)
    _save(fig, out_dir, "discovery-v2-accuracy")
    plt.close(fig)


def write_outputs(result: dict[str, Any], run_ids: dict[str, str], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "comparison.json").write_text(json.dumps({"runs": run_ids} | result, indent=2, sort_keys=True) + "\n")
    (out_dir / "comparison.md").write_text(render_markdown(result, run_ids))
    plot(result, out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--published", required=True, help="run with baseline and search rows (and the published control plane)")
    parser.add_argument("--v1", required=True, help="control-plane run with --discovery v1")
    parser.add_argument("--v2", required=True, help="control-plane run with --discovery v2")
    parser.add_argument("--split", default="test", choices=["test", "dev", "all"])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    arms = {"baseline": load_arm(args.published, "baseline"), "search": load_arm(args.published, "search"),
            "control_plane_v1": load_arm(args.v1, "control_plane"), "control_plane_v2": load_arm(args.v2, "control_plane")}
    run_ids = {"baseline": args.published, "search": args.published, "control_plane_v1": args.v1, "control_plane_v2": args.v2}
    if args.published not in (args.v1, args.v2):
        arms[REFERENCE_ARM] = load_arm(args.published, "control_plane")
        run_ids[REFERENCE_ARM] = args.published
    for name in ("control_plane_v1", "control_plane_v2"):
        profiles = {r.get("discovery", "v1") for r in arms[name]}
        if profiles != {name[-2:]}:
            raise SystemExit(f"--{name[-2:]} run has discovery profiles {sorted(map(str, profiles))}")
    out = args.out or REPORTS_DIR / args.v2
    write_outputs(compare(arms, args.split), run_ids, out)
    print(f"wrote {out}/comparison.md, comparison.json and discovery-v2-accuracy.png/.svg")


if __name__ == "__main__":
    main()
