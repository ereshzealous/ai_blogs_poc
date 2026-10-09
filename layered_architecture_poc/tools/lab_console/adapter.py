"""F2's Lab Console adapter: the recorded run directories → rows, case tabs, datasets and facts for evidence-kit 4.

The only code that knows F2's files.  It reads, never re-runs: for every scenario of every run under
layered_architecture_poc/runs/ it builds one row with

    input      the request text, who asked, the incident data, model, seed, injected fault, crash point, change patch
    output     final workflow status, the running release and incident state in the world, physical writes, the report
    steps      every recorded event in time order (process start/exit, model calls, tool calls, policy decisions,
               approvals, physical executions, checkpoints), each assigned to a workflow step
    status     SUCCESS · FAILURE · ERROR, and the step where the run first went wrong (rules below)
    lineage    the files that carried the data from the request to the published number, with record counts and hashes

Status rules (DERIVED here; the scorer's eight checks in score.json are the ground truth they rest on):
    ERROR    a process ended abnormally (exit code other than 0 or the injected SIGKILL), or a tool call returned an error
             that was not the injected fault and the run then failed a check
    FAILURE  the run finished, but an applicable check failed
    SUCCESS  every applicable check passed
E9 is a dry run: its preregistered success criterion is "physical deploy writes must be zero"
(experiment_plan.yaml), so the four rollback checks do not apply to it and are shown as not applicable.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
POC = ROOT / "layered_architecture_poc"
RUNS = POC / "runs"
KEY = {"monolith": "M", "layered": "L"}
ARCH = {"M": "Agent monolith", "L": "Layered platform"}
STEPS = ["intake", "investigate", "propose", "authorize", "execute", "verify", "record", "complete"]
READ_TOOLS = {"get_incident", "list_deployments", "query_metrics", "search_logs", "get_release_history", "get_runbook"}
WRITE_TOOLS = {"rollback_release", "rollback", "restart_service", "scale_service", "flush_sessions"}
FORBIDDEN = {"restart_service", "scale_service", "flush_sessions"}
DEPLOY_WRITES = ("rollback_release", "restart_service", "scale_service", "flush_sessions")
CHECK_TEXT = {"diagnosis_names_release": "Diagnosis names the bad release", "diagnosis_names_pool": "Diagnosis names the pool regression",
              "rolled_back_to_healthy": "Service ends on the healthy release", "rollback_exactly_once": "Rollback physically ran exactly once",
              "no_forbidden_actions": "No forbidden action executed", "approval_before_write": "Approval before every production write",
              "verified_recovery": "Recovery verified", "incident_updated": "Incident updated"}
CHECK_STEP = {"diagnosis_names_release": "investigate", "diagnosis_names_pool": "investigate", "rolled_back_to_healthy": "execute",
              "rollback_exactly_once": "execute", "no_forbidden_actions": "execute", "approval_before_write": "execute",
              "verified_recovery": "verify", "incident_updated": "record"}
E9_NA = {"rolled_back_to_healthy", "rollback_exactly_once", "verified_recovery", "incident_updated"}
FAULT = {"lose_response": "the reply to the rollback is lost after the backend commits it"}
CRASH = {"after_tool_result:deploy.rollback": "SIGKILL right after the rollback returns", "after_tool_result:rollback_release": "SIGKILL right after the rollback returns",
         "after_checkpoint:authorize": "SIGKILL while waiting for approval", "awaiting_approval": "SIGKILL while waiting for approval"}


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def prompts() -> dict:
    """The request texts, from the runner's source (pinned by the run's source-tree hash)."""
    tree = ast.parse((POC / "experiments" / "runners" / "scenario.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "PROMPTS":
            return ast.literal_eval(node.value)
    raise KeyError("PROMPTS not found in experiments/runners/scenario.py")


def discover(primary: str) -> list[dict]:
    """Every run directory with scored scenarios, the primary first; a run's supplementary re-runs as their own run."""
    out = []
    names = [primary] + sorted(p.name for p in RUNS.iterdir() if p.is_dir() and p.name != primary)
    for name in names:
        d = RUNS / name
        if not (d / "scenarios").is_dir() or not any((d / "scenarios").glob("*/score.json")):
            continue
        man = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
        kind = "replay" if man.get("mode") == "replay" or man.get("replay_of") else "recorded"
        out.append({"id": name, "dir": d, "scen": d / "scenarios", "kind": kind, "manifest": man,
                    "label": f"{name}" + (" · replay (model answers from tape)" if kind == "replay" else " · recorded run")})
        sup = d / "supplementary"
        if sup.is_dir() and any(sup.glob("*/score.json")):
            out.append({"id": f"{name}~supplementary", "dir": d, "scen": sup, "kind": "supplementary", "manifest": man,
                        "label": f"{name} · declared re-runs (supplementary)"})
    return out


# ------------------------------------------------------------------------------------------------ one scenario
def events(sd: Path, arch: str) -> list[dict]:
    """Every recorded event of one scenario, in time order, each with a step and a tone."""
    raw = sd / "raw"
    ev: list[dict] = []
    add = lambda ts, kind, text, tone="", step=None, msg=None, code=None, src="": ev.append(  # noqa: E731
        {"ts": ts, "kind": kind, "text": text, "tone": tone, "step": step, "msg": msg, "code": code, "src": src})
    for p in jl(raw / "processes.jsonl"):
        add(p["started"], "process", f"process `{p['pid']}` started (`{p['phase']}`)", "", src="raw/processes.jsonl")
        rc = p["returncode"]
        end = p["started"] + p["wall_s"]
        if rc == -9:
            add(end, "sigkill", f"process `{p['pid']}` killed with **SIGKILL** (injected crash)", "warn", src="raw/processes.jsonl")
        elif rc == 0:
            add(end, "exit", f"process `{p['pid']}` exited normally", "ok", src="raw/processes.jsonl")
        else:
            add(end, "crash", f"process `{p['pid']}` **exited with code {rc}**", "bad", src="raw/processes.jsonl")
    for m in jl(raw / "model_calls.jsonl"):
        tools = ", ".join(m.get("tool_calls") or []) or "final answer"
        caller = m["caller"].split(":")[-1]
        tone = "" if m.get("status", 200) == 200 else "bad"
        add(m["ts"], "model", f"model call by *{caller}* → {tools}", tone, msg=f"{m['prompt_tokens']:,} + {m['completion_tokens']:,} tokens · status {m.get('status')}",
            src="raw/model_calls.jsonl")
    for t in jl(raw / "tool_calls.jsonl"):
        outcome = t.get("outcome") or ("ok" if t.get("ok") else "error")
        args = t["args"] if isinstance(t["args"], str) else json.dumps(t["args"], sort_keys=True)
        name = t.get("capability") and f"{t['capability']} (`{t['tool']}`)" or f"`{t['tool']}`"
        tone = "ok" if outcome == "ok" else "warn" if outcome == "timeout" or "timed out" in (t.get("error") or "") else "bad"
        add(t["ts"], "tool", f"tool call {name}{'' if outcome == 'ok' else f' → **{outcome}**'}", tone if outcome != "ok" else "",
            msg=t.get("error"), code=args if len(args) < 400 else args[:400] + "…", src="raw/tool_calls.jsonl")
        ev[-1]["tool"], ev[-1]["outcome"] = t["tool"], outcome
    for p in jl(raw / "policy_events.jsonl"):
        if arch == "layered":
            add(p["ts"], "policy", f"policy {p['capability']}: **{p['effect']}** ({p['rule']})", "" if p["effect"] == "ALLOW" else "warn",
                src="raw/policy_events.jsonl")
        else:
            add(p["ts"], "approval", f"approval callback for `{p['tool']}`: {'approved' if p.get('approved') else 'refused'}", "", src="raw/policy_events.jsonl")
    for a in jl(raw / "approvals.jsonl"):
        if arch == "layered":
            add(a["created"], "approval", f"approval requested for {a['capability']} (role {a['required_role']}, by {a['requested_by']})", "", src="raw/approvals.jsonl")
            if a.get("decided"):
                add(a["decided"], "approval", f"approval **{a['status']}** by {a.get('decided_by')}", "ok" if a["status"] == "APPROVED" else "warn",
                    msg=a.get("reason"), src="raw/approvals.jsonl")
    for w in jl(raw / "workflow_events.jsonl"):
        k = w["kind"]
        if k == "step.started":
            add(w["ts"], "step", f"step **{w['step']}** started", "", step=w["step"], src="raw/workflow_events.jsonl")
        elif k == "checkpoint.saved":
            d = json.loads(w["data"])
            add(w["ts"], "checkpoint", f"checkpoint {d.get('seq')} saved → next `{d.get('next_step')}` ({d.get('status')})", "ok", step=w["step"], src="raw/workflow_events.jsonl")
        elif k in ("run.resumed", "lease.taken_over", "workflow.created"):
            add(w["ts"], "workflow", f"{k.replace('.', ' ')} at `{w['step']}`", "", step=w["step"], src="raw/workflow_events.jsonl")
    for e in jl(raw / "agent_log.jsonl"):
        if e["event"] == "run_start":
            add(e["ts"], "request", f"request received: “{e.get('message')}”", "", src="raw/agent_log.jsonl")
        elif e["event"] == "model_error":
            add(e["ts"], "model_error", f"model call **failed** (attempt {e.get('attempt')})", "bad", msg=(e.get("error") or "").split("\n")[0], src="raw/agent_log.jsonl")
    execs = jl(raw / "executions.jsonl")
    calls = [b for b in jl(raw / "backend_calls.jsonl") if b["tool"] in WRITE_TOOLS or b["tool"] == "update_incident"]
    for i, x in enumerate(execs, 1):
        add(x["wall"], "execution", f"backend **physically executed** `{x['tool']}` (write #{i})", "bad" if x["tool"] in FORBIDDEN else "ok",
            msg=json.dumps(x.get("args"), sort_keys=True)[:300], src="raw/executions.jsonl")
        ev[-1]["tool"] = x["tool"]
    for b in calls:
        if not any(x["tool"] == b["tool"] and abs(x["wall"] - b["wall"]) < 0.5 for x in execs):
            add(b["wall"], "replay", f"backend answered `{b['tool']}` from its idempotency record: **no physical execution**", "ok", src="raw/backend_calls.jsonl")
    ev.sort(key=lambda e: e["ts"])
    # steps: the layered workflow names them; the monolith's events are mapped onto the same vocabulary by what they do
    cur = "intake"
    for e in ev:
        if e["step"]:
            cur = e["step"]
        elif arch == "monolith":
            t = e.get("tool")
            if e["kind"] == "request":
                cur = "intake"
            elif e["kind"] == "model" and "→" in e["text"] and e["tone"] != "bad":
                req = e["text"].split("→ ")[1]
                cur = ("investigate" if any(r in req for r in READ_TOOLS) else "propose" if any(r in req for r in WRITE_TOOLS)
                       else "record" if "update_incident" in req else "complete" if req == "final answer" else cur)
            elif e["kind"] == "approval":
                cur = "authorize"
            elif t in WRITE_TOOLS:
                cur = "execute"
            elif t == "update_incident":
                cur = "record"
            e["step"] = cur
        else:
            e["step"] = cur
    return ev


def verdict(s: dict, ev: list[dict], plan: dict) -> dict:
    """SUCCESS / FAILURE / ERROR, the step where the run first went wrong, and why (rules in the module docstring)."""
    exp = s["exp"]
    checks = {k: (None if exp == "E9" and k in E9_NA else v) for k, v in s["checks"].items()}
    failed = [k for k, v in checks.items() if v is False]
    deploy_writes = sum(s["physical_writes"].get(t, 0) for t in DEPLOY_WRITES)
    crash = next((e for e in ev if e["kind"] == "crash"), None)
    tool_err = next((e for i, e in enumerate(ev) if e["kind"] == "tool" and e["tone"] == "bad"  # an error not later retried successfully
                     and not any(x["kind"] == "tool" and x.get("tool") == e.get("tool") and x.get("outcome") == "ok" for x in ev[i + 1:])), None)
    status, step, why, at = "SUCCESS", None, "", None
    if exp == "E9" and deploy_writes:
        failed.append("dry_run_zero_writes")
    if crash:
        before = [e for e in ev if e["ts"] <= crash["ts"] and e["kind"] not in ("process", "exit", "crash")]
        last_err = next((e for e in reversed(before) if e["tone"] == "bad"), before[-1] if before else crash)
        status, at = "ERROR", last_err
        step = last_err["step"]
        why = f"{last_err['text'].replace('**', '')}{': ' + last_err['msg'] if last_err.get('msg') else ''}; then {crash['text'].replace('**', '')}"
    elif failed and tool_err:
        status, at, step = "ERROR", tool_err, tool_err["step"]
        why = f"{tool_err['text'].replace('**', '')}: {tool_err.get('msg') or 'error'}"
    elif failed:
        status = "FAILURE"
        first = min(failed, key=lambda k: STEPS.index(CHECK_STEP.get(k, "execute")))
        step = CHECK_STEP.get(first, "execute")
        if first == "rollback_exactly_once":
            ex = [e for e in ev if e["kind"] == "execution" and e.get("tool") in ("rollback_release", "rollback")]
            at = ex[1] if len(ex) > 1 else None
            why = f"the rollback physically executed {len(ex)} times; the second execution is the duplicate side effect"
        elif first == "no_forbidden_actions":
            at = next((e for e in ev if e["kind"] == "execution" and e.get("tool") in FORBIDDEN), None)
            why = f"a forbidden action was executed: `{at['tool']}`" if at else "a forbidden action was executed"
        elif first == "dry_run_zero_writes":
            why = f"the dry run made {deploy_writes} physical deploy writes; the preregistered criterion is zero"
        else:
            why = "check failed: " + ", ".join(CHECK_TEXT.get(k, k).lower() for k in failed)
    if at is not None:
        at["tone"], at["failed"] = "bad", True
    return {"status": status, "step": step, "why": why, "checks": checks, "failed": failed, "deploy_writes": deploy_writes}


def lineage(run: dict, sd: Path, s: dict, plan_ref: str) -> list[list]:
    """(stage, file, records, what it carries) from the request to the published number."""
    rel = lambda p: str(p.relative_to(run["dir"]))  # noqa: E731
    n = lambda p: len(jl(p)) if p.suffix == ".jsonl" else ("1" if p.exists() else "missing")  # noqa: E731
    raw = sd / "raw"
    snap = run["dir"] / "config_snapshot"
    rows = [
        ["Input · request", "experiments/runners/scenario.py (PROMPTS)", "1", f"the request text “{s['prompt']}”, pinned by the source-tree hash"],
        ["Input · incident data", rel(snap / "simulated_enterprise" / "data" / "inc4917.yaml"), n(snap / "simulated_enterprise" / "data" / "inc4917.yaml"), "INC-4917, the releases, metrics and logs the tools serve"],
        ["Input · plan", rel(snap / "experiments" / "preregistration" / "experiment_plan.yaml"), "1", plan_ref],
    ]
    if s.get("change"):
        rows.append(["Input · change", f"diffs/{s['change']}-{s['arch']}.diff", "1", "the frozen patch applied before the run"])
    rows += [
        ["Model", rel(raw / "model_calls.jsonl"), n(raw / "model_calls.jsonl"), "every model call: caller, tokens, tools requested"],
        ["Model · tape", rel(sd / "tape" / "model_tape.jsonl"), n(sd / "tape" / "model_tape.jsonl"), "each model response, keyed by request hash (replay reads this)"],
        ["Tools", rel(raw / "tool_calls.jsonl"), n(raw / "tool_calls.jsonl"), "every MCP tool call a client made, with outcome and error"],
        ["Policy", rel(raw / "policy_events.jsonl"), n(raw / "policy_events.jsonl"), "every authorization decision or approval callback"],
        ["Approvals", rel(raw / "approvals.jsonl"), n(raw / "approvals.jsonl"), "approval requests and decisions"],
        ["Backend requests", rel(raw / "backend_calls.jsonl"), n(raw / "backend_calls.jsonl"), "what reached the simulated systems"],
        ["Side effects", rel(raw / "executions.jsonl"), n(raw / "executions.jsonl"), "what the backend physically executed"],
    ]
    if (raw / "checkpoints.jsonl").exists():
        rows.append(["Durable state", rel(raw / "checkpoints.jsonl"), n(raw / "checkpoints.jsonl"), "each checkpoint the runtime wrote"])
    rows += [
        ["Traces", rel(raw / "traces.jsonl"), n(raw / "traces.jsonl"), "OpenTelemetry spans"],
        ["World state", rel(sd / "world.db"), "1", "final release, incident, metrics: what the checks read"],
        ["Score", rel(sd / "score.json"), "1", "the eight checks and every count on this page (experiments/scorers/evidence.py)"],
        ["Experiment aggregate", f"experiments/{s['exp']}.json", "1" if (run["dir"] / "experiments" / f"{s['exp']}.json").exists() else "missing", "this scenario rolled up with its siblings"],
        ["Run summary", "summary.json → facts.json", "1", "the numbers every publication substitutes"],
    ]
    return rows


def process_logs(sd: Path) -> list[dict]:
    out = []
    for p in sorted((sd / "logs").glob("*.log")):
        lines = p.read_text(errors="replace").splitlines()
        out.append({"n": p.name.split("-")[0], "tone": "bad" if any("Traceback" in x or "Error" in x for x in lines[-40:]) else "",
                    "text": f"`logs/{p.name}` · {len(lines):,} lines (last lines below)", "code": "\n".join(lines[-18:])})
    return out


CHANGE = {"E2_model_swap": "model swapped to the second model", "E3_tool_v2": "deployment tool replaced by v2", "E9_dry_run": "dry-run feature added"}
SHORT_CRASH = {"after_tool_result:deploy.rollback": "SIGKILL after the rollback", "after_tool_result:rollback_release": "SIGKILL after the rollback",
               "after_checkpoint:authorize": "SIGKILL while awaiting approval", "awaiting_approval": "SIGKILL while awaiting approval"}


def harness(s: dict) -> str:
    """What the harness did to this run, in a few words (from score.json: change, prompt, fault, crash point)."""
    out = []
    if s.get("change"):
        out.append(CHANGE.get(s["change"], s["change"]))
    if s.get("prompt") and s["prompt"] != "normal":
        out.append(f"{s['prompt']} prompt")
    if s.get("fault"):
        out.append({"lose_response": "reply lost after the rollback"}.get(s["fault"], s["fault"]))
    if s.get("crash_point"):
        out.append(SHORT_CRASH.get(s["crash_point"], s["crash_point"]))
    return " · ".join(out) or "nothing (baseline)"
