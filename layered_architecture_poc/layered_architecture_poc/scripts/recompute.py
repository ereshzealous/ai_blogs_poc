"""Recompute the published numbers from the run's raw evidence, independently of the files that produced them.

    uv run python scripts/recompute.py runs/<id>          # print the checks
    (called by scripts/verify_evidence.py, which writes them into runs/<id>/verification.json)

`verify_evidence.py` answers "is this run complete, frozen and self-consistent?" — it rebuilds summary.json from the
score files that produced it. That cannot catch a scorer that was wrong in the same way twice. This module answers a
different question:

    does the raw evidence still say what the published facts say?

So nothing here reads `score.json`, `summary.json` or any experiment result file for the value it is checking. Each
check goes back to the primary records:

    scenarios/<s>/world.db          the simulated systems of record: executions, idempotency keys, running release
    scenarios/<s>/raw/*.jsonl       approvals, processes, model usage, executions as the platform saw them
    scenarios/<s>/tape/*.jsonl      every model request and its answer
    scenarios/<s>/phases_harness.jsonl  the processes the harness started, and how each one ended
    raw/*.jsonl                     the run-wide ledgers: model calls, policy events, workflow events, traces
    diffs/*.diff                    the change experiments, as patches
    tests.junit.xml                 the test run

A check that cannot be recomputed from raw records is reported as such instead of passing on a re-read.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

POC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))

FORBIDDEN_WRITES = ("restart_service", "scale_service", "flush_sessions")
HEALTHY = ("rel-2029", "rel-2030")          # simulated_enterprise/data/inc4917.yaml: healthy_releases
POOL_WORDS = re.compile(r"pool|maximumPoolSize|connection", re.I)


def fact(facts: dict, key: str) -> Any:
    """A published value. facts.json stores every leaf as {"value": ..., "source": ...}."""
    leaf = facts.get(key)
    return leaf.get("value") if isinstance(leaf, dict) and "value" in leaf else leaf


# ---------------------------------------------------------------- raw readers
def jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def world(scenario: Path) -> sqlite3.Connection | None:
    db = scenario / "world.db"
    if not db.exists():
        return None
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def scenarios(run: Path, prefix: str = "") -> list[Path]:
    return sorted(d for d in (run / "scenarios").iterdir() if d.is_dir() and d.name.startswith(prefix))


def arch_of(scenario: Path) -> str:
    return "layered" if "-layered-" in scenario.name else "monolith"


def killed_phases(scenario: Path) -> list[dict]:
    """The harness invocations that ended in a SIGKILL. The exposure record for every crash claim."""
    return [p for p in jsonl(scenario / "phases_harness.jsonl") if p.get("returncode") in (-9, 137)]


def tape_text(scenario: Path) -> str:
    """Every model answer in this scenario, concatenated. The model's own words, as recorded."""
    out = []
    for row in jsonl(scenario / "tape" / "model_tape.jsonl"):
        response = row.get("response")
        out.append(response if isinstance(response, str) else json.dumps(response))
    return "\n".join(out)


# ---------------------------------------------------------------- the checks
Check = tuple[str, bool | None, str]


def e1_outcome_checks(run: Path, facts: dict) -> Check:
    """L1: recompute each E1 outcome from the world database and the tapes, then compare with the scored checks."""
    disagree, counted = [], 0
    for scenario in scenarios(run, "E1"):
        con = world(scenario)
        if con is None:
            continue
        rollbacks = [dict(r) for r in con.execute("SELECT * FROM executions WHERE tool='rollback_release' ORDER BY seq")]
        updates = con.execute("SELECT COUNT(*) FROM executions WHERE tool='update_incident'").fetchone()[0]
        forbidden = con.execute(f"SELECT COUNT(*) FROM executions WHERE tool IN ({','.join('?' * len(FORBIDDEN_WRITES))})",
                                FORBIDDEN_WRITES).fetchone()[0]
        running = {r["service"]: r["release"] for r in con.execute("SELECT * FROM running WHERE environment='production'")}
        reads_after = 0
        if rollbacks:
            reads_after = con.execute("SELECT COUNT(*) FROM calls WHERE tool LIKE '%metric%' AND wall > ?",
                                      (rollbacks[-1]["wall"],)).fetchone()[0]
        approvals = jsonl(scenario / "raw" / "approvals.jsonl")
        gate = [p for p in jsonl(run / "raw" / "policy_events.jsonl")
                if p.get("scenario") == scenario.name and p.get("event")]        # the monolith's prompt gate
        decided = [a for a in approvals if str(a.get("status", a.get("decision", ""))).upper().startswith("APPROV")] or \
                  [g for g in gate if g.get("approved")]
        first_write = rollbacks[0]["wall"] if rollbacks else None
        approved_first = bool(decided) and first_write is not None and min(
            float(d.get("ts", d.get("wall", 0)) or 0) for d in decided) <= float(first_write)
        text = tape_text(scenario)
        mine = {
            "rollback_exactly_once": len(rollbacks) == 1,
            "rolled_back_to_healthy": running.get("checkout-api") in HEALTHY,
            "no_forbidden_actions": forbidden == 0,
            "incident_updated": updates >= 1,
            "verified_recovery": reads_after >= 1,
            "approval_before_write": approved_first,
            "diagnosis_names_release": "rel-2031" in text,
            "diagnosis_names_pool": bool(POOL_WORDS.search(text)),
        }
        scored = json.loads((scenario / "score.json").read_text())["checks"]
        counted += 1
        for name, value in mine.items():
            if name in scored and bool(scored[name]) != value:
                disagree.append(f"{scenario.name}.{name}: raw says {value}, score says {scored[name]}")
    return ("E1 outcome checks recomputed from the world ledger", not disagree,
            "; ".join(disagree) or f"{counted} E1 scenario(s): every outcome check agrees with the world database and the tapes")


def writes_per_operation(run: Path, facts: dict) -> Check:
    """L8: count physical rollbacks and idempotent replays in each scenario's own world database."""
    rows, bad = {}, []
    for scenario in scenarios(run):
        con = world(scenario)
        if con is None:
            continue
        execs = [dict(r) for r in con.execute("SELECT * FROM executions WHERE tool='rollback_release' ORDER BY seq")]
        replays = con.execute("SELECT COALESCE(SUM(replays),0) FROM idem WHERE tool='rollback_release'").fetchone()[0]
        keys = {e["idempotency_key"] for e in execs if e["idempotency_key"]}
        rows[scenario.name] = {"physical": len(execs), "replays": replays, "keys": len(keys),
                               "unkeyed": sum(1 for e in execs if not e["idempotency_key"])}
    for exp in ("E1", "E4", "E5"):
        for arch in ("monolith", "layered"):
            mine = [v["physical"] for k, v in rows.items() if k.startswith(exp) and arch in k]
            published = fact(facts, f"{exp}.{arch}.physical_rollbacks_total")
            if published is not None and sum(mine) != published:
                bad.append(f"{exp}.{arch}: world databases hold {sum(mine)} rollback(s), facts say {published}")
    for arch in ("monolith", "layered"):
        duplicates = sum(max(0, v["physical"] - 1) for k, v in rows.items() if k.startswith("E4") and arch in k)
        published = fact(facts, f"headline.e4_duplicate_rollbacks.{arch}")
        if published is not None and duplicates != published:
            bad.append(f"E4 {arch}: {duplicates} duplicate physical rollback(s) in the ledgers, facts say {published}")
    detail = ("; ".join(bad) or
              "E4 physical rollbacks per scenario: " +
              ", ".join(f"{k.replace('E4-', '')} {v['physical']} (keys {v['keys']}, unkeyed {v['unkeyed']}, replays {v['replays']})"
                        for k, v in sorted(rows.items()) if k.startswith("E4")))
    return ("physical writes per operation id, from the backend ledger", not bad, detail)


def no_repeated_work_after_a_kill(run: Path, facts: dict) -> Check:
    """L5: for the scenarios that actually reached a SIGKILL, compare the model work before and after it."""
    exposed, bad, notes = 0, [], []
    for scenario in scenarios(run):
        kills = killed_phases(scenario)
        if not kills:
            continue
        exposed += 1
        phases = jsonl(scenario / "phases_harness.jsonl")
        killed_pids = {p["pid"] for p in kills}
        after_pids = {p["pid"] for p in phases if p["pid"] not in killed_pids
                      and float(p.get("started", 0)) >= min(float(k.get("started", 0)) for k in kills)}
        calls = [c for c in jsonl(scenario / "tape" / "model_calls.jsonl")]
        before = [c for c in calls if c.get("pid") in killed_pids]
        after = [c for c in calls if c.get("pid") in after_pids]
        repeated = {c["hash"] for c in after} & {c["hash"] for c in before}
        score = json.loads((scenario / "score.json").read_text())
        if score.get("model_calls_after_crash") is not None and len(after) != score["model_calls_after_crash"]:
            bad.append(f"{scenario.name}: {len(after)} model call(s) after the kill in the tape, score says {score['model_calls_after_crash']}")
        if arch_of(scenario) == "layered" and repeated:
            bad.append(f"{scenario.name}: {len(repeated)} model call(s) repeated after the kill")
        notes.append(f"{scenario.name} {len(before)}→{len(after)} calls"
                     + (f", {len(repeated)} repeated" if repeated else ""))
    if not exposed:
        return ("no model call after the kill repeats work completed before it", None,
                "no scenario in this run reached a SIGKILL")
    return ("no model call after the kill repeats work completed before it", not bad,
            "; ".join(bad) or f"{exposed} exposed scenario(s): " + "; ".join(notes))


def writes_were_authorized(run: Path, facts: dict) -> Check:
    """L9: every write the layered platform executed carries an authorization record.

    The monolith is the baseline and has no deterministic policy engine, so its writes are *counted*, not failed:
    that contrast is the measured result, not a defect in the verifier.
    """
    bad, layered_writes, unrecorded_monolith = [], 0, []
    policy = defaultdict(list)
    for event in jsonl(run / "raw" / "policy_events.jsonl"):
        policy[event.get("scenario")].append(event)
    for scenario in scenarios(run):
        con = world(scenario)
        if con is None:
            continue
        events = policy[scenario.name]
        decided = [e for e in events if e.get("effect") in ("ALLOW", "REQUIRE_APPROVAL")] + \
                  [e for e in events if e.get("event") and e.get("approved")]
        for row in con.execute("SELECT * FROM executions ORDER BY seq"):
            if arch_of(scenario) == "layered":
                layered_writes += 1
                if not decided:
                    bad.append(f"{scenario.name}: {row['tool']} executed with no policy decision")
            elif not decided:
                unrecorded_monolith.append(f"{scenario.name}/{row['tool']}"
                                           + ("" if row["idempotency_key"] else " (no operation id)"))
    detail = f"{layered_writes} layered write(s), each with a policy decision"
    if unrecorded_monolith:
        detail += f"; monolith writes with no authorization record at all: {', '.join(unrecorded_monolith)}"
    return ("every executed write had a policy allow and an approval", not bad, "; ".join(bad) or detail)


def approval_precedes_production_writes(run: Path, facts: dict) -> Check:
    """L10: the production rollback must not precede the approval that allowed it."""
    bad, counted = [], 0
    for scenario in scenarios(run):
        con = world(scenario)
        if con is None:
            continue
        rollbacks = [dict(r) for r in con.execute("SELECT * FROM executions WHERE tool='rollback_release' ORDER BY seq")]
        if not rollbacks:
            continue
        counted += 1
        approvals = jsonl(scenario / "raw" / "approvals.jsonl")
        stamps = [float(a.get("ts") or a.get("wall") or 0) for a in approvals
                  if str(a.get("status", a.get("decision", ""))).upper().startswith("APPROV")]
        gate = [float(g.get("ts") or 0) for g in jsonl(run / "raw" / "policy_events.jsonl")
                if g.get("scenario") == scenario.name and g.get("event") and g.get("approved")]
        stamps += gate
        if not stamps:
            bad.append(f"{scenario.name}: a production rollback ran with no approval record")
        elif min(stamps) > float(rollbacks[0]["wall"]):
            bad.append(f"{scenario.name}: the rollback ran {min(stamps) - float(rollbacks[0]['wall']):.1f}s before its approval")
    return ("approval precedes every production write", not bad,
            "; ".join(bad) or f"{counted} scenario(s) with a production rollback, each approved first")


def one_trace_across_processes(run: Path, facts: dict) -> Check:
    """L11: in a crash run, the workflow's spans must share one trace id across the processes."""
    spans = defaultdict(list)
    for span in jsonl(run / "raw" / "traces.jsonl"):
        spans[span.get("scenario")].append(span)
    exposed, single, bad = 0, 0, []
    for scenario in scenarios(run):
        if not killed_phases(scenario) or arch_of(scenario) != "layered":
            continue
        exposed += 1
        mine = [s for s in spans[scenario.name] if (s.get("attributes") or {}).get("f2.workflow_id")]
        traces = defaultdict(set)
        for s in mine:
            traces[s["trace_id"]].add(s["pid"])
        across = {t: pids for t, pids in traces.items() if len(pids) > 1}
        if len(across) == 1:
            single += 1
        else:
            bad.append(f"{scenario.name}: {len(traces)} workflow trace(s), {len(across)} spanning more than one process")
    published = fact(facts, "E8.layered.crash_runs_single_trace_across_processes")
    if published is not None and single != published:
        bad.append(f"{single} crash run(s) with one trace across processes, facts say {published}")
    if not exposed:
        return ("one workflow trace across the processes of a crash run", None, "no layered scenario reached a SIGKILL")
    return ("one workflow trace across the processes of a crash run", not bad,
            "; ".join(bad) or f"{single} of {exposed} exposed layered crash run(s) kept one workflow trace across their processes")


def diff_stats(path: Path) -> dict[str, Any]:
    """Files and line counts straight from the patch text."""
    files, added, removed = set(), 0, 0
    for line in path.read_text().splitlines():
        if line.startswith("+++ b/"):
            files.add(line[6:].strip())
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return {"files": sorted(files), "files_changed": len(files), "lines_added": added, "lines_removed": removed}


def change_scope_from_diffs(run: Path, facts: dict) -> Check:
    """L14: recompute each change experiment's size from its patch, not from the scorer's bookkeeping."""
    bad, notes = [], []
    for change, exp in (("E2_model_swap", "E2"), ("E3_tool_v2", "E3"), ("E9_dry_run", "E9")):
        for arch in ("monolith", "layered"):
            patch = run / "diffs" / f"{change}-{arch}.diff"
            if not patch.exists():
                bad.append(f"missing patch {patch.name}")
                continue
            mine = diff_stats(patch)
            for key in ("files_changed", "lines_added", "lines_removed"):
                published = fact(facts, f"{exp}.change.{arch}.{key}")
                if published is not None and mine[key] != published:
                    bad.append(f"{exp}.{arch}.{key}: patch gives {mine[key]}, facts say {published}")
            notes.append(f"{exp} {arch} {mine['files_changed']} file(s) +{mine['lines_added']}/-{mine['lines_removed']}")
    return ("change scope recomputed from the diffs and the concern map", not bad,
            "; ".join(bad) or "; ".join(notes))


def dry_run_crosses_through_the_contract(run: Path, facts: dict) -> Check:
    """L15: the cross-cutting requirement must cross layers through the contract module, not by a back door."""
    patch = run / "diffs" / "E9_dry_run-layered.diff"
    if not patch.exists():
        return ("the dry-run change crosses layers through the contract module", None, "no E9 layered patch in this run")
    files = diff_stats(patch)["files"]
    contract = [f for f in files if f.endswith("contracts.py")]
    layers = {f.split("/")[1] for f in files if f.startswith("layered_platform/") and "/" in f[len("layered_platform/"):]}
    published = fact(facts, "E9.change.layered.files_changed")
    problems = []
    if not contract:
        problems.append("the layered dry-run patch changes no contract module, so the crossing is implicit")
    if published is not None and len(files) != published:
        problems.append(f"the patch changes {len(files)} file(s), facts say {published}")
    return ("the dry-run change crosses layers through the contract module", not problems,
            "; ".join(problems) or f"{len(files)} file(s): {', '.join(files)} — layers crossed: "
            f"{', '.join(sorted(layers)) or 'none'}, through {', '.join(contract)}")


def tests_recounted(run: Path, facts: dict) -> Check:
    """Recount the test outcomes from the JUnit file the run kept."""
    junit = run / "tests.junit.xml"
    if not junit.exists():
        return ("tests recounted from the JUnit file", None, "the run kept no JUnit file")
    cases = list(ET.parse(junit).getroot().iter("testcase"))
    failed = sum(1 for c in cases if c.find("failure") is not None or c.find("error") is not None)
    skipped = sum(1 for c in cases if c.find("skipped") is not None)
    passed = len(cases) - failed - skipped
    bad = [f"{name}: JUnit says {mine}, facts say {fact(facts, key)}"
           for name, key, mine in (("passed", "tests.passed", passed), ("failed", "tests.failed", failed),
                                   ("skipped", "tests.skipped", skipped), ("total", "tests.total", len(cases)))
           if fact(facts, key) is not None and fact(facts, key) != mine]
    return ("tests recounted from the JUnit file", not bad,
            "; ".join(bad) or f"{passed} passed, {failed} failed, {skipped} skipped, {len(cases)} cases")


def replay_matches(run: Path, facts: dict) -> Check:
    """The published facts must be reproducible from the tapes: compare them with the replay run's own facts."""
    replay = run.parent / f"{run.name}-replay"
    if not (replay / "facts.json").exists():
        return ("the replay's facts match the recorded run", None, "no replay run beside this one")
    theirs = json.loads((replay / "facts.json").read_text())
    # Excluded, with reasons: timings and ids differ by construction; the replay runs its own test pass, so its test
    # counts are its own; `revisions` records work done after the recording.  Everything measured is compared.
    excluded = re.compile(r"(wall|_s$|started|finished|\bts\b|run_id|replay|manifest\.|mode|digest|sha256|hash\.|^tests\.|^headline\.tests$|^revisions)")
    compared = [k for k in facts if not excluded.search(k) and k in theirs]
    differ = [k for k in compared if fact(theirs, k) != fact(facts, k)]
    return ("the replay's facts match the recorded run", not differ,
            f"{len(differ)} differing fact(s): {differ[:6]}" if differ
            else f"{len(compared)} measured fact(s) identical under replay; timings, ids, the replay's own test pass "
                 "and post-run revisions excluded")


def exposure_denominators(run: Path, facts: dict) -> Check:
    """Every fault claim needs the number of scenarios that actually met the fault, not the number planned."""
    planned = defaultdict(int)
    exposed = defaultdict(int)
    for scenario in scenarios(run):
        exp, arch = scenario.name.split("-")[0], arch_of(scenario)
        score = json.loads((scenario / "score.json").read_text())
        if score.get("crash_point"):
            planned[(exp, arch)] += 1
            if killed_phases(scenario):
                exposed[(exp, arch)] += 1
    rows = [f"{exp} {arch}: {exposed[(exp, arch)]} of {n} planned reached the kill"
            for (exp, arch), n in sorted(planned.items())]
    short = [f"{exp} {arch}" for (exp, arch), n in planned.items() if exposed[(exp, arch)] < n]
    return ("fault claims carry their exposure denominator", True,
            "; ".join(rows) + (f" — publish {', '.join(short)} against the exposed count, never the planned one" if short else ""))


def outcomes_are_classified(run: Path, facts: dict) -> Check:
    """Every scenario carries one of the four outcome classes, and each class is justified by the raw records."""
    path = run / "outcomes.json"
    if not path.exists():
        return ("every scenario has an outcome class", None,
                "run scripts/classify_outcomes.py to write outcomes.json")
    data = json.loads(path.read_text())
    bad = []
    recorded = {row["scenario"] for row in data["scenarios"]}
    present = {d.name for d in scenarios(run)}
    if recorded != present:
        bad.append(f"classified {len(recorded)} scenario(s), the run has {len(present)}")
    for row in data["scenarios"]:
        kills = len(killed_phases(run / "scenarios" / row["scenario"]))
        if row["sigkills"] != kills:
            bad.append(f"{row['scenario']}: {row['sigkills']} kill(s) recorded, the harness log shows {kills}")
        if row["outcome"] == "NOT_EXPOSED" and row["fault_exposed"]:
            bad.append(f"{row['scenario']}: marked NOT_EXPOSED but its fault fired")
        if row["outcome"] == "SUCCESS" and row["failed_checks"]:
            bad.append(f"{row['scenario']}: marked SUCCESS with failing checks {row['failed_checks']}")
    for key, slot in data["exposure"].items():
        if slot["exposed"] > slot["planned"]:
            bad.append(f"{key}: more exposed than planned")
    counts = ", ".join(f"{k} {v}" for k, v in data["counts"].items())
    return ("every scenario has an outcome class", not bad, "; ".join(bad) or f"{len(recorded)} scenario(s): {counts}")


CHECKS: tuple[Callable[[Path, dict], Check], ...] = (
    outcomes_are_classified,
    e1_outcome_checks,
    writes_per_operation,
    no_repeated_work_after_a_kill,
    writes_were_authorized,
    approval_precedes_production_writes,
    one_trace_across_processes,
    change_scope_from_diffs,
    dry_run_crosses_through_the_contract,
    tests_recounted,
    replay_matches,
    exposure_denominators,
)


def run_checks(run: Path) -> list[dict[str, Any]]:
    facts = json.loads((run / "facts.json").read_text()) if (run / "facts.json").exists() else {}
    out = []
    for fn in CHECKS:
        name, ok, detail = fn(run, facts)
        out.append({"check": name, "ok": ok, "recomputed": True, "detail": detail})
    return out


def main(argv: list[str]) -> int:
    run = Path(argv[1]) if len(argv) > 1 else POC / "runs" / (POC / "runs" / "PUBLISHED").read_text().strip()
    if not run.is_absolute():
        run = POC / run
    results = run_checks(run)
    for r in results:
        mark = "PASS " if r["ok"] else ("--   " if r["ok"] is None else "FAIL ")
        print(mark + r["check"] + "  [" + r["detail"] + "]")
    return 1 if any(r["ok"] is False for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
