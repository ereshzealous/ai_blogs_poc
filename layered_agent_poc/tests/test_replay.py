"""Recorded model traffic: the POC replays a run without a model server."""

from __future__ import annotations

import json

import pytest

import traffic
from experiments import poc
from tests.conftest import ROOT, lap

RECORDING = ROOT / "traffic" / "recordings" / "demo-gpt-oss_20b"


def test_chat_replays_in_order_per_caller(tmp_path, capsys):
    tape = traffic.Traffic("record", tmp_path)
    tape.record_chat("triage", "m", {"q": "wf-0123456789 first"}, {"content": "t1"}, 10.04)
    tape.record_chat("diagnosis", "m", {"q": "second"}, {"content": "d1"}, 20.0)
    tape.record_chat("triage", "m", {"q": "third"}, {"content": "t2"}, 30.0)

    replay = traffic.Traffic("replay", tmp_path)
    # a different workflow id is a volatile value, not a different request
    assert replay.replay_chat("triage", "m", {"q": "wf-abcdefabcd first"}) == ({"content": "t1"}, 10.0)
    assert replay.replay_chat("triage", "m", {"q": "changed"})[0] == {"content": "t2"}
    assert replay.replay_chat("diagnosis", "m", {"q": "second"})[0] == {"content": "d1"}
    assert replay.mismatches == 1
    assert "request differs" in capsys.readouterr().err
    with pytest.raises(traffic.TrafficMissing):
        replay.replay_chat("triage", "m", {"q": "fourth"})


def test_embeddings_replay_by_input(tmp_path):
    tape = traffic.Traffic("record", tmp_path)
    tape.record_embed("embed", ["a", "b"], [[0.1234567, 1.0], [2.0, 3.0]])
    replay = traffic.Traffic("replay", tmp_path)
    assert replay.replay_embed("embed", ["a", "b"]) == [[0.123457, 1.0], [2.0, 3.0]]
    assert replay.models() == {"embed"}
    with pytest.raises(traffic.TrafficMissing):
        replay.replay_embed("embed", ["b", "a"])
    with pytest.raises(FileNotFoundError):
        traffic.Traffic("replay", tmp_path / "empty")


def test_env_selects_the_mode(monkeypatch, tmp_path):
    monkeypatch.setenv(traffic.ENV, "")
    assert traffic.from_env() is None
    monkeypatch.setenv(traffic.ENV, f"record:{tmp_path}")
    assert traffic.from_env().mode == "record"
    monkeypatch.setenv(traffic.ENV, f"rewind:{tmp_path}")
    with pytest.raises(ValueError):
        traffic.from_env()


@pytest.mark.mcp
def test_demo_workflow_replays_without_a_model_server(platform_env):
    env = {**platform_env["env"], "LAP_MODEL_TRAFFIC": f"replay:{RECORDING}",
           "LAP_KNOWLEDGE_INDEX": str(platform_env["tmp"] / "knowledge_index.json"),
           "LAP_MODEL_REASONING": "gpt-oss:20b", "LAP_MODEL_SUMMARY": "gpt-oss:20b",
           "OLLAMA_URL": "http://127.0.0.1:9"}  # nothing listens there: any live model call fails
    run = lap("run", "INC-4917", "--as", "alice", env=env, timeout=300)
    assert "WAITING_APPROVAL" in run.stdout, run.stderr
    wf = next(w for w in run.stdout.split() if w.startswith("wf-"))
    assert lap("approve", wf, "--as", "bob", env=env).returncode != 0
    assert "COMPLETED" in lap("approve", wf, "--as", "alice", env=env, timeout=300).stdout
    ev = json.loads(lap("eval", wf, env=env).stdout)
    assert ev["ok"], ev
    assert len(platform_env["world"].executions("source_control.rollback_release")) == 1


def test_run_summary_reads_the_published_run():
    ok, rows = poc.summarize("2026-09-16")
    assert ok, rows
    names = [r[1] for r in rows]
    assert names[:2] == ["Stages", "Tests"]
    assert "Platform · gpt-oss:20b" in names and "Platform · qwen3:8b" in names
    assert set(poc.PROFILES) == {"quick", "standard", "full"}
    assert poc.PROFILES["full"]["model_tests"] and not poc.PROFILES["quick"]["model_tests"]


def test_a_rerun_scenario_starts_clean(tmp_path):
    from experiments import run

    d = tmp_path / "crash"
    run.fresh_world(d)
    (d / "platform.db").write_text("an earlier attempt")
    (d / "traffic").mkdir()
    run.fresh_world(d)
    assert {p.name for p in d.iterdir()} <= {"enterprise.db", "enterprise.db-wal", "enterprise.db-shm"}
    old = next((tmp_path / "_superseded").iterdir())
    assert (old / "platform.db").exists() and (old / "traffic").is_dir()


def test_reports_say_how_a_run_was_made(tmp_path):
    from experiments import report

    page = report.build(poc.REFERENCE_RUN, report_dir=tmp_path).read_text()
    assert "live, model traffic recorded · profile full" in page and "Replayed run." not in page
    base = ROOT / "runs" / poc.REFERENCE_RUN
    d = report.collect(base)
    d["meta"] |= {"mode": "replay", "replay_from": poc.REFERENCE_RUN, "recorded": False,
                  "reruns": [{"what": "crash", "resume": False, "at": "2026-09-17T14:00:00Z", "mode": "replay"}]}
    page = report.build_html(base, d)
    assert f"Model answers and token counts come from the recording in runs/{poc.REFERENCE_RUN}" in page
    assert "<dt>Re-run</dt><dd>crash, replay, 2026-09-17T14:00:00Z</dd>" in page
