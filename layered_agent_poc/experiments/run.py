"""Experiment runner. Every number in the article comes from files this script writes under runs/<run-id>/.

`uv run poc run --plan <plan>` is the usual way in: it resolves a plan (plans/*.yaml, see experiments/plan.py), saves it
as runs/<run-id>/plan.yaml and calls `experiments.run all --plan runs/<run-id>/plan.yaml`. The flags below still work
and build the same plan from the command line.

    uv run python -m experiments.run all --run-id 2026-09-17 --k 3 [--model-tests]   # every stage below, then the reports
    uv run python -m experiments.run tests [--model-tests]                            # pytest (JUnit) and import contracts
    uv run python -m experiments.run workflow --models gpt-oss:20b qwen3:8b --k 3     # E2, E3, E7, E8, E9
    uv run python -m experiments.run faults                                          # E5, E6
    uv run python -m experiments.run crash                                           # E4 (layered)
    uv run python -m experiments.run monolith --k 3                                  # E4, E6, E9 baseline
    uv run python -m experiments.run change                                          # E1 requirement-change patches
    uv run python -m experiments.run export                                          # diagram data files
    uv run python -m experiments.run report                                          # runs/<run-id>/report/

Each run keeps its console output in runs/<run-id>/run.log, each stage's start, end and result in stages.json, and
what kind of run it was in run.json.

Live runs record every model response next to each scenario (traffic/), so any run can be replayed later without Ollama:

    uv run python -m experiments.run all --run-id my-replay --replay-from 2026-09-17-recorded

All model calls go to the local Ollama server. Approvals are made by the synthetic user `alice` through the same
service call a channel uses.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import select
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
# How model traffic is handled in this process: {"mode": None | "record" | "replay", "base": run dir, "source": run dir}
TRAFFIC: dict[str, Any] = {"mode": None, "base": None, "source": None}
# The plan this process runs (experiments.plan); main() sets it from --plan or from the flags.
PLAN: dict[str, Any] = {}
REQUEST = ("Checkout API latency increased after the 10:15 production deployment. Investigate the cause, recommend the "
           "safest remediation, apply the approved action and update the incident.")


# ============================================================================ helpers
def traffic_env(d: Path) -> dict[str, str]:
    """Record this scenario's model traffic into d/traffic, or replay it from the same scenario of another run."""
    mode = TRAFFIC["mode"]
    if not mode:
        return {"LAP_MODEL_TRAFFIC": ""}
    where = d / "traffic" if mode == "record" else TRAFFIC["source"] / d.relative_to(TRAFFIC["base"]) / "traffic"
    # a fresh knowledge index per scenario, so its embedding calls are recorded (and then replayed) too
    return {"LAP_MODEL_TRAFFIC": f"{mode}:{where}", "LAP_KNOWLEDGE_INDEX": str(d / "knowledge_index.json")}


def env_for(d: Path, **extra: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update({"LAP_PLATFORM_DB": str(d / "platform.db"), "LAP_ENTERPRISE_DB": str(d / "enterprise.db"),
                "LAP_RUNS_DIR": str(d / "otel"), "LAP_KNOWLEDGE_INDEX": str(ROOT / "var" / "knowledge_index.json")})
    env.update(traffic_env(d))
    env.update(extra)
    return env


def fresh_world(d: Path):
    """A clean scenario folder with the enterprise systems reset. What an earlier attempt left in d (its platform database,
    recorded traffic, spans and results) moves to _superseded/ next to it, so a re-run never picks up old state."""
    from mock_enterprise.world import World

    if d.exists() and any(d.iterdir()):
        old = d.parent / "_superseded" / f"{d.name}-{time.strftime('%Y%m%dT%H%M%S')}"
        old.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(d), str(old))
    d.mkdir(parents=True, exist_ok=True)
    w = World(d / "enterprise.db")
    w.reset()
    return w


def world_outcome(w) -> dict[str, Any]:
    """Outcome checks computed from the systems of record, so they apply to both implementations."""
    calls = [r[0] for r in w._db.execute("SELECT tool FROM calls ORDER BY id")]
    rollbacks = w.executions("source_control.rollback_release")
    k8s = w.executions("kubernetes.rollback_deployment")
    notes = w.notes("INC-4917")
    first_rb = next((i for i, c in enumerate(calls) if c == "source_control.rollback_release"), None)
    first_update = next((i for i, c in enumerate(calls) if c == "itsm.update_incident"), None)
    verified = first_rb is not None and any(c == "observability.query_latency" for c in calls[first_rb:first_update])
    return {
        "rollback_executions": len(rollbacks), "rollback_targets": [r["args"].get("target_version") for r in rollbacks],
        "kubernetes_rollbacks": len(k8s), "incident_updates": len(notes),
        "final_version": w.version("checkout-api", "production"), "incident_active": w.incident_active("checkout-api", "production"),
        "authoritative_rollback": len(rollbacks) >= 1 and all(t == "v4.16" for t in [r["args"].get("target_version") for r in rollbacks]) and not k8s,
        "write_exactly_once": len(rollbacks) == 1,
        "verified_before_update": bool(verified and first_update is not None),
        "tool_calls": len(calls),
    }


def save(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str))


# ============================================================================ E2 E3 E7 E8 E9 · layered workflow
async def one_workflow(d: Path, model: str, channel: str = "cli", faults: dict[str, tuple[str, int, float]] | None = None,
                       arm_at: str = "approval") -> dict[str, Any]:
    world = fresh_world(d)
    if arm_at == "start":
        for tool, (mode, times, delay) in (faults or {}).items():
            world.arm_fault(tool, mode, times, delay)
    os.environ.update(env_for(d, LAP_MODEL_REASONING=model, LAP_MODEL_SUMMARY=model))
    from agent_platform.contracts import ApprovalDecision, StartInvestigation
    from agent_platform.service import PlatformService

    t0 = time.perf_counter()
    async with PlatformService.open() as svc:
        try:
            view = await svc.start_investigation(StartInvestigation(incident_id="INC-4917", request=REQUEST, user_id="alice", channel=channel))
        except Exception as exc:
            wf = svc.workflows()[-1]["workflow_id"]
            view = svc.workflow(wf) | {"error": f"{type(exc).__name__}: {exc}"}
        t_wait = time.perf_counter()
        wf = view["workflow_id"]
        if view["status"] == "WAITING_APPROVAL":
            for tool, (mode, times, delay) in (faults or {}).items() if arm_at == "approval" else ():
                world.arm_fault(tool, mode, times, delay)
            await asyncio.sleep(1.0)  # a human takes a moment; the trace shows the gap
            try:
                view = await svc.decide_approval(ApprovalDecision(workflow_id=wf, approver_id="alice", approve=True))
            except Exception as exc:
                view = svc.workflow(wf) | {"error": f"{type(exc).__name__}: {exc}"}
        t_end = time.perf_counter()
        rollbacks = len(world.executions("source_control.rollback_release"))
        rec = {
            "model": model, "channel": channel, "workflow_id": wf, "status": view["status"], "error": view.get("error"),
            "seconds_to_approval": round(t_wait - t0, 1), "seconds_total": round(t_end - t0, 1),
            "view": view, "events": svc.events(wf), "audit": svc.audit_log(wf), "usage": svc.model_usage(wf),
            "eval": svc.evaluate(wf, backend_rollbacks=rollbacks), "world": world_outcome(world),
            "trace": svc.trace(wf), "replays": world.replay_count("source_control.rollback_release"),
        }
        cp = svc.store.latest_checkpoint(wf)
        rec["investigation"] = (cp or {}).get("state", {}).get("investigation")
        rec["proposals"] = (cp or {}).get("state", {}).get("proposals")
    save(d / "record.json", rec)
    return rec


def summarize_workflows(records: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for r in records:
        m = out.setdefault(r["model"], {"runs": 0, "completed": 0, "eval_all_pass": 0, "check_pass": {}, "seconds_to_approval": [],
                                        "seconds_total": [], "tokens": [], "model_calls": [], "tool_calls": [], "statuses": []})
        m["runs"] += 1
        m["statuses"].append(r["status"])
        m["completed"] += r["status"] == "COMPLETED"
        m["eval_all_pass"] += bool(r["eval"]["ok"])
        for c in r["eval"]["checks"]:
            m["check_pass"][c["name"]] = m["check_pass"].get(c["name"], 0) + int(c["passed"])
        m["seconds_to_approval"].append(r["seconds_to_approval"])
        m["seconds_total"].append(r["seconds_total"])
        m["tokens"].append(sum(u["input_tokens"] + u["output_tokens"] for u in r["usage"]))
        m["model_calls"].append(len(r["usage"]))
        m["tool_calls"].append(r["world"]["tool_calls"])
    for m in out.values():
        m["pass_k"] = f"{m['eval_all_pass']}/{m['runs']}"
    return out


async def exp_workflow(base: Path, models: list[str], k: int) -> dict[str, Any]:
    """Runs --k workflows per model. Re-running one model keeps the others: an earlier attempt at the same run moves to
    workflow/_superseded/, and the summary is rebuilt from every record on disk. The stage fails if any run did not complete."""
    failed: list[str] = []
    for model in models:
        for i in range(1, k + 1):
            d = base / "workflow" / model.replace(":", "_") / f"run{i}"
            if d.exists():
                old = base / "workflow" / "_superseded" / d.parent.name / f"{d.name}-{time.strftime('%Y%m%dT%H%M%S')}"
                old.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(d), str(old))
            print(f"[workflow] {model} run {i}/{k} ...", flush=True)
            rec = await one_workflow(d, model)
            if rec["status"] != "COMPLETED":
                failed.append(f"{model} run {i}: {rec['status']}")
            print(f"  -> {rec['status']} evals {rec['eval']['passed']}/{rec['eval']['total']} in {rec['seconds_total']} s"
                  + (f" · {rec['error']}" if rec.get("error") else ""), flush=True)
    records = [json.loads(p.read_text()) for p in sorted((base / "workflow").glob("*/run*/record.json"))]
    summary = summarize_workflows(records)
    save(base / "workflow" / "summary.json", summary)
    if failed:
        raise RuntimeError(f"{len(failed)} run(s) did not complete: {'; '.join(failed)}")
    return summary


# ============================================================================ E5 E6 · faults
def fault_map(inject: list[dict[str, Any]] | None) -> dict[str, tuple[str, int, float]]:
    return {f["tool"]: (f["mode"], int(f.get("times", 1)), float(f.get("delay_s", 4.0))) for f in inject or []}


async def exp_faults(base: Path) -> dict[str, Any]:
    from experiments.plan import fault_text

    cfg = PLAN["faults"]
    d = base / "faults"
    print(f"[faults] {cfg['model']}, armed at {cfg['arm_at']}: {fault_text(cfg['inject'])} ...", flush=True)
    rec = await one_workflow(d, cfg["model"], faults=fault_map(cfg["inject"]), arm_at=cfg["arm_at"])
    spans = rec["trace"]
    tool_spans = [s for s in spans if s["name"].startswith("execute_tool ")]
    out = {
        "status": rec["status"], "eval": rec["eval"],
        "rollback": {"attempts": rec["view"]["remediation"]["attempts"] if rec["view"].get("remediation") else None,
                     "replayed": (rec["view"].get("remediation") or {}).get("replayed"),
                     "backend_executions": rec["world"]["rollback_executions"], "backend_replays": rec["replays"]},
        "verify_latency_calls": [{"attempts": s["attributes"].get("lap.retry.attempts"), "step": s["attributes"].get("lap.step")}
                                 for s in tool_spans if s["name"].endswith("query_latency") and s["attributes"].get("lap.step") == "verify"],
        "timeouts_in_audit": sum(1 for a in rec["audit"] if a["event"] == "invocation.timeout"),
        "injected": cfg["inject"], "arm_at": cfg["arm_at"], "model": cfg["model"],
    }
    save(d / "summary.json", out)
    print(f"  -> {json.dumps(out['rollback'])}, verify attempts {out['verify_latency_calls']}", flush=True)
    return out


# ============================================================================ E4 · crash and resume (layered)
def lap(args: list[str], env: dict[str, str]) -> tuple[subprocess.CompletedProcess, float]:
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, "-m", "agent_platform.channels.cli", *args], cwd=ROOT, env=env, capture_output=True, text=True)
    for line in p.stderr.splitlines():
        if line.startswith("[traffic]"):  # replay drift warnings from the child process
            print(line, file=sys.stderr, flush=True)
    return p, round(time.perf_counter() - t0, 1)


def usage_tokens(db: Path, wf: str) -> list[dict[str, Any]]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute("SELECT agent, model, input_tokens, output_tokens FROM model_usage WHERE workflow_id=? ORDER BY id", (wf,))]


def exp_crash(base: Path) -> dict[str, Any]:
    """One workflow, killed with SIGKILL at each of the plan's kill points in turn. Each new process does what a person
    or a supervisor would do next: approve a workflow that waits for approval, otherwise resume it."""
    cfg = PLAN["crash"]
    d = base / "crash"
    world = fresh_world(d)
    for tool, (mode, times, delay) in fault_map(cfg.get("inject")).items():
        world.arm_fault(tool, mode, times, delay)
    env = env_for(d, LAP_MODEL_REASONING=cfg["model"], LAP_MODEL_SUMMARY=cfg["model"])
    points = list(cfg["kill_at"])
    db = d / "platform.db"
    sequence: list[dict[str, Any]] = []

    def launch(args: list[str], label: str) -> dict[str, Any]:
        crash_on = points.pop(0) if points else None
        print(f"[crash] process {len(sequence) + 1}: lap {label}" + (f", SIGKILL at {crash_on}" if crash_on else "") + " ...", flush=True)
        proc, secs = lap(args, {**env, "LAP_CRASH_ON": crash_on or ""})
        entry = {"process": len(sequence) + 1, "command": f"lap {label}", "crash_on": crash_on, "returncode": proc.returncode, "seconds": secs}
        sequence.append(entry)
        return entry

    def status(wf: str) -> dict[str, Any]:
        st, _ = lap(["--json", "status", wf], env)
        return json.loads(st.stdout)

    first = launch(["run", "INC-4917", "--as", "alice"], "run INC-4917 --as alice")
    wf = sqlite3.connect(db).execute("SELECT id FROM workflows LIMIT 1").fetchone()[0]
    calls_after_first = len(usage_tokens(db, wf))
    first["status_after"] = status(wf)["status"]
    rollbacks_after: dict[int, int] = {}
    for _ in range(len(cfg["kill_at"]) + 4):  # each kill costs at most one more process; the rest is a safety bound
        view = status(wf)
        if view["status"] in ("COMPLETED", "FAILED", "REJECTED", "CANCELLED"):
            break
        if view["status"] == "WAITING_APPROVAL":
            entry = launch(["approve", wf, "--as", "alice"], "approve --as alice")
        else:
            entry = launch(["--json", "resume", wf], "resume")
        entry["status_after"] = status(wf)["status"]
        rollbacks_after[entry["process"]] = len(world.executions("source_control.rollback_release"))
        if entry["returncode"] not in (0, -9):
            break
    final = status(wf)
    usage = usage_tokens(db, wf)
    con = sqlite3.connect(db)
    pids = [r[0] for r in con.execute("SELECT DISTINCT pid FROM workflow_events WHERE workflow_id=? ORDER BY id", (wf,))]
    checkpoints = [dict(zip(("seq", "step", "next_step", "pid"), r)) for r in
                   con.execute("SELECT seq, step, next_step, pid FROM checkpoints WHERE workflow_id=? ORDER BY seq", (wf,))]
    approve = next((e for e in sequence if e["command"].startswith("lap approve")), None)
    last = sequence[-1]
    out = {
        "workflow_id": wf, "kill_at": cfg["kill_at"], "model": cfg["model"], "sequence": sequence,
        # the first process, the approving process and the last process, in the shape the reports read
        "run": {"returncode": first["returncode"], "seconds": first["seconds"], "status_after": first["status_after"]},
        "approve": {"returncode": approve["returncode"], "seconds": approve["seconds"], "status_after": approve["status_after"],
                    "backend_rollbacks_after_crash": min(1, rollbacks_after.get(approve["process"], 0))} if approve else None,
        "resume": {"returncode": last["returncode"], "seconds": last["seconds"], "status": final["status"],
                   "remediation_replayed": (final.get("remediation") or {}).get("replayed")},
        "backend_rollbacks": len(world.executions("source_control.rollback_release")),
        "processes": len(pids), "checkpoints": checkpoints,
        "model_calls_before_crash": calls_after_first, "model_calls_after_resume": len(usage) - calls_after_first,
        "tokens_before_crash": sum(u["input_tokens"] + u["output_tokens"] for u in usage[:calls_after_first]),
        "tokens_after_crash": sum(u["input_tokens"] + u["output_tokens"] for u in usage[calls_after_first:]),
    }
    save(d / "summary.json", out)
    print(f"  -> {json.dumps({k: out[k] for k in ('backend_rollbacks', 'processes', 'tokens_before_crash', 'tokens_after_crash')})}, "
          f"final {final['status']}", flush=True)
    if final["status"] != "COMPLETED":
        raise RuntimeError(f"the crashed workflow ended {final['status']} after {len(sequence)} processes")
    return out


# ============================================================================ monolith baseline
async def monolith_once(d: Path, faults: dict[str, tuple[str, int, float]] | None = None) -> dict[str, Any]:
    world = fresh_world(d)
    for tool, (mode, times, delay) in (faults or {}).items():
        world.arm_fault(tool, mode, times, delay)
    os.environ["LAP_ENTERPRISE_DB"] = str(d / "enterprise.db")
    os.environ.update(traffic_env(d))
    from monolith.incident_agent import IncidentAgent

    approvals: list[dict[str, Any]] = []

    async def approver(tool: str, args: dict[str, Any]) -> bool:
        approvals.append({"tool": tool, "args": args})
        return True

    agent = IncidentAgent(approver=approver)
    t0 = time.perf_counter()
    await agent.connect()
    try:
        answer = await agent.run(REQUEST + " The incident id is INC-4917.")
    except Exception as exc:
        answer = f"crashed: {type(exc).__name__}: {exc}"
    finally:
        await agent.close()
    rec = {"seconds": round(time.perf_counter() - t0, 1), "tokens": agent.token_count, "answer": answer[:600],
           "approvals_asked": approvals, "world": world_outcome(world)}
    save(d / "record.json", rec)
    return rec


def monolith_crash(d: Path) -> dict[str, Any]:
    """Kill the monolith while it waits for approval; a restart has nothing to resume."""
    fresh_world(d)
    env = env_for(d)
    t0 = time.perf_counter()
    p = subprocess.Popen([sys.executable, "-m", "monolith.cli", "run", "INC-4917"], cwd=ROOT, env=env,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    buf = b""
    prompt_at = None
    while time.perf_counter() - t0 < 900:
        r, _, _ = select.select([p.stdout], [], [], 1.0)
        if r:
            chunk = os.read(p.stdout.fileno(), 4096)
            if not chunk:
                break
            buf += chunk
            if b"Approve?" in buf:
                prompt_at = time.perf_counter() - t0
                break
    p.send_signal(signal.SIGKILL)
    p.wait()
    # what the monolith itself left behind (the recorded model traffic belongs to the experiment, not the monolith)
    leftovers = [str(x.relative_to(d)) for x in d.rglob("*") if x.is_file() and not x.name.startswith("enterprise.db")
                 and "traffic" not in x.relative_to(d).parts and x.name != "knowledge_index.json"]
    out = {"seconds_until_approval_prompt": round(prompt_at, 1) if prompt_at else None, "returncode": p.returncode,
           "state_left_behind": leftovers, "resume_command": None,
           "note": "The monolith keeps the conversation in memory; after SIGKILL a restart starts the investigation over."}
    save(d / "crash.json", out)
    return out


async def exp_monolith(base: Path, k: int) -> dict[str, Any]:
    cfg = PLAN["monolith"]
    runs = []
    for i in range(1, k + 1):
        print(f"[monolith] run {i}/{k} (auto-approve) ...", flush=True)
        r = await monolith_once(base / "monolith" / f"run{i}")
        print(f"  -> {json.dumps(r['world'])[:200]} in {r['seconds']} s", flush=True)
        runs.append(r)
    lost = crash = None
    if cfg.get("lost_response"):
        print("[monolith] lost rollback response ...", flush=True)
        lost = await monolith_once(base / "monolith" / "lost-response",
                                   faults={"source_control.rollback_release": ("lose_response", 1, 4.0)})
        print(f"  -> rollbacks executed {lost['world']['rollback_executions']}", flush=True)
    if cfg.get("crash"):
        print("[monolith] SIGKILL while waiting for approval ...", flush=True)
        crash = monolith_crash(base / "monolith" / "crash")
    out = {"runs": [{k2: r[k2] for k2 in ("seconds", "tokens", "world", "approvals_asked")} for r in runs],
           "lost_response": {k2: lost[k2] for k2 in ("seconds", "tokens", "world")} if lost else None, "crash": crash,
           "outcomes": {c: sum(bool(r["world"][c]) for r in runs) for c in ("authoritative_rollback", "write_exactly_once", "verified_before_update")},
           "kubernetes_rollbacks": sum(r["world"]["kubernetes_rollbacks"] for r in runs)}
    save(base / "monolith" / "summary.json", out)
    return out


# ============================================================================ diagram data
def kind_of(name: str) -> str:
    head = name.split(" ")[0]
    return {"invoke_workflow": "workflow", "workflow.step": "step", "invoke_agent": "agent", "chat": "chat",
            "execute_tool": "tool", "policy.evaluate": "policy", "approval.request": "approval", "approval.decide": "approval",
            "checkpoint.save": "checkpoint", "context.assemble": "context", "memory.read": "memory", "memory.write": "memory",
            "knowledge.retrieve": "knowledge", "embeddings": "embeddings"}.get(head, "")


def trace_summary(rec: dict[str, Any], run_id: str) -> dict[str, Any]:
    spans = [s for s in rec["trace"] if kind_of(s["name"])]
    by_id = {s["span_id"]: s for s in rec["trace"]}

    def depth(s: dict[str, Any]) -> int:
        """Nesting below the workflow; every process segment counts as the same workflow bar."""
        if kind_of(s["name"]) == "workflow":
            return 0
        n, p = 1, s["parent_id"]
        while p in by_id:
            if kind_of(by_id[p]["name"]) not in ("", "workflow"):
                n += 1
            p = by_id[p]["parent_id"]
        return n

    segments = sorted([s for s in spans if s["name"].startswith("invoke_workflow")], key=lambda s: s["start_ns"])
    seg1_end = segments[0]["end_ns"]
    seg2_start = segments[1]["start_ns"] if len(segments) > 1 else seg1_end
    wait_ms = (seg2_start - seg1_end) / 1e6
    t0 = segments[0]["start_ns"]
    GAP = 0  # the drawn axis excludes the approval wait

    def rel(ns: int) -> float:
        return (ns - t0) / 1e6 if ns <= seg1_end else (ns - t0) / 1e6 - wait_ms + GAP

    keep, chats, tools = [], 0, 0
    for s in sorted(spans, key=lambda s: s["start_ns"]):
        k, dep = kind_of(s["name"]), depth(s)
        if k == "workflow" and s is not segments[0]:
            continue  # later segments are drawn as one continuous workflow bar
        if k == "policy" and dep > 2:
            continue
        if k in ("memory", "embeddings", "knowledge") and dep > 2:
            continue
        if k == "checkpoint":
            continue
        if k == "chat" and "diagnosis" in str(s["attributes"].get("gen_ai.agent.name")):
            chats += 1
            if chats > 2:
                continue
        if k == "tool" and s["attributes"].get("lap.step") == "investigate":
            tools += 1
            if tools > 2:
                continue
        note = None
        a = s["attributes"]
        if k == "chat":
            note = f"{a.get('gen_ai.usage.input_tokens')}→{a.get('gen_ai.usage.output_tokens')} tok"
        elif k == "tool":
            bits = [a.get("lap.policy.decision", "")]
            if a.get("lap.retry.attempts", 1) and a.get("lap.retry.attempts", 1) > 1:
                bits.append(f"{a['lap.retry.attempts']} attempts")
            if a.get("lap.idempotency.replayed"):
                bits.append("replayed")
            note = " · ".join(b for b in bits if b)
        elif k == "agent":
            steps = a.get("lap.agent.steps", 0)
            note = (f"{steps} turns · {a.get('lap.agent.tool_calls', 0)} tool calls" if steps else "structured answer, no tools")
            if a.get("lap.agent.repaired"):
                note += " · 1 repair"
        elif k == "policy":
            note = a.get("lap.policy.decision")
        name = s["name"]
        if k == "workflow":
            end = rel(segments[-1]["end_ns"])
            keep.append({"name": name, "depth": 0, "start_ms": 0, "duration_ms": round(end, 1), "kind": k,
                         "note": f"{len(segments)} process segments"})
            continue
        keep.append({"name": name, "depth": min(dep, 5), "start_ms": round(rel(s["start_ns"]), 1),
                     "duration_ms": round((s["end_ns"] - s["start_ns"]) / 1e6, 1), "kind": k, "note": note})
        if k == "agent" and "diagnosis" in name:
            extra_chats = sum(1 for x in spans if kind_of(x["name"]) == "chat" and "diagnosis" in str(x["attributes"].get("gen_ai.agent.name"))) - 2
            if extra_chats > 0:
                keep[-1]["note"] += f" (2 of {extra_chats + 2} model calls shown)"
    # the approval wait, drawn as a fixed-width gap
    appr = next((s for s in spans if s["name"] == "approval.request"), None)
    if appr:
        keep.append({"name": "human approval (alice)", "depth": 1, "start_ms": round(rel(seg1_end), 1), "duration_ms": 0,
                     "kind": "approval", "note": f"waited {wait_ms / 1000:.1f} s"})
    # the human decision is drawn as the gap above, not as its own bar
    keep = [k for k in keep if k["name"] not in ("approval.request", "approval.decide")]
    keep.sort(key=lambda k: (k["start_ms"], k["depth"]))
    trace = rec["trace"]
    usage = rec["usage"]
    policy = {"ALLOW": 0, "REQUIRE_APPROVAL": 0, "DENY": 0}
    for a in rec["audit"]:
        if a["event"] == "policy.decision":
            policy[a["decision"]] += 1
    wall = (segments[-1]["end_ns"] - segments[0]["start_ns"]) / 1e6
    return {
        "placeholder": False, "run_id": run_id, "model": rec["model"], "workflow_id": rec["workflow_id"],
        "spans": keep,
        "totals": {"wall_ms": round(wall), "active_ms": round(wall - wait_ms), "approval_wait_ms": round(wait_ms),
                   "model_calls": len(usage), "input_tokens": sum(u["input_tokens"] for u in usage),
                   "output_tokens": sum(u["output_tokens"] for u in usage),
                   "tool_calls": sum(1 for s in trace if s["name"].startswith("execute_tool")),
                   "retries": sum(max(0, int(s["attributes"].get("lap.retry.attempts", 1)) - 1) for s in trace if s["name"].startswith("execute_tool")),
                   "policy": policy, "checkpoints": rec["view"]["checkpoints"],  # the store's count, as `lap status` shows it
                   "evals": f"{rec['eval']['passed']}/{rec['eval']['total']}"},
    }


def poc_facts(tests: int) -> dict[str, Any]:
    def count(pkg: str | list[str]) -> tuple[int, int]:
        pkgs = [pkg] if isinstance(pkg, str) else pkg
        files = [f for p in pkgs for f in (ROOT / p).rglob("*.py") if f.name != "__init__.py" and "__pycache__" not in f.parts]
        return len(files), sum(len(f.read_text().splitlines()) for f in files)

    layers = []
    for key, pkg in [("experience", "agent_platform/channels"), ("orchestration", "agent_platform/orchestration"),
                     ("runtime", "agent_platform/agents"),
                     ("context", ["agent_platform/context", "agent_platform/memory", "agent_platform/knowledge"]),
                     ("actions", "agent_platform/actions"), ("models", "agent_platform/models"),
                     ("crosscutting", ["agent_platform/identity", "agent_platform/telemetry", "agent_platform/evals"])]:
        files, loc = count(pkg)
        layers.append({"key": key, "package": pkg if isinstance(pkg, str) else " · ".join(p.split("/")[-1] for p in pkg),
                       "files": files, "loc": loc})
    from agent_platform.config import capabilities, policies

    return {"placeholder": False, "layers": layers, "mcp_servers": 5, "tools": len(capabilities()["tools"]),
            "channels": ["CLI", "REST (FastAPI)", "Slack-shaped chat webhook"],
            "models": ["gpt-oss:20b", "qwen3:8b", "nomic-embed-text"], "embedding_models": ["nomic-embed-text"],
            "policy_rules": len(policies()["rules"]), "tests": tests, "experiments": 9,
            "real": ["MCP protocol (SDK 2.2.0, stdio)", "Ollama models", "SQLite durability", "SIGKILL crashes", "OpenTelemetry spans"],
            "simulated": ["enterprise systems (INC-4917)", "Slack-shaped payloads", "human approvals", "injected faults", "synthetic identities"]}


def exp_export(base: Path, to_article: bool = False) -> None:
    # With --article, the figure data also goes to the article's diagram generator next to the POC (the article workspace).
    generator = ROOT.parent / "diagrams" / "generator"
    gen = generator / "data" if to_article and generator.is_dir() else None
    rec_path = base / "faults" / "record.json"
    clean = sorted((base / "workflow" / "gpt-oss_20b").glob("run*/record.json"))
    source = clean[0] if clean else rec_path
    rec = json.loads(source.read_text())
    ts = trace_summary(rec, base.name)
    if gen:
        save(gen / "trace-summary.json", ts)
    save(base / "diagram-data" / "trace-summary.json", ts)
    tests = int(json.loads((base / "tests.json").read_text())["passed"]) if (base / "tests.json").exists() else 0
    facts = poc_facts(tests)
    if gen:
        save(gen / "poc-facts.json", facts)
    save(base / "diagram-data" / "poc-facts.json", facts)
    cs = json.loads((ROOT / "runs" / "change-scope.json").read_text())
    scope = {"placeholder": False, "changes": [{"id": c["id"], "title": c["title"],
                                                **{side: {k: c[side][k] for k in ("files", "added", "removed", "concerns")}
                                                   for side in ("monolith", "layered")}} for c in cs["changes"]]}
    if gen:
        save(gen / "change-scope.json", scope)
    save(base / "diagram-data" / "change-scope.json", scope)
    where = f"{base.relative_to(ROOT)}/diagram-data" + (f" and {gen.relative_to(ROOT.parent)}" if gen else "")
    print(f"[export] trace from {source.relative_to(ROOT)}; wrote diagram data to {where}")


# ============================================================================ tests
def exp_tests(base: Path, model_tests: bool) -> dict[str, Any]:
    """pytest with JUnit output, plus the import contracts. Results go to runs/<run-id>/tests/."""
    import xml.etree.ElementTree as ET

    d = base / "tests"
    d.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("LAP_")}
    plan = [("Fast tests", "not ollama", "fast.xml", "uv run pytest -m \"not ollama\" (no model needed)")]
    if model_tests and TRAFFIC["mode"] == "replay":
        print("[tests] replay run: the end-to-end model tests need Ollama, so they are skipped", flush=True)
        model_tests = False
    if model_tests:
        plan.append(("Model tests", "ollama", "ollama.xml", "uv run pytest -m ollama (end-to-end against the local models)"))
    sittings, counts = [], {"passed": 0, "failed": 0, "skipped": 0, "fast": 0, "ollama": 0}
    for label, marker, fname, note in plan:
        print(f"[tests] {label} ...", flush=True)
        t0 = time.perf_counter()
        r = subprocess.run([sys.executable, "-m", "pytest", "-m", marker, f"--junitxml={d / fname}", "-p", "no:cacheprovider"],
                           cwd=ROOT, env=env, capture_output=True, text=True)
        (d / fname.replace(".xml", ".log")).write_text(r.stdout + r.stderr)
        tree = ET.parse(d / fname).getroot()
        cases = list(tree.iter("testcase"))
        failed = sum(1 for c in cases if c.find("failure") is not None or c.find("error") is not None)
        skipped = sum(1 for c in cases if c.find("skipped") is not None)
        passed = len(cases) - failed - skipped
        counts["passed"] += passed
        counts["failed"] += failed
        counts["skipped"] += skipped
        counts["fast" if marker == "not ollama" else "ollama"] = passed
        sittings.append({"label": label, "date": date.today().isoformat(), "kind": "junit", "file": fname,
                         "note": f"{note}. {passed} passed, {failed} failed, {skipped} skipped in {time.perf_counter() - t0:.0f} s."})
        print(f"  -> {passed} passed, {failed} failed, {skipped} skipped", flush=True)
    lint = subprocess.run([str(Path(sys.executable).parent / "lint-imports")], cwd=ROOT, env=env, capture_output=True, text=True)
    (d / "lint-imports.log").write_text(lint.stdout + lint.stderr)
    print(f"  -> import contracts: {'kept' if lint.returncode == 0 else 'BROKEN'}", flush=True)
    save(d / "sittings.json", sittings)
    save(base / "tests.json", counts | {"contracts_kept": lint.returncode == 0})
    if counts["failed"] or lint.returncode:
        raise RuntimeError(f"{counts['failed']} test(s) failed, contracts kept: {lint.returncode == 0}")
    return counts


def exp_change(base: Path) -> None:
    from experiments.change_scope import run as change_scope

    change_scope.main(out=base / "change-scope.json")


# ============================================================================ main
class Tee:
    """Copy everything printed during a run into runs/<run-id>/run.log."""

    def __init__(self, stream, path: Path):
        self.stream, self.file = stream, path.open("a", encoding="utf-8")

    def write(self, text: str) -> int:
        self.file.write(text)
        self.file.flush()
        return self.stream.write(text)

    def flush(self) -> None:
        self.stream.flush()
        self.file.flush()


def record_stage(base: Path, stage: str, start: float, end: float, ok: bool, error: str | None) -> None:
    path = base / "stages.json"
    stages = [s for s in (json.loads(path.read_text()) if path.exists() else []) if s["stage"] != stage]
    stages.append({"stage": stage, "start": round(start, 3), "end": round(end, 3), "ok": ok, "error": error})
    save(path, sorted(stages, key=lambda s: s["start"]))


STAGES = ["tests", "faults", "crash", "monolith", "workflow", "change", "export", "report"]


def main() -> None:
    p = argparse.ArgumentParser(description="Run the POC's experiments; see the module docstring.")
    p.add_argument("what", choices=["all", *STAGES])
    p.add_argument("--run-id", default=date.today().isoformat())
    p.add_argument("--models", nargs="+", default=["gpt-oss:20b", "qwen3:8b"])
    p.add_argument("--k", type=int, default=3, help="runs per model (workflow) and per monolith scenario")
    p.add_argument("--model-tests", action="store_true", help="the tests stage also runs the end-to-end tests against Ollama")
    p.add_argument("--article", action="store_true", help="export also writes the figure data used by the article's diagrams")
    p.add_argument("--replay-from", metavar="RUN_ID", help="replay the model traffic recorded by an earlier run; no Ollama needed")
    p.add_argument("--no-record", action="store_true", help="do not record model traffic (live runs record it by default)")
    p.add_argument("--resume", action="store_true", help="skip stages that already passed in this run")
    p.add_argument("--profile", default="custom", help=argparse.SUPPRESS)  # set by `poc run`, kept in run.json
    p.add_argument("--plan", metavar="FILE", help="a run plan (plans/*.yaml); its models, runs, experiments, faults and kill points win over the flags above")
    a = p.parse_args()
    from experiments import plan as plans

    saved = ROOT / "runs" / a.run_id / "plan.yaml"
    if not a.plan and a.what != "all" and saved.exists():  # a single stage re-run keeps the run's plan
        over = {k: v for k, v in (("models", a.models), ("runs", a.k)) if v != p.get_default(k if k == "models" else "k")}
        PLAN.update(plans.load(str(saved), over))
    elif a.plan:
        PLAN.update(plans.load(a.plan))
    else:  # the flags describe a plan too
        PLAN.update(plans.load(None, {"name": a.profile, "models": a.models, "runs": a.k, "tests": {"model_tests": a.model_tests},
                                      "model_answers": {"mode": "replay" if a.replay_from else "live", "replay_from": a.replay_from,
                                                        "record": not a.no_record},
                                      "faults": {"model": a.models[0]}, "crash": {"model": a.models[0]}}))
    ma = PLAN["model_answers"]
    a.models, a.k, a.profile = PLAN["models"], PLAN["runs"], PLAN["name"]
    a.replay_from = ma["replay_from"] if ma["mode"] == "replay" else None
    a.no_record = not ma.get("record", True)
    a.model_tests = PLAN["tests"]["model_tests"]
    if a.replay_from and a.replay_from == a.run_id:
        raise SystemExit("--replay-from must name another run: a replay writes into its own run folder")
    base = ROOT / "runs" / a.run_id
    base.mkdir(parents=True, exist_ok=True)
    if a.what != "report":  # rebuilding a report from the files does not belong in the run's console log
        sys.stdout = Tee(sys.stdout, base / "run.log")
    TRAFFIC["base"] = base
    if a.replay_from:
        source = ROOT / "runs" / a.replay_from
        if not any(source.rglob("traffic/chat.jsonl")):
            raise SystemExit(f"runs/{a.replay_from} has no recorded model traffic to replay")
        TRAFFIC.update(mode="replay", source=source)
    elif not a.no_record:
        TRAFFIC["mode"] = "record"
    # run.json describes the run as it was started; a resume or a single-stage re-run is appended under "reruns",
    # and a report rebuild leaves it alone
    now = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())  # noqa: E731
    meta_path = base / "run.json"
    old = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    this = {"mode": "replay" if a.replay_from else "live", "replay_from": a.replay_from, "recorded": TRAFFIC["mode"] == "record",
            "models": a.models}
    keep_meta = a.what != "report"
    if (a.what == "all" and not a.resume) or not old:
        meta = {"run_id": a.run_id, **this, "profile": a.profile, "k": a.k, "model_tests": a.model_tests and not a.replay_from,
                "experiments": PLAN["experiments"], "what": a.what,
                "host": {"platform": sys.platform, "python": sys.version.split()[0]}, "started": now()}
    else:
        meta = old
        if keep_meta:
            meta.setdefault("reruns", []).append({"what": a.what, "resume": a.resume, "at": now(), **this})
    if keep_meta:
        save(meta_path, meta)
        if not (base / "plan.yaml").exists() or (a.what == "all" and not a.resume):
            (base / "plan.yaml").write_text(plans.dump(PLAN))
    done = set()
    if a.resume and (base / "stages.json").exists():
        done = {s["stage"] for s in json.loads((base / "stages.json").read_text()) if s["ok"]}
    work = {
        "tests": lambda: exp_tests(base, a.model_tests),
        "faults": lambda: asyncio.run(exp_faults(base)),
        "crash": lambda: exp_crash(base),
        "monolith": lambda: asyncio.run(exp_monolith(base, a.k)),
        "workflow": lambda: asyncio.run(exp_workflow(base, a.models, a.k)),
        "change": lambda: exp_change(base),
        "export": lambda: exp_export(base, a.article),
        "report": lambda: print(f"[report] {report.build(a.run_id).relative_to(ROOT)}", flush=True),
    }
    from experiments import report

    failed = []
    default_models = p.get_default("models")
    for stage in ([*PLAN["experiments"], "report"] if a.what == "all" else [a.what]):
        # a re-run of the workflow stage for some models gets its own entry in stages.json
        label = f"{stage} ({', '.join(a.models)})" if stage == "workflow" and a.what != "all" and a.models != default_models else stage
        if label in done and stage != "report":
            print(f"=== STAGE {stage} SKIPPED (passed earlier; --resume)", flush=True)
            continue
        start = time.time()
        if stage == "report" and keep_meta:  # the report shows when the run finished
            meta.update(finished=now(), failed_stages=failed)
            save(meta_path, meta)
        print(f"=== STAGE {stage} START {time.strftime('%H:%M:%S', time.gmtime(start))}", flush=True)
        try:
            work[stage]()
            ok, error = True, None
        except Exception as exc:  # one failed stage should not stop the others, and the report shows it
            ok, error = False, f"{type(exc).__name__}: {exc}"
            failed.append(stage)
            print(f"  !! {error}", flush=True)
        end = time.time()
        if stage != "report":
            record_stage(base, label, start, end, ok, error)
        print(f"=== STAGE {stage} {'OK' if ok else 'FAILED'} {time.strftime('%H:%M:%S', time.gmtime(end))}", flush=True)
    if keep_meta:
        meta.update(finished=now(), failed_stages=failed)
        save(meta_path, meta)
    if a.what == "all":
        print(f"=== ALL DONE · report: runs/{a.run_id}/report/index.html · summary: runs/{a.run_id}/report/summary.md", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
