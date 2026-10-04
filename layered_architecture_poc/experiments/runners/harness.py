"""Experiment harness: runs every preregistered scenario as real processes and collects the evidence.

    uv run python -m experiments.runners.harness --run-dir runs/<id> [--replay-from runs/<id>] [--only E4,E5]

For each scenario: a fresh world database, the armed fault, and one process per phase.  A SIGKILLed phase is followed
by the architecture's realistic recovery: the monolith re-submits the request, the layered platform calls recover().
Change experiments (E2, E3, E9) first build an isolated git worktree, apply the frozen patch, commit it, measure the
diff and run the fast tests there, then run the scenario from that worktree.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from experiments.scorers import change_scope, evidence, traces
from simulated_enterprise.world import World

POC = Path(__file__).resolve().parents[2]
PLAN = POC / "experiments" / "preregistration" / "experiment_plan.yaml"
PY = sys.executable
EXCLUDE = {".venv", "var", "runs", "__pycache__", ".pytest_cache"}


def load_plan() -> dict[str, Any]:
    return yaml.safe_load(PLAN.read_text())


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---- worktrees for change experiments ----------------------------------------------------------------------------------
def _copy_source(dst: Path) -> None:
    def ignore(d: str, names: list[str]) -> set[str]:
        return {n for n in names if n in EXCLUDE or n.endswith(".pyc")}
    shutil.copytree(POC, dst, ignore=ignore)


def prepare_worktree(run_dir: Path, change: str, arch: str, plan: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    wt = run_dir / "worktrees" / f"{change}-{arch}"
    report = run_dir / "changes" / f"{change}-{arch}.json"
    if wt.exists() and report.exists():
        return wt, json.loads(report.read_text())
    shutil.rmtree(wt, ignore_errors=True)
    _copy_source(wt)
    g = lambda *a: subprocess.run(["git", "-c", "user.email=poc@local", "-c", "user.name=f2-harness", *a], cwd=wt, check=True, capture_output=True, text=True)  # noqa: E731
    g("init", "-q")
    g("add", "-A")
    g("commit", "-qm", "baseline (frozen POC source)")
    patch = POC / "experiments" / "changes" / change / f"{arch}.patch"
    g("apply", "--whitespace=nowarn", str(patch))
    g("add", "-A")
    g("commit", "-qm", f"{change} ({arch})")
    exp = next(k for k, v in plan["experiments"].items() if k == change.split("_")[0])
    scope = change_scope.measure(wt, arch, plan["concern_map"], plan["expected_concerns"][exp][arch])
    t0 = time.time()
    tests = subprocess.run([PY, "-m", "pytest", "-m", "not model", "-q", "-p", "no:cacheprovider", "--junitxml", str(run_dir / "changes" / f"{change}-{arch}.junit.xml")],
                           cwd=wt, capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=str(wt)))
    tail = [l for l in tests.stdout.splitlines() if l.strip()][-1:] or [""]
    scope.update({"change": change, "patch": str(patch.relative_to(POC)), "patch_sha256": _sha(patch), "tests_after_change": tail[0],
                  "tests_returncode": tests.returncode, "tests_wall_s": round(time.time() - t0, 1),
                  "diff": g("diff", "HEAD~1", "HEAD").stdout})
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(scope, indent=1))
    (run_dir / "diffs").mkdir(exist_ok=True)
    (run_dir / "diffs" / f"{change}-{arch}.diff").write_text(scope["diff"])
    return wt, scope


def _sha(p: Path) -> str:
    import hashlib

    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---- one scenario --------------------------------------------------------------------------------------------------------
def _phase(sdir: Path, src: Path, env: dict[str, str], arch: str, phase: str, extra: list[str]) -> dict[str, Any]:
    t0 = time.time()
    with open(sdir / "logs" / f"{len(list((sdir / 'logs').iterdir())):02d}-{arch}-{phase}.log", "w") as log:
        p = subprocess.Popen([PY, "-m", "experiments.runners.scenario", "--arch", arch, "--dir", str(sdir), "--phase", phase, *extra],
                             cwd=src, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            rc = p.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            p.send_signal(signal.SIGKILL)
            rc = p.wait()
    rec = {"phase": phase, "arch": arch, "pid": p.pid, "returncode": rc, "started": t0, "wall_s": round(time.time() - t0, 2)}
    with open(sdir / "phases_harness.jsonl", "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    _log(f"    {arch}:{phase} pid={p.pid} rc={rc} {rec['wall_s']}s")
    return rec


def _layered_status(sdir: Path) -> str | None:
    db = sdir / "platform" / "platform.db"
    if not db.exists():
        return None
    con = sqlite3.connect(db)
    try:
        row = con.execute("SELECT status FROM workflows ORDER BY created LIMIT 1").fetchone()
        return row[0] if row else None
    finally:
        con.close()


def run_scenario(spec: dict[str, Any], run_dir: Path, plan: dict[str, Any], replay_from: Path | None, area: str = "scenarios") -> dict[str, Any]:
    sdir = run_dir / area / spec["id"]
    shutil.rmtree(sdir, ignore_errors=True)
    (sdir / "logs").mkdir(parents=True)
    (sdir / "tape").mkdir()
    World(sdir / "world.db").reset()
    faults = plan["fault_parameters"]
    if spec.get("fault") == "lose_response":
        World(sdir / "world.db").arm_fault("rollback_release", "lose_response", faults["lost_response_delay_s"], 1)
    src, scope = POC, None
    if spec.get("change"):
        src, scope = prepare_worktree(run_dir, spec["change"], spec["arch"], plan)
    if replay_from:
        shutil.copy(replay_from / area / spec["id"] / "tape" / "model_tape.jsonl", sdir / "tape" / "model_tape.jsonl")
    env = dict(os.environ, F2_WORLD_DB=str(sdir / "world.db"), F2_SEED=str(spec["seed"]), F2_CRASH_MARKER=str(sdir / ".crashed"),
               F2_TOOL_TIMEOUT_S=str(faults["tool_timeout_s"]), PYTHONPATH=f"{src}{os.pathsep}{POC}",
               F2_TAPE=f"{'replay' if replay_from else 'record'}:{sdir / 'tape'}")
    env.pop("F2_CONFIG_DIR", None)
    if spec.get("crash"):
        env["F2_CRASH_AT"] = spec["crash"]
    extra = ["--prompt", spec.get("prompt", "normal")] + (["--dry-run"] if spec.get("dry_run") else [])
    _log(f"  {spec['id']} ({'replay' if replay_from else 'record'}; src={'worktree' if scope else 'poc'})")
    if spec["arch"] == "monolith":
        rec = _phase(sdir, src, env, "monolith", "run", extra)
        if rec["returncode"] == -9:  # the user re-submits the request; the session store only has finished turns
            _phase(sdir, src, env, "monolith", "run", extra)
    else:
        rec = _phase(sdir, src, env, "layered", "start", extra)
        for _ in range(4):
            if rec["returncode"] == -9:
                rec = _phase(sdir, src, env, "layered", "recover", [])
                continue
            if _layered_status(sdir) == "WAITING_APPROVAL":
                rec = _phase(sdir, src, env, "layered", "approve", [])
                continue
            break
    raw = evidence.collect(sdir, spec["arch"])
    (sdir / "raw").mkdir()
    for k, rows in raw.items():
        with open(sdir / "raw" / f"{k}.jsonl", "w") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
    sc = evidence.score(sdir, spec["arch"], raw, spec.get("crash"))
    sc["trace"] = traces.layered(raw) if spec["arch"] == "layered" else traces.monolith(raw)
    sc.update({"scenario": spec["id"], "exp": spec["exp"], "model": plan["models"][spec["model"]]["name"], "seed": spec["seed"],
               "fault": spec.get("fault"), "prompt": spec.get("prompt", "normal"), "change": spec.get("change"), "replayed": bool(replay_from),
               "tape_misses": len(evidence.jsonl(sdir / "tape" / "model_tape.misses.jsonl"))})
    (sdir / "score.json").write_text(json.dumps(sc, indent=1, default=str))
    _log(f"    -> {sc['final_status']} checks {sc['checks_passed']}/{sc['checks_total']} rollbacks={sc['physical_rollbacks']} "
         f"model_calls={sc['model_calls']} tokens={sc['tokens']}")
    return sc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--replay-from")
    ap.add_argument("--only", default="")
    ap.add_argument("--supplementary", action="store_true", help="write to <run>/supplementary/ (a declared re-run), never over the original")
    a = ap.parse_args()
    run_dir = Path(a.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    plan = load_plan()
    only = {x for x in a.only.split(",") if x}
    for spec in plan["scenarios"]:
        if only and spec["exp"] not in only and spec["id"] not in only:
            continue
        run_scenario(spec, run_dir, plan, Path(a.replay_from).resolve() if a.replay_from else None, "supplementary" if a.supplementary else "scenarios")


if __name__ == "__main__":
    main()
