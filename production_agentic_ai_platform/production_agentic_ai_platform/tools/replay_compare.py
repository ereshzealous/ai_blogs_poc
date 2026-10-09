"""The replay record of a run (Proof Contract §6): the run against a second, independent run of the same code.

    uv run python tools/replay_compare.py <run> [--replay DIR] [--out FILE]
        -> evidence/runs/<run>/replay.json   (default: compares raw/ with replay/raw/)
    uv run python tools/replay_compare.py <run> --previous <old-run>
        -> evidence/runs/<run>/previous-run-comparison.json   (the published run it would replace, against it)

Rows, each classified by evidence_kit.proof.compare_rows:

  checks    every harness check: its verdict and its observed value must be equal (measured)
  ids       the content-derived identifiers (R1's workflow, digest, approval, decision, capability, idempotency key,
            rollback, policy and bundle versions; R3's approved and tampered digests): must be equal (measured)
  volatile  what a second run cannot reproduce: R1's trace id, the run's timestamps, process ids, wall-clock time (volatile)

Level: EXACT when every row is deterministically equal, SEMANTIC when only volatile rows differ, and not equivalent
when any check or identifier differs. The models are recorded tapes: no model output is regenerated (MODEL_OUTPUT_VARIATION
cannot occur), and the comparison says so.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor"))
sys.path.insert(0, str(ROOT / "tools"))
from evidence_kit import proof  # noqa: E402
from proof_facts import CONTENT_IDS, RUNS, harness_checks, read, scalar  # noqa: E402


def row_sets(res: dict) -> dict[str, dict[str, dict]]:
    F = {e["id"]: e["facts"] for e in res["experiments"]}
    checks = {c["id"]: {"passed": c["passed"], "actual": scalar(c["actual"])} for _, c in harness_checks(res)}
    ids = {f"{e}.{k}": {"value": F[e][k]} for e, k in CONTENT_IDS}
    vol = {"R1.trace_id": {"value": F["R1"]["trace_id"]}, "run.started_at": {"value": res["started_at"]},
           "run.finished_at": {"value": res["finished_at"]}, "run.wall_clock_s": {"value": res["wall_clock_s"]},
           "R9.pids": {"value": F["R9"]["pids"]}}
    return {"checks": checks, "ids": ids, "volatile": vol}


def compare(run_id: str, replay_dir: Path | None = None) -> dict:
    a_dir = RUNS / run_id / "raw"
    b_dir = replay_dir or RUNS / run_id / "replay" / "raw"
    a, b = read(a_dir / "results.json"), read(b_dir / "results.json")
    A, B = row_sets(a), row_sets(b)
    groups, detail, classes = {}, [], {k: 0 for k in proof.CLASSES}
    for g, (measured, volatile) in {"checks": (["passed", "actual"], []), "ids": (["value"], []), "volatile": ([], ["value"])}.items():
        r = proof.compare_rows(A[g], B[g], measured=measured, invariants=[], volatile=volatile)
        groups[g] = {"rows": r["rows"], "deterministic_equivalent": r["classes"]["DETERMINISTIC_EQUIVALENT"], "classes": r["classes"],
                     "only_in_a": r["only_in_a"], "only_in_b": r["only_in_b"], "equivalent": r["equivalent"] and not r["only_in_a"] and not r["only_in_b"]}
        detail += [{"group": g, **d} for d in r["detail"]]
        for k, v in r["classes"].items():
            classes[k] += v
    equivalent = all(g["equivalent"] for g in groups.values())
    level = "EXACT" if equivalent and classes["NONDETERMINISTIC"] == 0 else "SEMANTIC" if equivalent else "NOT EQUIVALENT"
    rel = lambda p: p.resolve().relative_to(ROOT).as_posix()  # noqa: E731
    return {
        "schema": proof.SCHEMA, "kind": "run comparison", "replay": True, "run_id": run_id,
        "a": {"label": "published run", "run": a["run_id"], "path": rel(a_dir)},
        "b": {"label": "replay: a second run of the same code, from a fresh start", "run": b["run_id"], "path": rel(b_dir)},
        "replay_level": level, "equivalent": equivalent, "rows": sum(g["rows"] for g in groups.values()), "classes": classes,
        "groups": groups, "methodology_differences": {},
        "measured_fields": {"checks": ["passed", "actual"], "ids": ["value"]}, "volatile_fields": {"volatile": ["value"]},
        "fresh_model_calls": 0,
        "note": "models are recorded tapes, so no model output is regenerated; trace ids, timestamps, process ids and wall-clock time are "
                "expected to differ and are listed, not compared",
        "detail": detail,
    }


def previous(run_id: str, old_id: str) -> dict:
    """The run that would be replaced, against this one: the checks both have must agree in verdict and value, and the
    content-derived ids must be equal; checks only the new run has are listed (new cases, a methodology change, not a
    regression); the source digests are the methodology difference."""
    a, b = read(RUNS / old_id / "raw" / "results.json"), read(RUNS / run_id / "raw" / "results.json")
    A, B = row_sets(a), row_sets(b)
    out = {"schema": proof.SCHEMA, "kind": "run comparison", "replay": False, "run_id": run_id,
           "a": {"label": "previous published run", "run": old_id}, "b": {"label": "the new run", "run": run_id}, "groups": {}}
    for g, measured in {"checks": ["passed", "actual"], "ids": ["value"]}.items():
        r = proof.compare_rows(A[g], B[g], measured=measured, invariants=[], volatile=[])
        out["groups"][g] = {"rows": r["rows"], "identical": r["classes"]["DETERMINISTIC_EQUIVALENT"],
                            "different": [d["row"] for d in r["detail"] if d["class"] != "DETERMINISTIC_EQUIVALENT"],
                            "only_in_previous": r["only_in_a"], "only_in_new": r["only_in_b"]}
    ea, eb = a["environment"], b["environment"]
    out["methodology_differences"] = {k: [ea.get(k), eb.get(k)] for k in ("source_sha256", "agent_code_sha256") if ea.get(k) != eb.get(k)}
    out["methodology_differences"]["harness_checks"] = [a["totals"]["checks"], b["totals"]["checks"]]
    out["unit_tests"] = [a["unit_tests"]["total"], b["unit_tests"]["total"]]
    out["note"] = "new checks are new cases (a methodology change), not a regression; a check both runs have that differs would be one"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--replay", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--previous")
    o = ap.parse_args()
    if o.previous:
        out = previous(o.run, o.previous)
        dest = o.out or RUNS / o.run / "previous-run-comparison.json"
        dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
        g = out["groups"]
        print(f"{o.previous} → {o.run}: checks both have {g['checks']['identical']}/{g['checks']['rows']} identical "
              f"(different: {g['checks']['different'] or 'none'}); new checks {len(g['checks']['only_in_new'])}; ids {g['ids']['identical']}/{g['ids']['rows']}")
        return 0
    out = compare(o.run, o.replay)
    dest = o.out or RUNS / o.run / "replay.json"
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    g = out["groups"]
    print(f"{out['replay_level']}: checks {g['checks']['deterministic_equivalent']}/{g['checks']['rows']} identical · "
          f"ids {g['ids']['deterministic_equivalent']}/{g['ids']['rows']} identical · volatile {g['volatile']['rows']} rows "
          f"({out['classes']['NONDETERMINISTIC']} differ, as expected) -> {dest.relative_to(ROOT) if dest.is_relative_to(ROOT) else dest}")
    return 0 if out["equivalent"] else 1


if __name__ == "__main__":
    sys.exit(main())
