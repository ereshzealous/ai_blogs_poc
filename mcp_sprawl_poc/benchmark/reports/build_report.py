"""Build the benchmark report from raw run files only.

    python -m benchmark.reports.build_report --run-id <run-id> [--split test]

Reads benchmark/runs/<run-id>/{config.json, selection.jsonl, retrieval.jsonl, agent.jsonl} and writes
benchmark/reports/<run-id>/{summary.json, report.md, charts/*.svg, charts/*.png}. No number in the
report is typed by hand.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmark.evaluator.metrics import aggregate, wilson
from control_plane.paths import REPO_ROOT

RUNS_DIR = REPO_ROOT / "benchmark" / "runs"
REPORTS_DIR = REPO_ROOT / "benchmark" / "reports"
LADDER = ["catalog_10", "catalog_25", "catalog_50", "catalog_100", "catalog_250", "catalog_500"]
SIZES = [10, 25, 50, 100, 250, 500]
MODES = ["baseline", "search", "control_plane"]
MODE_LABEL = {"baseline": "Baseline: all tools", "search": "Tool search (hybrid top-5)", "control_plane": "Capability control plane"}
# Validated with the dataviz palette validator (all-pairs, light surface): CVD dE >= 13, normal-vision dE >= 16, contrast >= 3:1.
MODE_COLOR = {"baseline": "#4a3aa7", "search": "#eb6834", "control_plane": "#2a78d6"}
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"

SEL_RATES = ["exact", "capability_correct", "valid_call", "wrong_tool", "args_correct", "no_call", "hallucinated_tool", "selected_deprecated",
             "selected_unregistered", "trap_selected", "unsafe_selection", "unsafe_execution", "golden_in_prompt", "execution_error"]
SEL_MEANS = ["prompt_tokens", "tool_definition_tokens", "completion_tokens", "total_tokens", "llm_latency_ms", "prompt_eval_ms",
             "discovery_latency_ms", "tools_in_prompt"]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def rescore_selection(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Re-derive every score from the raw selection with the current cases.yaml and registry.

    The model's choice, its arguments and whether the gateway executed the call are raw facts; scores are
    judgements, so they are recomputed here and every row in a report uses one set of golden labels.
    """
    import hashlib

    from benchmark.evaluator.metrics import CASES_FILE, load_cases, retrieval_scores, score_selection
    from control_plane.paths import CATALOG_DIR
    from control_plane.registry.registry import CapabilityRegistry

    cases = {c.id: c for c in load_cases()}
    registry = CapabilityRegistry.load()
    manifests: dict[str, dict[str, dict[str, Any]]] = {}
    changed = 0
    for r in rows:
        if r["catalog"] not in manifests:
            m = json.loads((CATALOG_DIR / f"{r['catalog']}.json").read_text())
            manifests[r["catalog"]] = {f"{t['server']}.{t['name']}": t for t in m["tools"]}
        tools = manifests[r["catalog"]]
        case = cases[r["case_id"]]
        props = tools[r["selected"]]["input_schema"].get("properties", {}) if r["selected"] in tools else {}
        new = score_selection(case, r["selected"], r["arguments"], registry=registry, catalog_tool_ids=set(tools), schema_properties=props)
        new["unsafe_execution"] = bool(new["unsafe_selection"] and r["executed"])
        new["valid_call"] = bool(new["capability_correct"] and not r["execution_error"])
        if r.get("candidates") is not None:
            new |= {f"retrieval_{k}": v for k, v in retrieval_scores(case, r["candidates"], ks=(1, 3, 5)).items()}
            new["golden_in_prompt"] = case.golden_tool in r["candidates"]
        # count only rows whose existing scores changed (keys added by newer evaluator versions do not count)
        if any(k in r and r[k] != v for k, v in new.items() if k != "arg_failures"):
            changed += 1
        r.update(new)
        r["expected_policy"] = case.expected_policy
    return {"cases_sha256": hashlib.sha256(CASES_FILE.read_bytes()).hexdigest(), "rows_rescored": len(rows),
            "rows_with_changed_scores": changed, "derived_metrics_added": ["valid_call"]}


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


# ----------------------------------------------------------------------------------------------
# Summaries
# ----------------------------------------------------------------------------------------------
def summarize_selection(rows: list[dict[str, Any]], split: str) -> dict[str, Any]:
    rows = [r for r in rows if split == "all" or r["split"] == split]
    for r in rows:
        r["args_correct_given_capability"] = r["args_correct"] if r["capability_correct"] else None
    out: dict[str, Any] = {}
    out["ladder_subset"] = aggregate([r for r in rows if r["ladder_subset"] and r["catalog"] in LADDER], ["catalog", "mode"],
                                     SEL_RATES + ["args_correct_given_capability"], SEL_MEANS)
    out["full_set"] = aggregate([r for r in rows if r["catalog"] in LADDER[2:]], ["catalog", "mode"],
                                SEL_RATES + ["args_correct_given_capability"], SEL_MEANS)
    out["overlap"] = aggregate([r for r in rows if r["catalog"] in ("low_overlap_100", "high_overlap_100", "catalog_100")],
                               ["catalog", "mode"], SEL_RATES + ["args_correct_given_capability"], SEL_MEANS)
    out["by_category_500"] = aggregate([r for r in rows if r["catalog"] == "catalog_500"], ["category", "mode"],
                                       ["exact", "capability_correct", "unsafe_selection", "unsafe_execution", "trap_selected"], ["prompt_tokens"])
    # governance metrics (control plane only enforces; other modes observe)
    gov = []
    for mode in MODES:
        m = [r for r in rows if r["mode"] == mode]
        unsafe = [r for r in m if r["unsafe_selection"]]
        golden_calls = [r for r in m if r["exact"]]
        approvals = [r for r in golden_calls if r["expected_policy"] == "REQUIRE_APPROVAL"]
        lo, hi = wilson(sum(not r["executed"] for r in unsafe), len(unsafe))
        gov.append({
            "mode": mode, "n": len(m), "unsafe_selections": len(unsafe),
            "unsafe_executions": sum(r["unsafe_execution"] for r in m),
            "unsafe_blocked_rate": round(sum(not r["executed"] for r in unsafe) / len(unsafe), 4) if unsafe else None,
            "unsafe_blocked_ci": [round(lo, 4), round(hi, 4)] if unsafe else None,
            "policy_decision_accuracy_on_golden_calls": round(sum(r["policy_decision"] == r["expected_policy"] for r in golden_calls) / len(golden_calls), 4) if golden_calls else None,
            "approval_required_accuracy": round(sum(r["policy_decision"] == "REQUIRE_APPROVAL" for r in approvals) / len(approvals), 4) if approvals else None,
            "unsafe_by_kind": _unsafe_kinds(unsafe),
        })
    out["governance"] = gov
    return out


def _unsafe_kinds(unsafe: list[dict[str, Any]]) -> dict[str, int]:
    kinds: dict[str, int] = defaultdict(int)
    for r in unsafe:
        if r["selected_unregistered"]:
            kinds["unregistered (shadow) tool"] += 1
        elif r["selected_deprecated"]:
            kinds["deprecated tool"] += 1
        elif r["capability_correct"]:
            kinds["right tool, wrong environment"] += 1
        else:
            kinds["different side-effecting tool"] += 1
    return dict(kinds)


def summarize_retrieval(rows: list[dict[str, Any]], split: str) -> dict[str, Any]:
    rows = [r for r in rows if split == "all" or r["split"] == split]
    rates = ["recall@1", "recall@3", "recall@5", "recall@10", "recall_any@5", "route_domain_correct", "route_operation_correct", "golden_filtered_out"]
    return {
        "ladder_subset": aggregate([r for r in rows if r["ladder_subset"] and r["catalog"] in LADDER], ["catalog", "mode", "retrieval"], rates, ["mrr", "latency_ms"]),
        "full_set": aggregate([r for r in rows if r["catalog"] in LADDER[2:] + ["low_overlap_100", "high_overlap_100"]],
                              ["catalog", "mode", "retrieval"], rates, ["mrr", "latency_ms"]),
    }


def summarize_agent(rows: list[dict[str, Any]]) -> dict[str, Any]:
    flat = [{k: v for k, v in r.items() if k != "run"} for r in rows]
    for r in flat:
        r["unsafe_executions"] = len(r["unsafe_executed_tools"])
    return {
        "by_catalog_mode": aggregate(flat, ["catalog", "mode"], ["task_success", "no_unsafe_execution", "cause_identified", "final_answer"],
                                     ["tool_calls", "wasted_calls", "unsafe_executions", "prompt_tokens", "completion_tokens", "llm_latency_ms", "wall_ms"]),
        "runs": [{k: r[k] for k in ("catalog", "mode", "scenario_id", "task_success", "cause_identified", "rollback_executed", "incident_updated",
                                    "verified_after_rollback", "no_unsafe_execution", "unsafe_executed_tools", "tool_calls", "wasted_calls",
                                    "prompt_tokens", "stopped")} for r in flat],
    }


# ----------------------------------------------------------------------------------------------
# Charts
# ----------------------------------------------------------------------------------------------
def _style(plt) -> None:
    plt.rcParams.update({
        "font.family": ["Helvetica Neue", "Arial", "DejaVu Sans"], "font.size": 12, "axes.edgecolor": AXIS, "axes.linewidth": 1,
        "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 1,
        "grid.linestyle": "-", "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": "white", "axes.facecolor": "white",
        "legend.frameon": False, "svg.fonttype": "none",
    })


def _save(fig, charts: Path, name: str) -> None:
    import matplotlib

    charts.mkdir(parents=True, exist_ok=True)
    # A fixed id salt and no timestamp make the SVG byte-identical on every rebuild from the same raw rows.
    with matplotlib.rc_context({"svg.hashsalt": "mcp-tool-sprawl"}):
        fig.savefig(charts / f"{name}.svg", bbox_inches="tight", metadata={"Date": None})
    fig.savefig(charts / f"{name}.png", dpi=200, bbox_inches="tight")


def _series(rows: list[dict[str, Any]], mode: str, field: str) -> list[float | None]:
    by = {r["catalog"]: r for r in rows if r["mode"] == mode}
    return [by[c][field] if c in by else None for c in LADDER]


def _line_panel(ax, rows, field, ylabel, percent=True, log_y=False, label_ends=True):
    for mode in MODES:
        ys = _series(rows, mode, field)
        xs = [s for s, y in zip(SIZES, ys) if y is not None]
        ys = [y for y in ys if y is not None]
        if not ys:
            continue
        vals = [100 * y for y in ys] if percent else ys
        ax.plot(xs, vals, color=MODE_COLOR[mode], linewidth=2, solid_capstyle="round", label=MODE_LABEL[mode], zorder=3)
        ax.scatter(xs, vals, s=46, color=MODE_COLOR[mode], edgecolors="white", linewidths=2, zorder=4)
        if label_ends:
            end = vals[-1]
            ax.annotate(f"{end:.0f}%" if percent else f"{end:,.0f}", (xs[-1], end), xytext=(8, 0), textcoords="offset points",
                        va="center", fontsize=11, color=INK2)
    ax.set_xscale("log")
    ax.set_xticks(SIZES)
    ax.set_xticklabels([str(s) for s in SIZES])
    ax.minorticks_off()
    ax.set_xlabel("Tools in catalog (log scale)")
    ax.set_ylabel(ylabel)
    if percent:
        ax.set_ylim(0, 104)
    if log_y:
        ax.set_yscale("log")
    ax.set_xlim(8, 900)


def build_charts(summary: dict[str, Any], charts: Path, meta: dict[str, Any]) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _style(plt)
    made = []
    sel = summary.get("selection") or {}
    foot = f"{meta.get('model', '')} · temperature 0 · test split · n per point in summary.json"

    if sel.get("ladder_subset"):
        rows = sel["ladder_subset"]
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
        _line_panel(axes[0], rows, "exact", "Cases (%)")
        axes[0].set_title("Exact tool accuracy", loc="left", fontsize=13, color=INK)
        _line_panel(axes[1], rows, "capability_correct", "")
        axes[1].set_title("Capability accuracy (golden or acceptable tool)", loc="left", fontsize=13, color=INK)
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper left", ncol=3, bbox_to_anchor=(0.06, 1.04), fontsize=11)
        fig.text(0.06, -0.04, f"{meta.get('model', '')} · temperature 0 · COMMON-CASE SCALE SET · n = {rows[0]['n']} cases evaluable at every size", fontsize=9.5, color=MUTED)
        _save(fig, charts, "selection-accuracy-vs-catalog-size")
        plt.close(fig)
        made.append("selection-accuracy-vs-catalog-size")

        fig, ax = plt.subplots(figsize=(7.2, 4.6))
        _line_panel(ax, rows, "prompt_tokens", "Mean input tokens per decision (log scale)", percent=False, log_y=True, label_ends=False)
        ends = {m: _series(rows, m, "prompt_tokens")[-1] for m in MODES}
        if ends["baseline"] is not None:
            ax.annotate(f"{ends['baseline']:,.0f}", (500, ends["baseline"]), xytext=(8, 0), textcoords="offset points", va="center", fontsize=11, color=INK2)
        if ends["search"] is not None and ends["control_plane"] is not None:
            high = max(ends["search"], ends["control_plane"])
            ax.annotate(f"control plane {ends['control_plane']:,.0f} · search {ends['search']:,.0f}", (500, high), xytext=(-4, 12),
                        textcoords="offset points", ha="right", va="bottom", fontsize=10.5, color=INK2)
        ax.set_ylim(400, 40000)
        ax.set_title("Input tokens per tool-selection decision", loc="left", fontsize=13, color=INK)
        ax.legend(loc="upper left", fontsize=10.5)
        fig.text(0.02, -0.05, f"{meta.get('model', '')} · temperature 0 · COMMON-CASE SCALE SET · n = {rows[0]['n']}", fontsize=9.5, color=MUTED)
        _save(fig, charts, "input-tokens-vs-catalog-size")
        plt.close(fig)
        made.append("input-tokens-vs-catalog-size")

    if sel.get("overlap"):
        rows = {(r["catalog"], r["mode"]): r for r in sel["overlap"]}
        conds = [c for c in ("low_overlap_100", "high_overlap_100") if any((c, m) in rows for m in MODES)]
        if conds:
            fig, ax = plt.subplots(figsize=(7.2, 4.4))
            width = 0.22
            for i, mode in enumerate(MODES):
                xs, vals = [], []
                for j, c in enumerate(conds):
                    if (c, mode) in rows:
                        xs.append(j + (i - 1) * (width + 0.03))
                        vals.append(100 * rows[(c, mode)]["capability_correct"])
                bars = ax.bar(xs, vals, width=width, color=MODE_COLOR[mode], label=MODE_LABEL[mode], zorder=3)
                for b, v in zip(bars, vals):
                    ax.annotate(f"{v:.0f}%", (b.get_x() + b.get_width() / 2, v), xytext=(0, 4), textcoords="offset points",
                                ha="center", fontsize=10.5, color=INK2)
            ax.set_xticks(range(len(conds)))
            ax.set_xticklabels(["100 tools, low semantic overlap", "100 tools, high semantic overlap"][: len(conds)])
            ax.set_ylim(0, 110)
            ax.set_ylabel("Capability accuracy (%)")
            ax.grid(axis="x", visible=False)
            ax.set_title("Same catalog size, different overlap", loc="left", fontsize=13, color=INK)
            ax.legend(loc="upper center", ncol=3, bbox_to_anchor=(0.5, -0.12), fontsize=10)
            fig.text(0.02, -0.14, f"{meta.get('model', '')} · temperature 0 · FULL TEST SET · n = {rows[(conds[0], MODES[0])]['n']} cases per bar", fontsize=9.5, color=MUTED)
            _save(fig, charts, "overlap-at-100-tools")
            plt.close(fig)
            made.append("overlap-at-100-tools")

    gov = sel.get("governance")
    if gov:
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=False)
        for ax, field, title in ((axes[0], "unsafe_selections", "Unsafe tool selections"),
                                 (axes[1], "unsafe_executions", "Unsafe invocations that reached a backend")):
            vals = [next(g[field] for g in gov if g["mode"] == m) for m in MODES]
            bars = ax.barh(range(len(MODES)), vals, height=0.5, color=[MODE_COLOR[m] for m in MODES], zorder=3)
            ax.set_yticks(range(len(MODES)))
            ax.set_yticklabels([MODE_LABEL[m] for m in MODES], color=INK2)
            ax.invert_yaxis()
            ax.grid(axis="y", visible=False)
            for b, v in zip(bars, vals):
                ax.annotate(f"{v}", (b.get_width(), b.get_y() + b.get_height() / 2), xytext=(6, 0), textcoords="offset points",
                            va="center", fontsize=11, color=INK)
            ax.set_xlim(0, max(max(vals) * 1.25, 1))
            ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
            ax.set_xlabel("Count across all test decisions")
            ax.set_title(title, loc="left", fontsize=13, color=INK)
        axes[1].set_yticklabels([])
        fig.text(0.02, -0.04, f"{meta.get('model', '')} · ALL TEST DECISIONS · {gov[0]['n']} per mode · baseline and search execute every call; the control plane enforces policy", fontsize=9.5, color=MUTED)
        _save(fig, charts, "unsafe-selection-vs-execution")
        plt.close(fig)
        made.append("unsafe-selection-vs-execution")

    ret = (summary.get("retrieval") or {}).get("ladder_subset")
    if ret:
        rows = [r for r in ret if r["retrieval"] == "hybrid"]
        fig, ax = plt.subplots(figsize=(7.2, 4.4))
        _line_panel(ax, rows, "recall@5", "Golden tool in top 5 (%)")
        ax.set_title("Retrieval: is the golden tool among the 5 surfaced?", loc="left", fontsize=13, color=INK)
        ax.legend(loc="lower left", fontsize=10.5)
        fig.text(0.02, -0.05, f"hybrid BM25 + embeddings · COMMON-CASE SCALE SET · n = {rows[0]['n']}", fontsize=9.5, color=MUTED)
        _save(fig, charts, "retrieval-recall-at-5")
        plt.close(fig)
        made.append("retrieval-recall-at-5")
    return made


# ----------------------------------------------------------------------------------------------
# Markdown
# ----------------------------------------------------------------------------------------------
def _table(rows: list[dict[str, Any]], cols: list[tuple[str, str, str]]) -> str:
    head = "| " + " | ".join(c[1] for c in cols) + " |\n|" + "---|" * len(cols) + "\n"
    body = []
    for r in rows:
        cells = []
        for key, _, fmt in cols:
            v = r.get(key)
            cells.append("" if v is None else _pct(v) if fmt == "pct" else f"{v:,.0f}" if fmt == "int" else f"{v:,.1f}" if fmt == "f1" else str(v))
        body.append("| " + " | ".join(cells) + " |")
    return head + "\n".join(body) + "\n"


def build_markdown(summary: dict[str, Any], meta: dict[str, Any], charts: list[str]) -> str:
    lines = [f"# Benchmark report · {meta['run_id']}", "", f"Generated from raw run files by `benchmark/reports/build_report.py`. Split: **{meta['split']}**.", ""]
    lines += ["## Configuration", "", "```json", json.dumps(meta.get("config_digest", {}), indent=1), "```", ""]
    sel = summary.get("selection")
    cols = [("catalog", "Catalog", "s"), ("mode", "Mode", "s"), ("n", "n", "s"), ("exact", "Exact", "pct"), ("capability_correct", "Capability", "pct"), ("valid_call", "Valid call", "pct"),
            ("args_correct_given_capability", "Args | capability", "pct"), ("unsafe_selection", "Unsafe sel.", "pct"),
            ("unsafe_execution", "Unsafe exec.", "pct"), ("golden_in_prompt", "Golden in prompt", "pct"),
            ("prompt_tokens", "Input tokens", "int"), ("tool_definition_tokens", "Tool-def tokens", "int"), ("llm_latency_ms", "LLM ms", "int")]
    if sel:
        lines += ["## Tool selection · ladder subset (cases whose golden tool is in catalog_10)", "", _table(sel["ladder_subset"], cols)]
        lines += ["## Tool selection · all cases (catalogs of 50 tools and more)", "", _table(sel["full_set"], cols)]
        lines += ["## Tool selection · semantic overlap at 100 tools", "", _table(sel["overlap"], cols)]
        lines += ["## Tool selection · by category at 500 tools", "",
                  _table(sel["by_category_500"], [("category", "Category", "s"), ("mode", "Mode", "s"), ("n", "n", "s"), ("exact", "Exact", "pct"),
                                                  ("capability_correct", "Capability", "pct"), ("unsafe_selection", "Unsafe sel.", "pct"),
                                                  ("unsafe_execution", "Unsafe exec.", "pct"), ("trap_selected", "Trap chosen", "pct")])]
        lines += ["## Governance", "", "```json", json.dumps(sel["governance"], indent=1), "```", ""]
    ret = summary.get("retrieval")
    if ret:
        rcols = [("catalog", "Catalog", "s"), ("mode", "Mode", "s"), ("retrieval", "Retrieval", "s"), ("n", "n", "s"), ("recall@1", "R@1", "pct"),
                 ("recall@3", "R@3", "pct"), ("recall@5", "R@5", "pct"), ("recall_any@5", "Any@5", "pct"), ("mrr", "MRR", "f1"),
                 ("route_domain_correct", "Route domain", "pct"), ("route_operation_correct", "Route op", "pct"), ("latency_ms", "ms", "f1")]
        lines += ["## Retrieval · ladder subset", "", _table(ret["ladder_subset"], rcols), "## Retrieval · all cases", "", _table(ret["full_set"], rcols)]
    ag = summary.get("agent")
    if ag:
        lines += ["## Multi-step agent", "", _table(ag["by_catalog_mode"], [("catalog", "Catalog", "s"), ("mode", "Mode", "s"), ("n", "Runs", "s"),
                  ("task_success", "Task success", "pct"), ("no_unsafe_execution", "No unsafe exec.", "pct"), ("tool_calls", "Tool calls", "f1"),
                  ("wasted_calls", "Wasted calls", "f1"), ("prompt_tokens", "Input tokens", "int"), ("wall_ms", "Wall ms", "int")]),
                  "", _table(ag["runs"], [("catalog", "Catalog", "s"), ("mode", "Mode", "s"), ("scenario_id", "Scenario", "s"),
                                          ("task_success", "Success", "s"), ("cause_identified", "Cause", "s"), ("rollback_executed", "Rollback", "s"),
                                          ("incident_updated", "Incident updated", "s"), ("unsafe_executed_tools", "Unsafe executed", "s"),
                                          ("tool_calls", "Calls", "s"), ("stopped", "Stopped", "s")])]
    lines += ["## Charts", ""] + [f"![{c}](charts/{c}.svg)" for c in charts]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--split", default="test", choices=["test", "dev", "all"])
    args = parser.parse_args()
    run_dir = RUNS_DIR / args.run_id
    out_dir = REPORTS_DIR / args.run_id
    config = json.loads((run_dir / "config.json").read_text()) if (run_dir / "config.json").exists() else {}
    model = next((c["model"] for sec in ("selection", "agent") for c in config.get(sec, []) if "model" in c), {})
    meta = {"run_id": args.run_id, "split": args.split, "model": f"{model.get('model', '')} ({model.get('quantization', '')})",
            "config_digest": {"model": model, "sections": {k: len(v) for k, v in config.items()},
                              "first_selection_config": {k: v for k, v in (config.get("selection") or [{}])[0].items() if k not in ("argv",)}}}
    summary: dict[str, Any] = {"run_id": args.run_id, "split": args.split}
    sel_rows = _read_jsonl(run_dir / "selection.jsonl")
    if sel_rows:
        summary["scoring"] = rescore_selection(sel_rows)
        summary["selection"] = summarize_selection(sel_rows, args.split)
    ret_rows = _read_jsonl(run_dir / "retrieval.jsonl")
    if ret_rows:
        summary["retrieval"] = summarize_retrieval(ret_rows, args.split)
    agent_rows = _read_jsonl(run_dir / "agent.jsonl")
    if agent_rows:
        summary["agent"] = summarize_agent(agent_rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    charts = build_charts(summary, out_dir / "charts", meta)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    (out_dir / "report.md").write_text(build_markdown(summary, meta, charts))
    print(f"wrote {out_dir}/summary.json, report.md and {len(charts)} charts")


if __name__ == "__main__":
    main()
