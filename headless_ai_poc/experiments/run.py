"""`hai-exp`: run the H1–H7 experiments and write one run folder.

    uv run hai-exp run                     live: model answers from Ollama, recorded into the run folder
    uv run hai-exp run --replay [RUN_ID]   replay a recorded run (default: the reference run); no Ollama needed
    uv run hai-exp run --tape demo         replay Part 2's recorded demo answers (fast smoke run)
    uv run hai-exp run --only h2,h7        a subset
    uv run hai-exp list                    runs on this machine

A run folder: runs/<run-id>/{run.json, summary.json, h1/ … h7/, change-scope.json}. Each scenario folder keeps its
result.json, the model traffic it used (traffic/), its databases and, for H2/H7, the process logs.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from experiments.harness import prepare_env, replay_tape

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
ORDER = ["h1", "h2", "h3", "h4", "h5", "h6", "h7"]
REFERENCE_RUN = "2026-09-17-recorded"
TITLES = {"h1": "Same capability, different channels", "h2": "Slack → Web → CLI handoff (separate processes)",
          "h3": "Add a channel, change a rule (change scope)", "h4": "Governance is the same in every channel",
          "h5": "Same person, same authority, any channel", "h6": "Rendering needs no reasoning",
          "h7": "The channel dies; the workflow does not"}
WORKFLOWS = {"h1": 3, "h2": 1, "h4": 4, "h5": 1, "h6": 1, "h7": 1}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def scenario_env(folder: Path, mode: str, replay_run: Path | None, name: str) -> dict[str, str]:
    state = folder / "state"
    if state.exists():
        shutil.rmtree(state)
    traffic = folder / "traffic"
    if mode == "live":
        if traffic.exists():
            shutil.rmtree(traffic)
        env = prepare_env(state, record_to=traffic)
    elif mode == "tape":
        env = prepare_env(state, replay_workflows=WORKFLOWS[name])
    else:
        assert replay_run is not None
        env = prepare_env(state, replay_from=replay_run / name / "traffic")
    env["LAP_RUNS_DIR"] = str(folder / "traces")
    return env


def run(args: argparse.Namespace) -> int:
    mode = "tape" if args.tape else "replay" if args.replay is not None else "live"
    replay_run = RUNS / (args.replay or REFERENCE_RUN) if mode == "replay" else None
    if replay_run is not None and not replay_run.exists():
        print(f"no recorded run at {replay_run}", file=sys.stderr)
        return 2
    run_id = args.run_id or (f"{datetime.now().strftime('%Y-%m-%d-%H%M')}-{mode}")
    out = RUNS / run_id
    out.mkdir(parents=True, exist_ok=True)
    only = [s for s in (args.only.split(",") if args.only else ORDER)]
    meta = {"run_id": run_id, "mode": mode, "replay_from": replay_run.name if replay_run else None,
            "tape": "part2 demo-gpt-oss_20b" if mode == "tape" else None, "started": now(), "scenarios": only,
            "host": {"platform": sys.platform, "python": platform.python_version(), "machine": platform.machine()},
            "models": ["gpt-oss:20b (reasoning, summary)", "nomic-embed-text"] if mode == "live" else "recorded"}
    if args.only and (out / "run.json").exists():
        meta = {**json.loads((out / "run.json").read_text()), "last_mode": mode}
    (out / "run.json").write_text(json.dumps(meta, indent=2))
    results = {}
    for name in only:
        t0 = time.monotonic()
        print(f"· {name}  {TITLES[name]} …", flush=True)
        if name == "h3":
            cmd = [sys.executable, "-m", "experiments.change_scope.run", "--out", str(out / "change-scope.json")]
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            (out / "h3").mkdir(exist_ok=True)
            (out / "h3" / "run.log").write_text(p.stdout + p.stderr)
            results[name] = h3_result(out / "change-scope.json", p.returncode)
            (out / "h3" / "result.json").write_text(json.dumps(results[name], indent=2))
        else:
            folder = out / name
            folder.mkdir(exist_ok=True)
            env = {**{k: v for k, v in os.environ.items() if not k.startswith(("LAP_", "HAI_"))},
                   **scenario_env(folder, mode, replay_run, name)}
            with (folder / "run.log").open("w") as log:
                p = subprocess.run([sys.executable, "-m", "experiments.scenarios", name, str(folder)], cwd=ROOT, env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
            results[name] = json.loads((folder / "result.json").read_text())
            checkpoint_wal(folder / "state")
        r = results[name]
        failed = [k for k, v in r.get("checks", {}).items() if not v]
        mark = "✓" if r.get("pass") else "✗"
        print(f"  {mark} {name} {time.monotonic() - t0:.0f}s" + (f"  failed: {failed}" if failed else "")
              + (f"  error: {r['error']}" if r.get("error") else ""), flush=True)
    previous = out / "summary.json"
    if args.only and previous.exists():  # a partial re-run keeps the other scenarios' results
        for n, sc in json.loads(previous.read_text())["scenarios"].items():
            if n not in results:
                results[n] = json.loads((out / n / "result.json").read_text())
        results = {n: results[n] for n in ORDER if n in results}
    summary = {"run_id": run_id, "mode": mode, "finished": now(),
               "scenarios": {n: {"title": TITLES[n], "pass": r.get("pass"), "seconds": r.get("seconds"),
                                 "checks": r.get("checks", {})} for n, r in results.items()},
               "passed": sum(1 for r in results.values() if r.get("pass")), "total": len(results)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    meta["finished"] = summary["finished"]
    meta["scenarios"] = list(results)
    if args.only:
        meta.setdefault("reruns", []).append({"only": only, "at": summary["finished"]})
    (out / "run.json").write_text(json.dumps(meta, indent=2))
    print(f"\n{summary['passed']}/{summary['total']} scenarios passed · {out}")
    return 0 if summary["passed"] == summary["total"] else 1


def checkpoint_wal(state: Path) -> None:
    """Fold each database's write-ahead log into the .db file, so the kept state is complete on its own."""
    import sqlite3

    for db in sorted(state.glob("*.db")):
        try:
            with sqlite3.connect(db) as con:
                con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error as exc:
            print(f"  ! could not checkpoint {db.name}: {exc}")


def h3_result(path: Path, code: int) -> dict:
    if code or not path.exists():
        return {"pass": False, "checks": {}, "facts": {}, "error": "change-scope run failed", "scenario": "h3"}
    data = json.loads(path.read_text())
    by = {c["id"]: c for c in data["changes"]}
    add, role, drift = by["add-channel"], by["approver-role"], by["approver-role-drift"]
    hl_roles = role["headless"]["runtime"]["roles"]
    checks = {
        "all_patches_apply_and_import": all(c[s].get("applies") and c[s].get("imports")
                                            for c in data["changes"] for s in ("baseline", "headless") if s in c),
        "new_channel_touches_no_core_file": add["headless"]["core_files"] == 0,
        "new_channel_keeps_import_contracts": bool(add["headless"].get("contracts_kept")),
        "new_channel_completes_a_workflow": add["headless"]["runtime"]["teams"]["final_status"] == "COMPLETED",
        "new_channel_gets_existing_governance": add["headless"]["runtime"]["roles"]["teams"]["required_role"] == "incident-commander",
        "baseline_new_channel_adds_a_governance_copy": add["baseline"]["governance_copies"]["baseline_approval_rules"]
                                                        == data["governance_copies_before"]["baseline_approval_rules"] + 1,
        "rule_change_is_one_place_headless": role["headless"]["core_files"] == 0
                                             and set(role["headless"]["kinds"]) == {"platform-config"},
        "rule_change_reaches_every_channel": {v["required_role"] for v in hl_roles.values()} == {"release-manager"},
        "baseline_rule_change_edits_every_copy": role["baseline"]["files"] == data["governance_copies_before"]["baseline_approval_rules"],
        "controlled_drift_is_visible": len(set(drift["baseline"]["runtime"]["approval_role"].values())) == 2,
    }
    return {"pass": all(checks.values()), "checks": checks, "facts": data, "scenario": "h3"}


def tests(args: argparse.Namespace) -> int:
    """Run the test suite and the import contracts; record the counts in runs/<run-id>/tests.json."""
    out = RUNS / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LAP_", "HAI_"))}
    py = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT, env=env,
                        capture_output=True, text=True)
    lint = subprocess.run([str(Path(sys.executable).parent / "lint-imports")], cwd=ROOT, env=env, capture_output=True, text=True)
    # -rA prints one line per test; the trailing count line is not always captured, so count the lines.
    outcomes = [l.split(" ")[0] for l in py.stdout.splitlines() if l[:6] in ("PASSED", "FAILED", "SKIPPE", "ERROR ")]
    counts = {"passed": outcomes.count("PASSED"), "failed": outcomes.count("FAILED"),
              "skipped": outcomes.count("SKIPPED"), "errors": outcomes.count("ERROR")}
    tail = ", ".join(f"{v} {k}" for k, v in counts.items() if v)
    kept = __import__("re").search(r"Contracts: (\d+) kept, (\d+) broken", lint.stdout)
    data = {"at": now(), "summary": tail, "passed": counts.get("passed", 0), "failed": counts.get("failed", 0),
            "skipped": counts.get("skipped", 0), "contracts_kept": int(kept.group(1)) if kept else 0,
            "contracts_broken": int(kept.group(2)) if kept else -1, "ok": py.returncode == 0 and lint.returncode == 0}
    (out / "tests.json").write_text(json.dumps(data, indent=2))
    print(json.dumps(data, indent=2))
    return 0 if data["ok"] else 1


def list_runs(_: argparse.Namespace) -> int:
    for d in sorted(RUNS.iterdir()) if RUNS.exists() else []:
        s = d / "summary.json"
        if s.exists():
            data = json.loads(s.read_text())
            print(f"{d.name:<32} {data['mode']:<7} {data['passed']}/{data['total']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hai-exp")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--run-id")
    r.add_argument("--only")
    r.add_argument("--replay", nargs="?", const=REFERENCE_RUN)
    r.add_argument("--tape", action="store_true")
    r.set_defaults(fn=run)
    t = sub.add_parser("tests")
    t.add_argument("--run-id", default=REFERENCE_RUN)
    t.set_defaults(fn=tests)
    sub.add_parser("list").set_defaults(fn=list_runs)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
