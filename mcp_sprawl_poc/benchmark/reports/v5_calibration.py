"""Calibrate discovery v5's confidence thresholds (docs/CAPABILITY_RESOLUTION_V5.md, section 7).

    python -m benchmark.reports.v5_calibration --run <calibration run> --out benchmark/reports/<name> [--write]

The calibration run is discovery v5 with asking switched off on the studied cases. For each risk tier of the
leading capability, the threshold is the smallest margin on the grid at which automatic decisions are at least 99%
precise over at least 20 decisions. A tier with fewer qualifying decisions takes the higher of its own 99% point and
the next stricter tier's threshold; a tier that never reaches 99% always asks. `--write` freezes the result into
`control_plane/discovery/v5_thresholds.py`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from benchmark.evaluator.metrics import wilson
from benchmark.reports.build_report import RUNS_DIR, _read_jsonl, rescore_selection
from control_plane.discovery.resolver import decide
from control_plane.paths import REPO_ROOT
from control_plane.registry.capabilities import CapabilityCatalog

GRID = [round(0.02 * i, 2) for i in range(31)]  # 0.00 .. 0.60
TARGET, MIN_N = 0.99, 20
STRICTEST_FIRST = ("HIGH_RISK_WRITE", "LOW_RISK_WRITE", "READ_ONLY")
THRESHOLDS_FILE = REPO_ROOT / "control_plane" / "discovery" / "v5_thresholds.py"


def load_rows(run_ids: list[str]) -> list[dict[str, Any]]:
    rows = []
    for run in run_ids:
        found = [r for r in _read_jsonl(RUNS_DIR / run / "selection.jsonl") if r.get("v5_first")]
        if not found:
            raise FileNotFoundError(f"no discovery v5 rows in run '{run}'")
        rows += found
    rescore_selection(rows)
    return rows


def _auto(row: dict[str, Any], tier: str, theta: float, catalog: CapabilityCatalog) -> tuple[bool, str | None]:
    d = decide(row["v5_first"], row["selected"], {tier: theta}, catalog=catalog)
    return d.auto and d.tier == tier, d.tier


def _stats(auto_rows: list[dict[str, Any]], tier_rows: list[dict[str, Any]]) -> dict[str, Any]:
    hits = sum(bool(r["capability_correct"]) for r in auto_rows)
    lo, hi = wilson(hits, len(auto_rows))
    return {"automatic": len(auto_rows), "correct": hits, "precision": round(hits / len(auto_rows), 4) if auto_rows else None,
            "precision_ci": [round(lo, 4), round(hi, 4)] if auto_rows else None, "tier_decisions": len(tier_rows),
            "coverage": round(len(auto_rows) / len(tier_rows), 4) if tier_rows else None}


def calibrate(rows: list[dict[str, Any]], catalog: CapabilityCatalog) -> dict[str, Any]:
    tiers = {r["_id"]: decide(r["v5_first"], r["selected"], {}, catalog=catalog).tier for r in rows}
    thresholds: dict[str, float | None] = {}
    result: dict[str, Any] = {}
    for position, tier in enumerate(STRICTEST_FIRST):
        tier_rows = [r for r in rows if tiers[r["_id"]] == tier]
        curve = []
        chosen, rule = None, "no threshold reaches 99% precision: always ask"
        for theta in GRID:
            auto_rows = [r for r in tier_rows if _auto(r, tier, theta, catalog)[0]]
            stats = _stats(auto_rows, tier_rows)
            curve.append({"threshold": theta} | stats)
        qualifying = [c for c in curve if c["precision"] is not None and c["precision"] >= TARGET]
        if qualifying and qualifying[0]["automatic"] >= MIN_N:
            chosen, rule = qualifying[0]["threshold"], "smallest threshold with at least 99% precision over at least 20 decisions"
        elif qualifying and position > 0:
            # never below the tier's own 99% point: the higher of that and the stricter tier's threshold
            stricter = thresholds[STRICTEST_FIRST[position - 1]]
            chosen = None if stricter is None else max(stricter, qualifying[0]["threshold"])
            rule = (f"fewer than {MIN_N} qualifying decisions: the higher of its own 99% threshold "
                    f"and that of {STRICTEST_FIRST[position - 1]}")
        elif qualifying:
            rule = f"fewer than {MIN_N} qualifying decisions and no stricter tier: always ask"
        thresholds[tier] = chosen
        at = next((c for c in curve if c["threshold"] == chosen), None) if chosen is not None else None
        result[tier] = {"threshold": chosen, "rule": rule, "at_threshold": at, "curve": curve}
    # the whole calibration set under the chosen thresholds
    auto_all = [r for r in rows if decide(r["v5_first"], r["selected"], thresholds, catalog=catalog).auto]
    overall = _stats(auto_all, rows)
    return {"thresholds": thresholds, "tiers": result, "overall": overall, "decisions": len(rows),
            "accuracy_without_asking": round(sum(bool(r["capability_correct"]) for r in rows) / len(rows), 4) if rows else None}


def render_markdown(cal: dict[str, Any], runs: list[str]) -> str:
    lines = ["# Discovery v5 calibration", "",
             f"Runs: {', '.join(f'`{r}`' for r in runs)}. {cal['decisions']} decisions with asking switched off; "
             f"{100 * cal['accuracy_without_asking']:.1f}% chose the right capability.", "",
             "| Tier of the leading capability | Decisions | Threshold | Automatic | Precision (95% CI) | Rule |", "|---|---:|---:|---:|---|---|"]
    for tier in STRICTEST_FIRST:
        t = cal["tiers"][tier]
        at = t["at_threshold"]
        n = t["curve"][0]["tier_decisions"]
        if at:
            prec = f"{100 * at['precision']:.1f}% [{100 * at['precision_ci'][0]:.1f}, {100 * at['precision_ci'][1]:.1f}]"
            lines.append(f"| {tier} | {n} | {t['threshold']:.2f} | {at['automatic']} ({100 * at['coverage']:.0f}%) | {prec} | {t['rule']} |")
        else:
            lines.append(f"| {tier} | {n} | none | 0 | n/a | {t['rule']} |")
    o = cal["overall"]
    if o["automatic"]:
        lines += ["", f"Under these thresholds, {o['automatic']} of {cal['decisions']} calibration decisions "
                      f"({100 * o['coverage']:.1f}%) would be automatic, {100 * o['precision']:.1f}% of them right "
                      f"[{100 * o['precision_ci'][0]:.1f}, {100 * o['precision_ci'][1]:.1f}]. The rest would ask."]
    lines += ["", "Precision by threshold, per tier:", ""]
    for tier in STRICTEST_FIRST:
        curve = [c for c in cal["tiers"][tier]["curve"] if c["automatic"]]
        cells = ", ".join(f"{c['threshold']:.2f}: {c['correct']}/{c['automatic']}" for c in curve[::3])
        lines.append(f"- {tier}: {cells or 'no automatic decisions'}")
    return "\n".join(lines) + "\n"


def write_thresholds(cal: dict[str, Any], runs: list[str], path: Path = THRESHOLDS_FILE) -> None:
    summary = {tier: {k: v for k, v in cal["tiers"][tier].items() if k != "curve"} for tier in STRICTEST_FIRST}
    text = (
        '"""Confidence thresholds for discovery v5, one per risk tier of the leading capability.\n\n'
        "Written by `python -m benchmark.reports.v5_calibration` from the calibration runs (docs/CAPABILITY_RESOLUTION_V5.md,\n"
        'section 7) and frozen with the v5 code. None means "not calibrated": that tier always asks.\n"""\n\n'
        f"THRESHOLDS: dict[str, float | None] = {json.dumps(cal['thresholds'])}\n"
        f"CALIBRATION: dict[str, object] = {json.dumps({'runs': runs, 'decisions': cal['decisions'], 'overall': cal['overall'], 'tiers': summary}, indent=4)}\n"
    ).replace("null", "None").replace("true", "True").replace("false", "False")
    path.write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--write", action="store_true", help="freeze the thresholds into control_plane/discovery/v5_thresholds.py")
    args = parser.parse_args()
    rows = load_rows(args.run)
    for i, r in enumerate(rows):
        r["_id"] = i
    cal = calibrate(rows, CapabilityCatalog.load())
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "calibration.json").write_text(json.dumps({"runs": args.run} | cal, indent=2) + "\n")
    (args.out / "calibration.md").write_text(render_markdown(cal, args.run))
    if args.write:
        write_thresholds(cal, args.run)
    print(render_markdown(cal, args.run))


if __name__ == "__main__":
    main()
