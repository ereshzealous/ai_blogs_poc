"""The harness: run every preregistered scenario as real processes, then collect, verify and score.

    python -m lineage.run record [--run-id ID] [--only e01-success,...]   live model (Ollama), tapes recorded per scenario
    python -m lineage.run replay <recorded-run-id>                        same scenarios, model answers from the recorded tapes
    python -m lineage.run smoke [--only ...]                              every scenario into runs/_smoke, model tapes from the
                                                                          published run (no Ollama needed)

Per scenario (one directory under runs/<run-id>/scenarios/):
  1. write spec.json (the scenario resolved against the defaults), the deployment API's database and its fault script;
  2. start the deployment API, the scripted operator and two agent runtimes (target and background) as separate processes;
  3. supervise the runtimes: a runtime that dies of SIGKILL (a crash point fired) is restarted, as an orchestrator would;
  4. stop the services, snapshot the world, export and verify the evidence chain;
  5. build ground truth from the systems of record and score the three observation layers (lineage/score.py).

The harness never edits evidence, logs or spans.  A recorded run never overwrites an existing run directory.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
import tomllib
from datetime import date
from pathlib import Path

from .common import EXPERIMENTS, POC, canon, file_digest, sha

RUNS = POC / "runs"
PREREG_PATH = EXPERIMENTS / "preregistration.toml"
PREREG = tomllib.loads(PREREG_PATH.read_text())
CASES = {c["id"]: c for c in PREREG["case"]}
FROZEN = ["config/world.toml", "config/control_plane.toml", "config/policies/prod-rollback-v41.toml", "config/policies/prod-rollback-v42.toml",
          "config/principals.toml", "config/data.toml", "config/retention.toml", "experiments/preregistration.toml"]


def code_hashes() -> dict:
    return {p.relative_to(POC).as_posix(): file_digest(p) for p in sorted((POC / "lineage").glob("*.py"))}


def resolve(case: dict) -> dict:
    d = PREREG["defaults"]
    target = {"policy": case.get("policy", d["policy"]), "agent_config": case.get("agent_config", d["agent_config"]),
              "idempotency": case.get("idempotency", d["idempotency"]), "severity": case.get("severity", d["severity"]),
              "decisions": case.get("decisions", d["decisions"]), "annotation": case.get("annotation"),
              "context_request": case.get("context_request"), "planner_override": case.get("planner_override"),
              "direct_gateway_call": case.get("direct_gateway_call", False), "redeliver_step": case.get("redeliver_step"),
              "crash_at": case.get("crash_at")}
    background = {"policy": d["policy"], "agent_config": d["agent_config"], "idempotency": "on", "severity": "SEV-2",
                  "decisions": d["background_decisions"]}
    return {"scenario": case["id"], "title": case["title"], "group": case["group"], "question": case["question"], "expect": case["expect"],
            "faults": case.get("faults", []), "run": PREREG["run"], "executions": {"target": target, "background": background}}


def init_state(sdir: Path) -> None:
    """Create the shared databases in WAL mode before two runtimes open them at once."""
    import sqlite3
    from .evidence import EvidenceStore
    EvidenceStore(sdir / "state" / "evidence.db", sdir / "witness" / "anchors.jsonl")
    for name in ("workflow.db", "evidence.db", "approvals.db"):
        db = sqlite3.connect(sdir / "state" / name)
        db.execute("PRAGMA journal_mode=WAL")
        db.close()


def wait_for(path: Path, timeout: float = 20) -> None:
    t = time.time()
    while not path.exists():
        if time.time() - t > timeout:
            raise RuntimeError(f"timed out waiting for {path}")
        time.sleep(0.05)


def supervise(sdir: Path, role: str, env: dict) -> list[dict]:
    life = []
    for n in range(1, 5):
        e = {**env, "LINEAGE_INCARNATION": str(n)}
        t0 = time.time()
        p = subprocess.run([sys.executable, "-m", "lineage.runtime", str(sdir), role], cwd=POC, env=e, capture_output=True, text=True, timeout=900)
        (sdir / "procs" / f"{role}-{n}.log").write_text(f"$ python -m lineage.runtime {sdir.name} {role}\nexit {p.returncode}\n--- stdout\n{p.stdout}\n--- stderr\n{p.stderr}")
        life.append({"role": role, "process": n, "exit": p.returncode, "signal": "SIGKILL" if p.returncode == -9 else None, "wall_s": round(time.time() - t0, 2)})
        if p.returncode != -9:
            break
    return life


def run_scenario(rdir: Path, cid: str, tape_mode: str, tape_src: Path | None) -> dict:
    from .collect import collect

    spec = resolve(CASES[cid])
    sdir = rdir / "scenarios" / cid
    for sub in ("deploy", "state", "logs", "telemetry", "procs", "world", "witness"):
        (sdir / sub).mkdir(parents=True, exist_ok=True)
    (sdir / "spec.json").write_text(json.dumps(spec, indent=1))
    (sdir / "deploy" / "faults.json").write_text(json.dumps({"drop_hold_s": spec["run"]["drop_hold_s"], "faults": spec["faults"]}, indent=1))
    from .deploysvc import init_db, snapshot
    init_db(sdir)
    (sdir / "world" / "before.json").write_text(json.dumps(snapshot(sdir), indent=1))
    base = {**os.environ, "PYTHONHASHSEED": "0"}
    base.pop("LINEAGE_CRASH_AT", None)
    t0 = time.time()
    svc = subprocess.Popen([sys.executable, "-m", "lineage.deploysvc", str(sdir)], cwd=POC, env=base,
                           stdout=open(sdir / "procs" / "deploy-api.log", "w"), stderr=subprocess.STDOUT)
    wait_for(sdir / "deploy" / "port")
    from .approval import ApprovalService
    ApprovalService(sdir)            # create the approval database before anyone polls it
    init_state(sdir)
    op = subprocess.Popen([sys.executable, "-m", "lineage.operator", str(sdir)], cwd=POC, env=base,
                          stdout=open(sdir / "procs" / "operator.log", "w"), stderr=subprocess.STDOUT)
    envs = {}
    for role in ("target", "background"):
        e = dict(base)
        if tape_mode == "fake":
            e["LINEAGE_TAPE"] = f"replay:{sdir / 'tape' / role}"
        else:
            e["LINEAGE_TAPE"] = f"{tape_mode}:{sdir / 'tape' / role}"
        if tape_mode in ("replay", "fake"):
            (sdir / "tape" / role).mkdir(parents=True, exist_ok=True)
            shutil.copy(tape_src / "scenarios" / cid / "tape" / role / "model_tape.jsonl", sdir / "tape" / role / "model_tape.jsonl")
        if role == "target" and spec["executions"]["target"].get("crash_at"):
            e["LINEAGE_CRASH_AT"] = spec["executions"]["target"]["crash_at"]
            e["LINEAGE_CRASH_MARKER"] = str(sdir / "procs" / ".crashed")
        envs[role] = e
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(2) as ex:
        futs = {role: ex.submit(supervise, sdir, role, envs[role]) for role in ("target", "background")}
        # the background execution starts a moment later, as INC-4472 opened after INC-4471
        life = futs["target"].result() + futs["background"].result()
    (sdir / "state" / "operator.stop").touch()
    (sdir / "deploy" / "stop").touch()
    op.wait(timeout=30)
    svc.wait(timeout=30)
    (sdir / "procs" / "supervisor.json").write_text(json.dumps(life, indent=1))
    result = collect(sdir, spec, life, round(time.time() - t0, 2))
    return result


def run_all(run_id: str, tape_mode: str, only: list[str] | None = None, source: Path | None = None) -> Path:
    rdir = RUNS / run_id
    if rdir.exists() and not run_id.startswith("_"):
        raise SystemExit(f"{rdir} exists: a recorded run is never overwritten")
    shutil.rmtree(rdir, ignore_errors=True)
    (rdir / "scenarios").mkdir(parents=True)
    ids = only or list(CASES)
    manifest = {"run_id": run_id, "kind": {"record": "recorded", "replay": "replay", "fake": "smoke"}[tape_mode],
                "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "scenarios": ids, "replay_of": source.name if source else None,
                "preregistration_sha256": file_digest(PREREG_PATH), "frozen_inputs": {p: file_digest(POC / p) for p in FROZEN},
                "code": code_hashes()}
    (rdir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (rdir / "environment.json").write_text(json.dumps(environment(tape_mode), indent=1))
    for cid in ids:
        res = run_scenario(rdir, cid, tape_mode, source)
        print(f"{cid:30s} outcome={res['outcome']:20s} mutations={res['mutations']} attempts={res['attempts']} procs={res['processes']} "
              f"evidence={'intact' if res['evidence_intact'] else 'BROKEN'} L0={res['score']['L0']['correct']}/13 "
              f"L1={res['score']['L1']['correct']}/13 L2={res['score']['L2']['correct']}/13 {res['wall_s']}s", flush=True)
    manifest["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (rdir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    from .aggregate import aggregate
    aggregate(rdir)
    return rdir


def environment(tape_mode: str) -> dict:
    import importlib.metadata as md
    env = {"python": sys.version.split()[0], "platform": platform.platform(), "machine": platform.machine(),
           "opentelemetry-sdk": md.version("opentelemetry-sdk"), "opentelemetry-api": md.version("opentelemetry-api"),
           "tape_mode": tape_mode, "ollama": None}
    if tape_mode == "record":
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=5) as r:
                env["ollama"] = json.loads(r.read())
        except OSError as e:
            env["ollama"] = f"unreachable: {e}"
    return env


def main() -> None:
    a = sys.argv[1:]
    only = a[a.index("--only") + 1].split(",") if "--only" in a else None
    if not a or a[0] == "smoke":
        src = RUNS / (RUNS / "PUBLISHED").read_text().strip()
        print(run_all("_smoke", "fake", only, source=src))
    elif a[0] == "record":
        rid = a[a.index("--run-id") + 1] if "--run-id" in a else f"{date.today().isoformat()}-recorded"
        print(run_all(rid, "record", only))
    elif a[0] == "replay":
        src = RUNS / a[1]
        rid = a[a.index("--run-id") + 1] if "--run-id" in a else f"{a[1]}-replay"
        rdir = run_all(rid, "replay", only, source=src)
        from .aggregate import compare_replay
        compare_replay(src, rdir)
        print(rdir)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
