"""Run plans: loading, validation, overrides, judging a run, and a crash sequence taken from a plan."""

from __future__ import annotations

import pytest

from experiments import plan as plans
from tests.conftest import ROOT

REFERENCE = ROOT / "runs" / "2026-09-17-recorded"


def test_every_shipped_plan_loads_and_explains_itself():
    assert {"quick", "standard", "full", "replay", "chaos"} <= set(plans.available())
    for name in plans.available():
        p = plans.load(name)
        text = "\n".join(plans.describe(p, name))
        assert p["name"] == name and "What runs" in text and "Passes when" in text
    assert plans.load("quick")["models"] == ["gpt-oss:20b"] and not plans.load("quick")["tests"]["model_tests"]
    assert plans.load("replay")["model_answers"] == {"mode": "replay", "replay_from": "2026-09-17-recorded", "record": True}


@pytest.mark.parametrize("override, message", [
    ({"experiments": ["tests", "benchmarks"]}, "experiments: unknown ['benchmarks']"),
    ({"crash": {"kill_at": ["after_step:nowhere"]}}, "unknown step 'nowhere'"),
    ({"crash": {"kill_at": ["timeout:itsm.get_incident"]}}, "never fires unless crash.inject"),
    ({"faults": {"inject": [{"tool": "itsm.get_incident", "mode": "lose_response"}]}}, "only applies to writes"),
    ({"faults": {"inject": [{"tool": "itsm.nope", "mode": "timeout"}]}}, "unknown tool 'itsm.nope'"),
    ({"model_answers": {"mode": "replay", "replay_from": None}}, "the run id to replay"),
    ({"runs": 0}, "runs: a whole number"),
    ({"expect": {"crash_final_status": "COMPLETED", "speed": 1}}, "expect: unknown ['speed']"),
])
def test_invalid_plans_are_rejected_with_a_reason(override, message):
    with pytest.raises(plans.PlanError, match=message.replace("[", r"\[").replace("]", r"\]").replace("(", r"\(")):
        plans.load("full", override)


def test_unknown_top_level_keys_are_rejected(tmp_path):
    f = tmp_path / "typo.yaml"
    f.write_text("modles: [gpt-oss:20b]\n")
    with pytest.raises(plans.PlanError, match="unknown key"):
        plans.load(str(f))


def test_set_overrides_nested_keys_with_yaml_values():
    over: dict = {}
    for kv in ("runs=2", "tests.model_tests=false", "crash.kill_at=[after_step:investigate, after_step:await_approval]", "models=gpt-oss:20b"):
        plans.set_value(over, kv)
    p = plans.load("full", over)
    assert p["runs"] == 2 and p["tests"]["model_tests"] is False and p["models"] == ["gpt-oss:20b"]
    assert p["crash"]["kill_at"] == ["after_step:investigate", "after_step:await_approval"]
    assert p["faults"]["inject"] == plans.DEFAULTS["faults"]["inject"]  # untouched keys keep the plan's values
    with pytest.raises(plans.PlanError):
        plans.set_value({}, "no-equals-sign")


def test_a_run_is_judged_by_its_plan():
    plan = plans.for_run(REFERENCE, "full")
    assert all(status == "ok" for status, _, _ in plans.evaluate(REFERENCE, plan))
    strict = plans.merge(plan, {"expect": {"crash_backend_rollbacks": 2, "platform_all_checks": None}})
    rows = {name: status for status, name, _ in plans.evaluate(REFERENCE, strict)}
    assert rows["Rollbacks after the crashes"] == "fail" and "All 8 eval checks" not in rows
    only = plans.merge(plan, {"experiments": ["crash"]})
    assert {name for _, name, _ in plans.evaluate(REFERENCE, only)} == {"Workflow survives SIGKILLs", "Rollbacks after the crashes"}


@pytest.mark.mcp
def test_crash_follows_the_plans_kill_points(tmp_path, monkeypatch):
    """One SIGKILL after the approval checkpoint, then a new process approves: replayed from the demo recording."""
    from experiments import run

    source = tmp_path / "recording"
    (source / "crash").mkdir(parents=True)
    (source / "crash" / "traffic").symlink_to(ROOT / "traffic" / "recordings" / "demo-gpt-oss_20b")
    base = tmp_path / "run"
    base.mkdir()
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9")  # nothing listens there
    monkeypatch.setitem(run.TRAFFIC, "mode", "replay")
    monkeypatch.setitem(run.TRAFFIC, "base", base)
    monkeypatch.setitem(run.TRAFFIC, "source", source)
    monkeypatch.setattr(run, "PLAN", plans.load("quick", {"crash": {"kill_at": ["after_step:await_approval"]}}))
    out = run.exp_crash(base)
    assert [e["command"].split()[1] for e in out["sequence"]] == ["run", "approve"]
    assert out["sequence"][0]["returncode"] == -9 and out["sequence"][0]["status_after"] == "WAITING_APPROVAL"
    assert out["resume"]["status"] == "COMPLETED" and out["backend_rollbacks"] == 1 and out["processes"] == 2
    assert plans.kills(out) == 1 and plans.final_status(out) == "COMPLETED"
