"""Before/after comparison of two agent runs, built only from their saved rows.

    python -m benchmark.reports.compare_agent_evidence --before <run-id> --after <run-id> [--out DIR]

Both runs must be scored with version 2 (benchmark/agent_runner.py). Writes comparison.md, comparison.json and
evidence-comparison.png / .svg to benchmark/reports/<after-run-id>/ unless --out is given.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from control_plane.paths import REPO_ROOT

RUNS_DIR = REPO_ROOT / "benchmark" / "runs"
SCENARIOS_FILE = REPO_ROOT / "benchmark" / "golden" / "agent_scenarios.yaml"
ARM_LABEL = {"legacy": "Legacy agent", "evidence": "Evidence guard"}
# Validated categorical pair (light surface): the report palette's search orange and control-plane blue.
COLOR = {"before": "#eb6834", "after": "#2a78d6"}
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def load_rows(run_id: str, runs_dir: Path | None = None) -> list[dict[str, Any]]:
    path = Path(runs_dir or RUNS_DIR) / run_id / "agent.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_scenarios(path: Path = SCENARIOS_FILE) -> dict[str, list]:
    return {s["id"]: s["cause_terms"] for s in yaml.safe_load(path.read_text())["scenarios"]}


def load_action_requests(path: Path = SCENARIOS_FILE) -> set[str]:
    return {s["id"] for s in yaml.safe_load(path.read_text())["scenarios"] if s.get("action_request")}


def _summary(rows: list[dict[str, Any]], scenarios: dict[str, list]) -> dict[str, Any]:
    needs_cause = [r for r in rows if scenarios.get(r["scenario_id"])]
    remediated = [r for r in rows if r.get("remediation_executed")]
    n = len(rows)
    return {
        "guard": rows[0].get("guard") if rows else None,
        "discovery": rows[0].get("discovery") or "v1" if rows else None,
        "scenarios": n,
        "strict_passes": sum(bool(r["task_success"]) for r in rows),
        "diagnoses_required": len(needs_cause),
        "supported_diagnoses": sum(bool(r.get("supported_diagnosis")) and bool(r.get("cause_identified")) for r in needs_cause),
        "remediations_performed": len(remediated),
        "verified_remediations": sum(bool(r.get("verified_after_rollback")) for r in remediated),
        "unsafe_writes": sum(len(r.get("unsafe_executed_tools") or []) for r in rows),
        "unsupported_claims": sum(len(r.get("unsupported_claims") or []) for r in rows),
        "invalid_calls": sum(int(r.get("invalid_calls") or 0) for r in rows),
        "guard_blocks": sum(int(r.get("guard_blocks") or 0) for r in rows),
        "mean_prompt_tokens": round(sum(r.get("prompt_tokens") or 0 for r in rows) / n) if n else None,
        "mean_wall_s": round(sum(r.get("wall_ms") or 0 for r in rows) / n / 1000, 1) if n else None,
    }


def _scenario_cell(r: dict[str, Any] | None, action_request: bool = False) -> str:
    if r is None:
        return "not run"
    parts = ["pass" if r["task_success"] else "fail"]
    if r.get("cause_identified") is not None:
        parts.append("diagnosis supported" if r.get("cause_identified") else "diagnosis not supported")
    if r.get("remediation_executed"):
        parts.append("fix verified" if r.get("verified_after_rollback") else "fix not verified")
    elif action_request:
        parts.append("no fix performed")
    if r.get("unsafe_executed_tools"):
        parts.append(f"unsafe: {', '.join(r['unsafe_executed_tools'])}")
    if r.get("unsupported_claims"):
        parts.append(f"unsupported: {'; '.join(r['unsupported_claims'])}")
    return " · ".join(parts)


def compare(before: list[dict[str, Any]], after: list[dict[str, Any]], scenarios: dict[str, list],
            actions: set[str] = frozenset()) -> dict[str, Any]:
    for label, rows in (("before", before), ("after", after)):
        versions = {r.get("scoring_version") for r in rows}
        if versions != {2}:
            raise ValueError(f"{label} run has scoring version {sorted(map(str, versions))}; only version-2 scores are comparable")
    catalogs = sorted({r["catalog"] for r in before} | {r["catalog"] for r in after})
    result: dict[str, Any] = {"catalogs": {}, "scenarios": {}}
    for cat in catalogs:
        b = [r for r in before if r["catalog"] == cat]
        a = [r for r in after if r["catalog"] == cat]
        result["catalogs"][cat] = {"before": _summary(b, scenarios), "after": _summary(a, scenarios)}
        by_b = {r["scenario_id"]: r for r in b}
        by_a = {r["scenario_id"]: r for r in a}
        result["scenarios"][cat] = [{"scenario": s, "before": _scenario_cell(by_b.get(s), s in actions),
                                     "after": _scenario_cell(by_a.get(s), s in actions)}
                                    for s in sorted(set(by_b) | set(by_a))]
    return result


def _label(summary: dict[str, Any]) -> str | None:
    if summary["guard"] not in ARM_LABEL:
        return None
    return ARM_LABEL[summary["guard"]] + (" + discovery v2" if summary.get("discovery") == "v2" else "")


def _labels(result: dict[str, Any]) -> tuple[str, str]:
    first = next(iter(result["catalogs"].values()))
    b, a = _label(first["before"]), _label(first["after"])
    if b and a and b != a:
        return b, a
    return "Before", "After"


def render_markdown(result: dict[str, Any], before_id: str, after_id: str) -> str:
    lb, la = _labels(result)
    out = ["# Agent evidence comparison", "",
           f"Before: `{before_id}` ({lb.lower()}). After: `{after_id}` ({la.lower()}). Both runs are scored with version 2: "
           "a pass needs a diagnosis joined from the run's own successful tool results, a recovery measured after the fix, "
           "and no unsupported claims in incident fields or the final answer.", ""]
    for cat, arms in result["catalogs"].items():
        b, a = arms["before"], arms["after"]
        frac = lambda x, y: f"{x}/{y}"
        rows = [
            ("Strict workflow passes", frac(b["strict_passes"], b["scenarios"]), frac(a["strict_passes"], a["scenarios"])),
            ("Supported required diagnoses", frac(b["supported_diagnoses"], b["diagnoses_required"]), frac(a["supported_diagnoses"], a["diagnoses_required"])),
            ("Verified fixes, of those performed", frac(b["verified_remediations"], b["remediations_performed"]),
             frac(a["verified_remediations"], a["remediations_performed"])),
            ("Unsafe backend writes", str(b["unsafe_writes"]), str(a["unsafe_writes"])),
            ("Unsupported claims", str(b["unsupported_claims"]), str(a["unsupported_claims"])),
            ("Invalid tool calls", str(b["invalid_calls"]), str(a["invalid_calls"])),
            ("Calls blocked by the evidence guard", str(b["guard_blocks"]), str(a["guard_blocks"])),
            ("Mean input tokens per run", f"{b['mean_prompt_tokens']:,}", f"{a['mean_prompt_tokens']:,}"),
            ("Mean wall time per run", f"{b['mean_wall_s']} s", f"{a['mean_wall_s']} s"),
        ]
        out += [f"## {cat}", "", f"| Metric | {lb} | {la} |", "|---|---:|---:|"]
        out += [f"| {m} | {x} | {y} |" for m, x, y in rows]
        out += ["", f"| Scenario | {lb} | {la} |", "|---|---|---|"]
        out += [f"| {s['scenario']} | {s['before']} | {s['after']} |" for s in result["scenarios"][cat]]
        out.append("")
    out += ["## Limits", "",
            "- Four scenarios per arm, one run each: a demonstration, not a statistic.",
            "- The scorer reuses the guard's diagnosis and recovery checks (agent/evidence.py), so it is not an independent "
            "semantic audit; the ground truth it checks against is read from the scenario data.",
            "- One supported cause (a connection-pool limit reduction) and one model (the run's config.json records it).", ""]
    return "\n".join(out)


def plot(result: dict[str, Any], out_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    lb, la = _labels(result)
    cats = list(result["catalogs"])
    fig, axes = plt.subplots(len(cats), 3, figsize=(12.5, 3.3 * len(cats)), squeeze=False,
                             gridspec_kw={"width_ratios": [2.2, 1, 1]}, facecolor=SURFACE)
    outcome_rows = [("Strict passes", "strict_passes", "scenarios"), ("Supported diagnoses", "supported_diagnoses", "diagnoses_required"),
                    ("Verified fixes", "verified_remediations", "remediations_performed"), ("Unsafe writes", "unsafe_writes", None)]
    h = 0.36
    for row, cat in enumerate(cats):
        arms = result["catalogs"][cat]
        ax = axes[row][0]
        top = max(1, *(arms[k]["scenarios"] for k in ("before", "after")))
        for i, (label, key, total_key) in enumerate(outcome_rows):
            for j, arm in enumerate(("before", "after")):
                s = arms[arm]
                y = i + (j - 0.5) * (h + 0.04)
                ax.barh(y, s[key], height=h, color=COLOR[arm], edgecolor=SURFACE, linewidth=2)
                text = f"{s[key]}/{s[total_key]}" if total_key else str(s[key])
                ax.text(s[key] + top * 0.015, y, text, va="center", fontsize=8.5, color=INK_2)
        ax.set_yticks(range(len(outcome_rows)), [r[0] for r in outcome_rows])
        ax.invert_yaxis()
        ax.set_xlim(0, top * 1.18)
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
        ax.set_title(f"{cat} · scenario outcomes (count)", loc="left", fontsize=10, color=INK)
        for col, (key, title, fmt) in enumerate((("mean_prompt_tokens", "Mean input tokens per run", "{:,.0f}"),
                                                 ("mean_wall_s", "Mean wall time per run (s)", "{:.1f}")), start=1):
            ax2 = axes[row][col]
            values = [arms["before"][key] or 0, arms["after"][key] or 0]
            ax2.bar([0, 1], values, width=0.6, color=[COLOR["before"], COLOR["after"]], edgecolor=SURFACE, linewidth=2)
            for x, v in enumerate(values):
                ax2.text(x, v, fmt.format(v), ha="center", va="bottom", fontsize=8.5, color=INK_2)
            ax2.set_xticks([0, 1], [label.replace(" ", "\n", 1) if " + " not in label else label.replace(" + ", "\n+ ")
                                    for label in (lb, la)], fontsize=8.5)
            ax2.set_ylim(0, max(values + [1]) * 1.18)
            ax2.set_title(title, loc="left", fontsize=10, color=INK)
        for a in axes[row]:
            a.set_facecolor(SURFACE)
            a.tick_params(colors=INK_2, labelsize=8.5)
            a.grid(axis="x" if a is ax else "y", color=GRID, linewidth=0.8)
            a.set_axisbelow(True)
            for side in ("top", "right"):
                a.spines[side].set_visible(False)
            for side in ("left", "bottom"):
                a.spines[side].set_color(GRID)
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLOR[k]) for k in ("before", "after")]
    fig.legend(handles, [lb, la], loc="upper right", ncol=2, frameon=False, fontsize=9, labelcolor=INK)
    fig.text(0.01, 0.005, "Version-2 scoring · one run per scenario · a demonstration, not a statistic", fontsize=8, color=INK_2)
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    with matplotlib.rc_context({"svg.hashsalt": "agent-evidence"}):
        fig.savefig(out_dir / "evidence-comparison.svg", metadata={"Date": None})
    fig.savefig(out_dir / "evidence-comparison.png", dpi=200)
    plt.close(fig)


def write_outputs(result: dict[str, Any], before_id: str, after_id: str, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "comparison.json").write_text(json.dumps({"before": before_id, "after": after_id, **result}, indent=1) + "\n")
    (out_dir / "comparison.md").write_text(render_markdown(result, before_id, after_id))
    plot(result, out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    result = compare(load_rows(args.before), load_rows(args.after), load_scenarios(), load_action_requests())
    out = args.out or REPO_ROOT / "benchmark" / "reports" / args.after
    write_outputs(result, args.before, args.after, out)
    print(f"wrote {out}/comparison.md, comparison.json and evidence-comparison.png/.svg")


if __name__ == "__main__":
    main()
