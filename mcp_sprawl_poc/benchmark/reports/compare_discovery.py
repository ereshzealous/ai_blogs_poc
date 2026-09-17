"""Compare control-plane discovery profiles (v1 against v2 or v3) on saved selection rows.

    python -m benchmark.reports.compare_discovery --published gpt-oss-20b-2026-09-15 \
        --v1 selection-test-v1-2026-09-16 --v2 selection-test-v2-2026-09-16 [--split test] [--out DIR]
    python -m benchmark.reports.compare_discovery --published <run> --v1 <run> --v3 <run> --split holdout

The candidate profile's rows live under the arm key `control_plane_v2` whichever profile it is; labels name the profile.

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
    path = Path(runs_dir or RUNS_DIR) / run_id / "selection.jsonl"
    rows = [r for r in _read_jsonl(path) if r["mode"] == mode]
    if not rows:
        raise FileNotFoundError(f"no {mode} rows in run '{run_id}' ({path}); run "
                                f"`python -m benchmark.runner selection --run-id {run_id} --modes {mode} ...` first")
    rescore_selection(rows)
    return rows


def _rate(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [bool(r[field]) for r in rows if r.get(field) is not None]
    return round(sum(values) / len(values), 4) if values else None


def _mean_tokens(rows: list[dict[str, Any]]) -> float | None:
    """Input tokens per decision, including a discovery rewrite call; rows whose model call failed have no count."""
    counted = [(r["prompt_tokens"] or 0) + (r.get("discovery_prompt_tokens") or 0) for r in rows if r.get("prompt_tokens") is not None]
    return round(sum(counted) / len(counted), 1) if counted else None


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
        "mean_prompt_tokens": _mean_tokens(rows),
        "unsafe_selections": sum(bool(r["unsafe_selection"]) for r in rows),
        "unsafe_executions": sum(bool(r["unsafe_execution"]) for r in rows),
    } | ({"asked": _rate(rows, "asked"),
          "right_without_asking": round(sum(bool(r["capability_correct"]) and not r.get("asked") for r in rows) / n, 4)}
         if any(r.get("asked") is not None for r in rows) else {})


def _mcnemar_exact(fixed: int, broke: int) -> float:
    n = fixed + broke
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(min(fixed, broke) + 1)) / 2 ** n
    return round(min(1.0, 2 * tail), 8)


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
    # the size curve uses the cases present at every plotted catalog, so its points compare the same cases
    sources = profiled or list(arms)
    curve = [c for c in catalogs if c in LADDER and all(any(r["catalog"] == c for r in arms[n]) for n in sources)]
    common_ids: set[str] | None = None
    for cat in curve:
        for name in sources:
            ids = {r["case_id"] for r in arms[name] if r["catalog"] == cat}
            common_ids = ids if common_ids is None else common_ids & ids
    for cat in catalogs:
        by_arm = {name: [r for r in arms[name] if r["catalog"] == cat] for name in (*ARMS, REFERENCE_ARM) if name in arms}
        result["catalogs"][cat] = {name: _summary(rows) for name, rows in by_arm.items() if rows}
        if by_arm.get("control_plane_v1") and by_arm.get("control_plane_v2"):
            result["paired"][cat] = _paired(by_arm["control_plane_v1"], by_arm["control_plane_v2"])
        if cat in curve:
            common = {name: [r for r in rows if r["case_id"] in (common_ids or set())] for name, rows in by_arm.items()}
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


def _labels(candidate: str) -> tuple[dict[str, str], dict[str, str]]:
    return ({**ARM_LABEL, "control_plane_v2": f"Control plane, discovery {candidate}"},
            {**ARM_SHORT, "control_plane_v2": candidate})


def _notes(split: str, candidate: str) -> tuple[str, str, str]:
    """(split note, limits line about the candidate's signals, chart footer)"""
    if candidate == "v2":
        split_note = ("Discovery v2 was tuned on the dev split only; the test split was run once, after the profile was fixed."
                      if split == "test" else
                      "This split includes the dev cases that were used to tune discovery v2, so it shows the tuning evidence, "
                      "not an unbiased estimate.")
        limits = ("- The v2 signals (scope, write intent, operation verb, named identifier) were chosen from dev-split misses. They are "
                  "general registry and schema signals, but a different estate may need different weights.")
        return split_note, limits, "discovery v2 tuned on the dev split only"
    if split in ("holdout", "holdout2"):
        split_note = (f"The held-out cases were written after the published run by a separate agent without access to the failure "
                      f"analysis or the discovery code, and frozen before this run. Both profiles were measured on them once.")
        footer = f"discovery {candidate} measured on held-out cases"
    else:
        split_note = (f"Discovery {candidate} was written after the dev and test failures were analysed, so this split is not an "
                      f"unbiased estimate for it; the holdout split is.")
        footer = f"discovery {candidate} written from analysed dev and test failures"
    if candidate == "v4":
        limits = ("- The v4 changes (a model-written first step and read/write judgement, a collapse of equivalent tools, and v3's "
                  "router and cut) were written after analysing the main set and the first held-out set. For v4, input tokens "
                  "include the rewrite call.")
    else:
        limits = (f"- The {candidate} changes (router vocabulary, a soft read filter, an adaptive top-K) were written from analysed "
                  f"dev and test failures. A different estate may need different vocabulary.")
    return split_note, limits, footer


def _paired_line(p: dict[str, Any], candidate: str = "v2") -> str:
    cap, exact = p["capability"], p["exact"]
    def fmt(value: float) -> str:
        return "p < 0.001" if value < 0.001 else f"p = {value:.2f}"

    return (f"Paired on the same {cap['n']} cases, {candidate} against v1: right capability fixed {cap['fixed']} · broke {cap['broke']} "
            f"(both right {cap['both_right']}, both wrong {cap['both_wrong']}; exact McNemar {fmt(p['capability_mcnemar_p'])}); "
            f"exact tool fixed {exact['fixed']} · broke {exact['broke']} ({fmt(p['exact_mcnemar_p'])}). "
            f"Fixed: {', '.join(p['fixed_cases']) or 'none'}. Broken: {', '.join(p['broken_cases']) or 'none'}.")


def render_markdown(result: dict[str, Any], run_ids: dict[str, str], candidate: str = "v2") -> str:
    label, _ = _labels(candidate)
    split_note, limits, _ = _notes(result["split"], candidate)
    runs = " ".join(f"{label[a]}: `{run_ids[a]}`." for a in (*ARMS, REFERENCE_ARM) if a in run_ids)
    rescored = "the current `cases.yaml`" if not result["split"].startswith("holdout") else "the current case files"
    lines = [
        f"# Discovery {candidate} comparison", "",
        f"Split: **{result['split']}**. {split_note} Every row is rescored with {rescored}.", "",
        f"Runs. {runs}", "",
        f"Control plane v1 and {candidate} ran in the same session with the same model and settings, so they differ only in the "
        "discovery profile. " + (
            "Baseline and tool search come from the published run; the discovery profile does not change them."
            if candidate == "v2" else
            f"Baseline and tool search come from `{run_ids.get('baseline', 'the baseline run')}`; the discovery profile does not "
            "change them."), "",
    ]
    if result["paired"]:
        lines += ["## Summary", "", f"| Catalog | Cases | Baseline | Tool search | Control plane v1 | Control plane {candidate} | "
                  f"{candidate} against v1 |",
                  "|---|---:|---:|---:|---:|---:|---|"]
        for cat, p in result["paired"].items():
            arms = result["catalogs"][cat]
            cells = [_cell(arms[a]["capability_correct"], "pct") if a in arms else "n/a" for a in ARMS]
            lines.append(f"| {cat} | {p['capability']['n']} | {' | '.join(cells)} | "
                         f"fixed {p['capability']['fixed']} · broke {p['capability']['broke']} |")
        lines += ["", "Right capability: the golden tool or an acceptable alternative was called.", ""]
    for cat, arms in result["catalogs"].items():
        names = [a for a in (*ARMS, REFERENCE_ARM) if a in arms]
        extra = [("Asked the user", "asked", "pct"), ("Right without asking", "right_without_asking", "pct")] \
            if any("asked" in arms[a] for a in names) else []
        lines += [f"## {cat}", "", "| Metric | " + " | ".join(label[a] for a in names) + " |",
                  "|---|" + "---:|" * len(names)]
        for row_label, field, kind in (*METRIC_ROWS, *extra):
            lines.append(f"| {row_label} | " + " | ".join(_cell(arms[a].get(field), kind) for a in names) + " |")
        n_note = ", ".join(f"{label[a]} {arms[a]['n']}" for a in names)
        lines += ["", f"Rows: {n_note}."]
        if cat in result["paired"]:
            lines += ["", _paired_line(result["paired"][cat], candidate)]
        lines.append("")
    lines += [
        "## Limits", "",
        "- One model at temperature 0, one run per case: the paired counts show where the two profiles differ, and the "
        "McNemar p-values are per catalog; catalogs share cases, so they are not independent tests.",
        limits,
        f"- Discovery {candidate} changes only what the model is shown. Policy and the gateway are unchanged.",
    ]
    return "\n".join(lines) + "\n"


def plot(result: dict[str, Any], out_dir: Path, candidate: str = "v2") -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _style(plt)
    label, short = _labels(candidate)
    footer = _notes(result["split"], candidate)[2]
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
            ax.plot(xs, ys, color=color, linestyle=style, linewidth=2, solid_capstyle="round", label=label[arm], zorder=3)
            ax.scatter(xs, ys, s=46, color=color if style == "-" else "white", edgecolors=color if style != "-" else "white",
                       linewidths=2, zorder=4)
            ends.append((arm, xs[-1], ys[-1]))
        for (arm, x, y), y_label in zip(ends, spread([y for _, _, y in ends], gap=4.5)):
            ax.annotate(f"{y:.0f}% {short[arm]}", (x, y), xytext=(x * 1.12, y_label), textcoords="data", va="center",
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
    fig.text(0.06, -0.04, f"{result['split']} split · cases evaluable at every size, {n} per point · {footer}",
             fontsize=9.5, color=MUTED)
    _save(fig, out_dir, f"discovery-{candidate}-accuracy")
    plt.close(fig)


def write_outputs(result: dict[str, Any], run_ids: dict[str, str], out_dir: Path, candidate: str = "v2") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"runs": run_ids} | result | ({"candidate": candidate} if candidate != "v2" else {})
    (out_dir / "comparison.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (out_dir / "comparison.md").write_text(render_markdown(result, run_ids, candidate))
    plot(result, out_dir, candidate)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--published", required=True, help="run with baseline and search rows (and the published control plane)")
    parser.add_argument("--v1", required=True, help="control-plane run with --discovery v1")
    candidate = parser.add_mutually_exclusive_group(required=True)
    candidate.add_argument("--v2", help="control-plane run with --discovery v2")
    candidate.add_argument("--v3", help="control-plane run with --discovery v3")
    candidate.add_argument("--v4", help="control-plane run with --discovery v4")
    parser.add_argument("--split", default="test", choices=["test", "dev", "holdout", "holdout2", "all"])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    profile, new_run = next((p, getattr(args, p)) for p in ("v2", "v3", "v4") if getattr(args, p))
    try:
        arms = {"baseline": load_arm(args.published, "baseline"), "search": load_arm(args.published, "search"),
                "control_plane_v1": load_arm(args.v1, "control_plane"), "control_plane_v2": load_arm(new_run, "control_plane")}
    except FileNotFoundError as exc:
        raise SystemExit(f"error: {exc}") from None
    run_ids = {"baseline": args.published, "search": args.published, "control_plane_v1": args.v1, "control_plane_v2": new_run}
    if args.published not in (args.v1, new_run):
        try:
            arms[REFERENCE_ARM] = load_arm(args.published, "control_plane")
            run_ids[REFERENCE_ARM] = args.published
        except FileNotFoundError:
            pass  # the reference column is optional
    for name, expected in (("control_plane_v1", "v1"), ("control_plane_v2", profile)):
        profiles = {r.get("discovery", "v1") for r in arms[name]}
        if profiles != {expected}:
            raise SystemExit(f"error: the --{expected} run has discovery profiles {sorted(map(str, profiles))}")
    out = args.out or REPORTS_DIR / new_run
    write_outputs(compare(arms, args.split), run_ids, out, profile)
    print(f"wrote {out}/comparison.md, comparison.json and discovery-{profile}-accuracy.png/.svg")


if __name__ == "__main__":
    main()
