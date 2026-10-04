"""Run plans: what a `poc run` tests, how, and what counts as a pass.

A plan is a YAML file (see plans/). Every key is optional: a plan is laid over DEFAULTS, which is the full plan.

    uv run poc plans                          # the plans in plans/
    uv run poc plan show plans/chaos.yaml     # what a plan runs, injects and expects
    uv run poc run --plan chaos               # run it; --models, --runs, --only, --skip and --set override it

The resolved plan is saved as runs/<run-id>/plan.yaml, and the run passes only if every expectation holds.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "plans"
STEPS = ["intake", "investigate", "propose_remediation", "await_approval", "remediate", "verify", "record", "complete"]
FAULT_MODES = ("timeout", "lose_response")
ARM_AT = ("start", "approval")

# experiment -> (article ids, what it shows)
EXPERIMENTS: dict[str, tuple[str, str]] = {
    "tests": ("", "pytest and the 7 import contracts"),
    "faults": ("E5 · E6", "one platform run with injected tool faults: bounded retry in the gateway, deduplication by idempotency key"),
    "crash": ("E4", "SIGKILLs at chosen points of one workflow; new processes approve or resume it from its checkpoints"),
    "monolith": ("baseline", "the same incident through the agent monolith, then its lost response and a SIGKILL while it waits"),
    "workflow": ("E2 · E3 · E7 · E8 · E9", "INC-4917 end to end per model, with evals, traces, memory and context records"),
    "change": ("E1", "each requirement-change patch applied to both implementations: files, lines, concerns, contracts"),
    "export": ("", "the data behind the article's measured figures"),
}

DEFAULTS: dict[str, Any] = {
    "name": "custom",
    "description": "",
    "minutes": None,
    "models": ["gpt-oss:20b", "qwen3:8b"],
    "runs": 3,
    "model_answers": {"mode": "live", "replay_from": None, "record": True},
    "experiments": list(EXPERIMENTS),
    "tests": {"model_tests": True},
    "faults": {
        "model": "gpt-oss:20b",
        "arm_at": "approval",
        "inject": [
            {"tool": "observability.query_latency", "mode": "timeout", "times": 2, "delay_s": 3.0},
            {"tool": "source_control.rollback_release", "mode": "lose_response", "times": 1, "delay_s": 4.0},
        ],
    },
    "crash": {"model": "gpt-oss:20b", "kill_at": ["after_step:await_approval", "executed:source_control.rollback_release"], "inject": []},
    "monolith": {"lost_response": True, "crash": True},
    "expect": {
        "tests_pass": True,
        "contracts_kept": True,
        "platform_runs_complete": "all",
        "platform_all_checks": "all",
        "lost_response_backend_executions": 1,
        "monolith_lost_response_rollbacks_at_least": 2,
        "crash_final_status": "COMPLETED",
        "crash_backend_rollbacks": 1,
        "change_contracts_kept": True,
    },
}

# expectation -> the experiment that measures it
EXPECT_NEEDS = {"tests_pass": "tests", "contracts_kept": "tests", "platform_runs_complete": "workflow", "platform_all_checks": "workflow",
                "lost_response_backend_executions": "faults", "monolith_lost_response_rollbacks_at_least": "monolith",
                "crash_final_status": "crash", "crash_backend_rollbacks": "crash", "change_contracts_kept": "change"}

EXPECTATIONS = {
    "tests_pass": "every test passes",
    "contracts_kept": "the 7 layer contracts hold",
    "platform_runs_complete": "platform runs complete",
    "platform_all_checks": "platform runs pass all 8 eval checks",
    "lost_response_backend_executions": "after a lost response the backend executes the write this many times",
    "monolith_lost_response_rollbacks_at_least": "the monolith repeats the lost write at least this many times",
    "crash_final_status": "the crashed workflow ends in this status",
    "crash_backend_rollbacks": "the crashed workflow rolls back this many times",
    "change_contracts_kept": "every layered patch applies and keeps the contracts",
}


class PlanError(ValueError):
    pass


# ------------------------------------------------------------------ loading
def resolve_path(name_or_path: str) -> Path:
    p = Path(name_or_path)
    for cand in (p, ROOT / p, PLANS / p, PLANS / f"{name_or_path}.yaml"):
        if cand.is_file():
            return cand
    raise PlanError(f"no plan {name_or_path!r}: pass a file, or one of: {', '.join(available())}")


def available() -> list[str]:
    return sorted(p.stem for p in PLANS.glob("*.yaml"))


def merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def load(name_or_path: str | None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if name_or_path:
        path = resolve_path(name_or_path)
        raw = yaml.safe_load(path.read_text()) or {}
        if not isinstance(raw, dict):
            raise PlanError(f"{path}: a plan is a YAML mapping")
        unknown = set(raw) - set(DEFAULTS)
        if unknown:
            raise PlanError(f"{path.name}: unknown key(s) {sorted(unknown)}; known: {sorted(DEFAULTS)}")
        raw.setdefault("name", path.stem)
    plan = merge(DEFAULTS, raw)
    plan = merge(plan, overrides or {})
    for key in ("models", "experiments"):  # "a,b" is shorthand for [a, b]
        if isinstance(plan[key], str):
            plan[key] = [x.strip() for x in plan[key].split(",") if x.strip()]
    for section in ("faults", "crash"):
        if isinstance(plan[section].get("kill_at"), str):
            plan[section]["kill_at"] = [plan[section]["kill_at"]]
    errors = validate(plan)
    if errors:
        raise PlanError("invalid plan:\n  - " + "\n  - ".join(errors))
    return plan


def set_value(plan_overrides: dict[str, Any], assignment: str) -> None:
    """`--set crash.kill_at=[after_step:investigate]` → nested override; the value is parsed as YAML."""
    key, sep, value = assignment.partition("=")
    if not sep or not key:
        raise PlanError(f"--set needs key=value, got {assignment!r}")
    node = plan_overrides
    parts = key.strip().split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = yaml.safe_load(value)


def tools() -> dict[str, dict[str, Any]]:
    return yaml.safe_load((ROOT / "config" / "capabilities.yaml").read_text())["tools"]


def validate(plan: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    known = tools()
    models = plan["models"]
    if not isinstance(models, list) or not models or not all(isinstance(m, str) and m for m in models):
        errs.append("models: a non-empty list of Ollama model names")
    if not isinstance(plan["runs"], int) or not 1 <= plan["runs"] <= 20:
        errs.append("runs: a whole number from 1 to 20")
    ma = plan["model_answers"]
    if ma.get("mode") not in ("live", "replay"):
        errs.append("model_answers.mode: live or replay")
    if ma.get("mode") == "replay" and not ma.get("replay_from"):
        errs.append("model_answers.replay_from: the run id to replay (mode is replay)")
    if ma.get("mode") == "replay" and ma.get("replay_from") and not (ROOT / "runs" / str(ma["replay_from"])).is_dir():
        errs.append(f"model_answers.replay_from: runs/{ma['replay_from']} does not exist")
    exps = plan["experiments"]
    if not isinstance(exps, list) or not exps:
        errs.append(f"experiments: a non-empty list from {list(EXPERIMENTS)}")
    else:
        bad = [e for e in exps if e not in EXPERIMENTS]
        if bad:
            errs.append(f"experiments: unknown {bad}; choose from {list(EXPERIMENTS)}")
        if len(set(exps)) != len(exps):
            errs.append("experiments: each experiment once")
    for section in ("faults", "crash"):
        sec = plan[section]
        if not isinstance(sec.get("model"), str) or not sec.get("model"):
            errs.append(f"{section}.model: an Ollama model name")
        seen = set()
        for i, f in enumerate(sec.get("inject") or []):
            where = f"{section}.inject[{i}]"
            if not isinstance(f, dict):
                errs.append(f"{where}: a mapping with tool, mode, times, delay_s")
                continue
            if f.get("tool") not in known:
                errs.append(f"{where}.tool: unknown tool {f.get('tool')!r}")
            if f.get("mode") not in FAULT_MODES:
                errs.append(f"{where}.mode: one of {list(FAULT_MODES)}")
            if f.get("mode") == "lose_response" and known.get(f.get("tool"), {}).get("risk") == "READ_ONLY":
                errs.append(f"{where}: lose_response only applies to writes; {f.get('tool')} is read-only")
            if not isinstance(f.get("times", 1), int) or f.get("times", 1) < 1:
                errs.append(f"{where}.times: a whole number, at least 1")
            if not isinstance(f.get("delay_s", 4.0), (int, float)) or f.get("delay_s", 4.0) <= 0:
                errs.append(f"{where}.delay_s: seconds, above 0")
            if f.get("tool") in seen:
                errs.append(f"{where}: one fault per tool ({f.get('tool')} appears twice)")
            seen.add(f.get("tool"))
    if plan["faults"].get("arm_at") not in ARM_AT:
        errs.append(f"faults.arm_at: one of {list(ARM_AT)}")
    points = plan["crash"].get("kill_at")
    if not isinstance(points, list):
        errs.append("crash.kill_at: a list of kill points")
    else:
        injected = {f.get("tool") for f in plan["crash"].get("inject") or [] if isinstance(f, dict) and f.get("mode") == "timeout"}
        for i, pt in enumerate(points):
            m = re.fullmatch(r"(after_step|executed|timeout):(.+)", str(pt))
            if not m:
                errs.append(f"crash.kill_at[{i}]: after_step:<step>, executed:<tool> or timeout:<tool>, got {pt!r}")
            elif m.group(1) == "after_step" and m.group(2) not in STEPS:
                errs.append(f"crash.kill_at[{i}]: unknown step {m.group(2)!r}; steps: {STEPS}")
            elif m.group(1) != "after_step" and m.group(2) not in known:
                errs.append(f"crash.kill_at[{i}]: unknown tool {m.group(2)!r}")
            elif m.group(1) == "timeout" and m.group(2) not in injected:
                errs.append(f"crash.kill_at[{i}]: {pt} never fires unless crash.inject makes {m.group(2)} time out")
    bad_expect = set(plan["expect"]) - set(EXPECTATIONS)
    if bad_expect:
        errs.append(f"expect: unknown {sorted(bad_expect)}; known: {sorted(EXPECTATIONS)}")
    for k in ("platform_runs_complete", "platform_all_checks"):
        v = plan["expect"].get(k)
        if v is not None and v != "all" and not (isinstance(v, int) and v >= 0):
            errs.append(f"expect.{k}: all, a number of runs, or null")
    return errs


def dump(plan: dict[str, Any]) -> str:
    return "# Resolved plan for this run (written by poc run).\n" + yaml.safe_dump(plan, sort_keys=False, allow_unicode=True)


# ------------------------------------------------------------------ explaining
def fault_text(inject: list[dict[str, Any]]) -> str:
    parts = []
    for f in inject:
        what = "times out" if f["mode"] == "timeout" else "commits, then loses its response"
        parts.append(f'{f["tool"]} {what} ×{f.get("times", 1)}')
    return "; ".join(parts) or "no faults"


def describe(plan: dict[str, Any], source: str = "") -> list[str]:
    ma, lines = plan["model_answers"], []
    lines.append(f"Plan {plan['name']}" + (f" · {source}" if source else ""))
    if plan.get("description"):
        lines.append(plan["description"])
    if plan.get("minutes"):
        lines.append(f"About {plan['minutes']} min on an idle 24 GB laptop.")
    lines.append("")
    lines.append(f"  models         {', '.join(plan['models'])} · {plan['runs']} run(s) per scenario")
    if ma["mode"] == "replay":
        lines.append(f"  model answers  replayed from runs/{ma['replay_from']}: no Ollama needed; timings are not model timings")
    else:
        lines.append(f"  model answers  live from Ollama{', recorded for later replay' if ma.get('record', True) else ''}")
    lines.append("")
    lines.append("What runs")
    pad = " " * 17
    for i, e in enumerate(plan["experiments"], 1):
        ids, what = EXPERIMENTS[e]
        details: list[str] = []
        if e == "tests":
            on = plan["tests"]["model_tests"] and ma["mode"] == "live"
            details.append(f"end-to-end model tests: {'on' if on else 'off'}")
        elif e == "faults":
            f = plan["faults"]
            details.append(f"{f['model']}, faults armed at {'the start' if f['arm_at'] == 'start' else 'the approval gate'}:")
            details += [f"  {x}" for x in fault_text(f.get("inject") or []).split("; ")]
        elif e == "crash":
            c = plan["crash"]
            details.append(f"{c['model']}, SIGKILL in turn at:")
            details += [f"  {k}" for k in c["kill_at"]] or ["  (no kill points)"]
            if c.get("inject"):
                details.append("faults: " + fault_text(c["inject"]))
        elif e == "monolith":
            m = plan["monolith"]
            extra = [x for x, on in (("the lost response", m.get("lost_response")), ("a SIGKILL while it waits", m.get("crash"))) if on]
            details.append(f"{plan['runs']} run(s)" + (f", then {' and '.join(extra)}" if extra else ""))
        elif e == "workflow":
            details.append(f"{plan['runs']} run(s) × {len(plan['models'])} model(s)")
        lines.append(f"  {i}. {e:<10}  " + (f"{ids} · " if ids else "") + what)
        lines += [pad + d for d in details]
    lines.append("")
    lines.append("Passes when")
    for k, v in plan["expect"].items():
        if v is None or v is False or EXPECT_NEEDS[k] not in plan["experiments"]:
            continue
        lines.append(f"  - {EXPECTATIONS[k]}" + ("" if v is True else f": {v}"))
    return lines


# ------------------------------------------------------------------ judging a run
def evaluate(base: Path, plan: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(status, check, measured) for each expectation; status is ok, fail or skip (the experiment did not run)."""
    load_json = lambda p: json.loads((base / p).read_text()) if (base / p).exists() else None  # noqa: E731
    exp, ran = plan["expect"], set(plan["experiments"])
    tests, wf = load_json("tests.json"), load_json("workflow/summary.json")
    faults, crash, mono, cs = load_json("faults/summary.json"), load_json("crash/summary.json"), load_json("monolith/summary.json"), load_json("change-scope.json")
    rows: list[tuple[str, str, str]] = []

    def add(key: str, label: str, needed: str, data: Any, check, measured) -> None:
        if exp.get(key) is None or exp.get(key) is False or needed not in ran:
            return
        if data is None:
            rows.append(("fail", label, f"no {needed} results recorded"))
        else:
            rows.append(("ok" if check(data, exp[key]) else "fail", label, measured(data)))

    add("tests_pass", "Tests", "tests", tests, lambda t, _: t.get("failed", 0) == 0,
        lambda t: f"{t['passed']} passed ({t['fast']} fast, {t['ollama']} with models), {t.get('failed', 0)} failed")
    if tests is not None and "contracts_kept" not in tests:  # runs recorded before the field existed: read the lint log
        from experiments.report import contracts_of

        lint = contracts_of(base)
        tests = {**tests, "contracts_kept": all(ok for _, ok in lint)} if lint else tests
    add("contracts_kept", "Layer contracts", "tests", tests if tests is None or "contracts_kept" in tests else None,
        lambda t, _: t.get("contracts_kept"), lambda t: "all kept" if t.get("contracts_kept") else "broken")

    def per_model(stat: str):
        def check(w, want):
            return all(s[stat] == s["runs"] if want == "all" else s[stat] >= want for s in w.values())
        return check

    add("platform_runs_complete", "Platform runs complete", "workflow", wf, per_model("completed"),
        lambda w: " · ".join(f"{m} {s['completed']}/{s['runs']}" for m, s in w.items()))
    add("platform_all_checks", "All 8 eval checks", "workflow", wf, per_model("eval_all_pass"),
        lambda w: " · ".join(f"{m} {s['eval_all_pass']}/{s['runs']}" for m, s in w.items()))
    add("lost_response_backend_executions", "Write executed once", "faults", faults,
        lambda f, want: f["rollback"]["backend_executions"] == want,
        lambda f: f"backend executions {f['rollback']['backend_executions']}, replays {f['rollback']['backend_replays']}")
    add("monolith_lost_response_rollbacks_at_least", "Monolith repeats the write", "monolith", mono,
        lambda m, want: bool(m.get("lost_response")) and m["lost_response"]["world"]["rollback_executions"] >= want,
        lambda m: f"{m['lost_response']['world']['rollback_executions']} rollbacks after a lost response" if m.get("lost_response") else "lost response not run")
    add("crash_final_status", "Workflow survives SIGKILLs", "crash", crash, lambda c, want: final_status(c) == want,
        lambda c: f"{c['processes']} processes, {kills(c)} SIGKILL(s), final {final_status(c)}")
    add("crash_backend_rollbacks", "Rollbacks after the crashes", "crash", crash, lambda c, want: c["backend_rollbacks"] == want,
        lambda c: f"{c['backend_rollbacks']} rollback(s)")
    add("change_contracts_kept", "Requirement changes", "change", cs,
        lambda c, _: all(x["layered"].get("applies") and x["layered"].get("contracts_kept", True) and x["monolith"].get("applies") for x in c["changes"]),
        lambda c: " · ".join(f"{x['id']} {x['monolith']['files']}→{x['layered']['files']} files" for x in c["changes"]))
    return rows


def kills(crash: dict[str, Any]) -> int:
    seq = crash.get("sequence")
    return sum(1 for p in seq if p.get("crash_on") and p.get("returncode") == -9) if seq else 2  # older runs: two fixed kills


def final_status(crash: dict[str, Any]) -> str:
    seq = crash.get("sequence")
    return seq[-1]["status_after"] if seq else crash["resume"]["status"]


def for_run(base: Path, profile: str | None = None) -> dict[str, Any]:
    """The plan a run used: its saved plan.yaml, else the built-in plan named by its profile, else the full plan."""
    saved = base / "plan.yaml"
    if saved.exists():
        return merge(DEFAULTS, yaml.safe_load(saved.read_text()) or {})
    if profile and (PLANS / f"{profile}.yaml").exists():
        return load(profile)
    return copy.deepcopy(DEFAULTS)
