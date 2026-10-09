"""Evidence store: hash chain, anchors, schema allow-list, credential refusal, retention classes."""
import copy
import json

import pytest

from lineage.evidence import SCHEMA, EvidenceRefused, EvidenceStore, event_hash, load_rows, verify
from lineage.common import jl, load


def store(tmp_path):
    return EvidenceStore(tmp_path / "evidence.db", tmp_path / "witness" / "anchors.jsonl")


def add(s, t="attempt.started", **p):
    return s.append(t, execution_id="exec-1", trace_id="t" * 32, span_id="s" * 16, workflow_id="wf", principal="agent for group",
                    agent_id="incident-agent-prod", payload=p or {"attempt": 1, "request_id": "r1", "idempotency_key": "act-1", "endpoint": "POST /x"},
                    action_id="act-1", attempt_id="act-1.a1")


def test_chain_links_every_event_to_the_previous(tmp_path):
    s = store(tmp_path)
    a, b = add(s), add(s)
    assert b["prev_hash"] == a["event_hash"] and a["prev_hash"] == "0" * 64
    s.anchor("exec-1")
    assert verify(load_rows(tmp_path / "evidence.db"), jl(tmp_path / "witness" / "anchors.jsonl"))["intact"]


def test_edit_in_place_is_detected_at_the_edited_event(tmp_path):
    s = store(tmp_path)
    for _ in range(4):
        add(s)
    s.anchor("exec-1")
    rows = load_rows(tmp_path / "evidence.db")
    rows[1]["payload_json"] = rows[1]["payload_json"].replace("r1", "r9")
    v = verify(rows, jl(tmp_path / "witness" / "anchors.jsonl"))
    assert not v["chain_ok"] and v["first_problem"][0]["seq"] == 2


def test_recomputed_chain_passes_the_chain_check_but_not_the_anchor(tmp_path):
    s = store(tmp_path)
    for _ in range(4):
        add(s)
    s.anchor("exec-1")
    rows = load_rows(tmp_path / "evidence.db")
    rows[1]["payload_json"] = rows[1]["payload_json"].replace("r1", "r9")
    for i in range(1, len(rows)):
        rows[i]["prev_hash"] = rows[i - 1]["event_hash"]
        rows[i]["event_hash"] = event_hash(rows[i])
    v = verify(rows, jl(tmp_path / "witness" / "anchors.jsonl"))
    assert v["chain_ok"] and not v["anchors_ok"]


def test_truncation_after_an_anchor_is_detected(tmp_path):
    s = store(tmp_path)
    for _ in range(3):
        add(s)
    s.anchor("exec-1")
    rows = load_rows(tmp_path / "evidence.db")[:-1]
    assert not verify(rows, jl(tmp_path / "witness" / "anchors.jsonl"))["anchors_ok"]


def test_schema_refuses_fields_it_does_not_know(tmp_path):
    with pytest.raises(EvidenceRefused, match="not in the evidence schema"):
        add(store(tmp_path), "model.invoked", model="qwen3:8b", prompt="the full prompt text")


@pytest.mark.parametrize("value", ["Bearer abc.def.ghi", "dpl_live_7Fq2xW9rTt3LmZ", "4111-1111-1111-1111"])
def test_schema_refuses_credentials_and_card_numbers(tmp_path, value):
    with pytest.raises(EvidenceRefused, match="credential or card"):
        add(store(tmp_path), "attempt.finished", attempt=1, result="COMMITTED", error=value)


def test_every_event_type_has_a_retention_class():
    classes = load("retention.toml")
    assert set(SCHEMA) == set(classes["event_types"])
    assert all(classes["event_types"][t] in classes["classes"] for t in SCHEMA)


def test_no_event_type_may_carry_raw_reasoning_or_prompt_text():
    forbidden = {"prompt", "messages", "reasoning", "thinking", "chain_of_thought", "content", "completion"}
    assert not any(forbidden & fields for fields in SCHEMA.values())
