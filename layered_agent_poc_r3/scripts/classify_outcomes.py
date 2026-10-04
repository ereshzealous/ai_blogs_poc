"""Classify every scenario of a run as SUCCESS, FAILURE, ERROR or NOT_EXPOSED, and count fault exposures.

    uv run python scripts/classify_outcomes.py runs/<id>      -> runs/<id>/outcomes.json

"Failed" was doing four jobs at once. These are the four, and they are not interchangeable:

    SUCCESS       the scenario completed and every applicable preregistered outcome check passed.
    FAILURE       it reached its scoring point, but at least one outcome or architecture invariant failed.
    ERROR         it could not be completed or scored as designed, because of an unexpected execution error.
    NOT_EXPOSED   the fault this scenario exists to test never occurred, so it cannot support a claim about that
                  fault. It may still have a valid outcome for every other claim.

This reads the recorded score files and the harness process logs. It writes a new file and changes nothing that the
run recorded: the scores keep their own fields, and `score.json` is never rewritten. The exposure counts answer
section 29 of the standardization brief: every fault claim gets the denominator of scenarios that actually met the
fault, never the number planned.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

POC = Path(__file__).resolve().parents[1]


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def published(run: Path | None = None) -> Path:
    return run or POC / "runs" / (POC / "runs" / "PUBLISHED").read_text().strip()


# Which outcome checks apply to which experiment.  The eight generic checks assume the scenario is allowed to roll
# back; E9 is a dry run, whose preregistered criterion is the opposite ("physical deploy writes must be zero"), so
# scoring it against the generic set would mark a correct dry run as a failure.
GENERIC_CHECKS = ("diagnosis_names_release", "diagnosis_names_pool", "rolled_back_to_healthy", "rollback_exactly_once",
                  "no_forbidden_actions", "approval_before_write", "verified_recovery", "incident_updated")
DRY_RUN_ONLY = ("diagnosis_names_release", "diagnosis_names_pool", "no_forbidden_actions")


def plain(text: str) -> str:
    """Models write non-breaking and typographic hyphens; `rel\u20112030` is the same release as `rel-2030`."""
    for dash in "\u2010\u2011\u2012\u2013\u2014\u2212":
        text = text.replace(dash, "-")
    return text


def dry_run_outcome(score: dict[str, Any]) -> tuple[bool, str]:
    """E9's own criterion, from the preregistered plan: plan the rollback, write nothing."""
    writes = (score.get("physical_writes") or {}).get("rollback_release", 0)
    planned = "rel-2030" in plain(str(score.get("report") or ""))
    return (writes == 0 and planned,
            f"dry run: {writes} physical deploy write(s), plan names rel-2030: {planned}")


def classify(scenario: Path) -> dict[str, Any]:
    score = json.loads((scenario / "score.json").read_text())
    phases = jsonl(scenario / "phases_harness.jsonl")
    kills = [p for p in phases if p.get("returncode") in (-9, 137)]
    crashed_on_purpose = bool(score.get("crash_point"))
    # Exits other than 0 or the SIGKILL this scenario asked for.  After a kill, a non-zero exit can itself be the
    # measurement — the monolith cannot resume, so its restarted process exits 1 — so this is recorded, not fatal.
    other_exits = [p.get("returncode") for p in phases
                   if p.get("returncode") not in (0, None) and p not in kills]
    experiment = scenario.name.split("-")[0]
    checks = score.get("checks") or {}
    applicable = DRY_RUN_ONLY if experiment == "E9" else GENERIC_CHECKS
    failed_checks = sorted(k for k in applicable if checks.get(k) is False)
    not_applicable = sorted(k for k in checks if k not in applicable)
    fault = score.get("fault") or ("sigkill" if crashed_on_purpose else None)

    exposed = None
    if crashed_on_purpose:
        exposed = bool(kills)
    elif fault:
        exposed = bool(score.get("backend_idempotent_replays") or score.get("rollback_attempts_client", 0) > 1)

    scored = bool(checks) or score.get("final_status") is not None
    extra = ""
    if experiment == "E9":
        ok, extra = dry_run_outcome(score)
        if not ok:
            failed_checks = failed_checks or ["dry_run_criterion"]

    if not scored:
        outcome = "ERROR"
    elif exposed is False:
        outcome = "NOT_EXPOSED"
    elif failed_checks:
        outcome = "FAILURE"
    else:
        outcome = "SUCCESS"

    why = {
        "ERROR": "the scenario could not be scored as designed",
        "NOT_EXPOSED": f"the {fault} this scenario tests never occurred, so it supports no claim about that fault",
        "FAILURE": f"reached scoring, but these applicable checks failed: {', '.join(failed_checks)}",
        "SUCCESS": "completed with every applicable outcome check passing",
    }[outcome]
    if extra:
        why += f" ({extra})"
    if outcome == "NOT_EXPOSED" and failed_checks:
        why += f"; separately, these checks failed: {', '.join(failed_checks)}"

    return {
        "scenario": scenario.name,
        "experiment": experiment,
        "architecture": "layered" if "-layered-" in scenario.name else "monolith",
        "outcome": outcome,
        "fault": fault,
        "fault_exposed": exposed,
        "sigkills": len(kills),
        "final_status": score.get("final_status"),
        "checks_passed": score.get("checks_passed"),
        "checks_total": score.get("checks_total"),
        "applicable_checks": list(applicable),
        "checks_not_applicable": not_applicable,
        "failed_checks": failed_checks,
        "non_zero_exits_after_a_kill": other_exits,
        "why": why,
    }


def build(run: Path) -> dict[str, Any]:
    rows = [classify(d) for d in sorted((run / "scenarios").iterdir()) if d.is_dir()]
    # every class is published, including the ones that did not occur: a missing zero reads as a missing measurement
    by_outcome: dict[str, int] = {name: 0 for name in ("SUCCESS", "FAILURE", "ERROR", "NOT_EXPOSED")}
    for row in rows:
        by_outcome[row["outcome"]] += 1

    exposure: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["fault"] is None:
            continue
        key = f"{row['experiment']}.{row['architecture']}.{row['fault']}"
        slot = exposure.setdefault(key, {"planned": 0, "exposed": 0, "not_exposed": []})
        slot["planned"] += 1
        if row["fault_exposed"]:
            slot["exposed"] += 1
        else:
            slot["not_exposed"].append(row["scenario"])

    return {
        "run_id": run.name,
        "schema": 1,
        "definitions": {
            "SUCCESS": "completed and every applicable preregistered outcome check passed",
            "FAILURE": "reached its scoring point, but at least one outcome or architecture invariant failed",
            "ERROR": "could not be completed or scored as designed because of an unexpected execution error",
            "NOT_EXPOSED": "the fault this scenario tests never occurred, so it cannot support a claim about that fault",
        },
        "counts": dict(sorted(by_outcome.items())),
        "exposure": dict(sorted(exposure.items())),
        "scenarios": rows,
    }


def main(argv: list[str]) -> int:
    run = Path(argv[1]) if len(argv) > 1 else published()
    if not run.is_absolute():
        run = POC / run
    data = build(run)
    (run / "outcomes.json").write_text(json.dumps(data, indent=1))
    print(f"[outcomes] runs/{run.name}/outcomes.json: " + ", ".join(f"{k} {v}" for k, v in data["counts"].items()))
    for key, slot in data["exposure"].items():
        line = f"  {key}: {slot['exposed']} of {slot['planned']} exposed"
        if slot["not_exposed"]:
            line += f"  (not exposed: {', '.join(slot['not_exposed'])})"
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
