"""The benchmark runner's v5 path: decide after the first pick, ask one question, resolve and select again."""

from __future__ import annotations

import argparse
import json

import pytest

from agent.llm import LLMResponse, ToolCall
from agent.selection import select_tool
from benchmark import runner
from benchmark.evaluator import metrics
from benchmark.evaluator.metrics import Case
from control_plane.discovery.pipeline import DiscoveryService
from control_plane.discovery.rewrite import QueryRewriter
from control_plane.paths import CATALOG_DIR
from control_plane.policy.engine import Identity
from control_plane.registry.registry import CapabilityRegistry

NOTE = "Wrapping up: drop a final 'mitigated, monitoring' note in #inc-4917-checkout-latency."
REWRITE = json.dumps({"first_step": "add a note to the incident", "operation": "write", "system": "incident management"})
ONCALL = Identity("oncall-1", ("sre-oncall",))


class Model:
    """Rewrites NOTE, and picks a tool: the incident comment when shown, else the first tool."""

    def __init__(self):
        self.selections = []

    def chat(self, messages, tools=None, options=None):
        if tools is None:
            return LLMResponse(REWRITE, [], 600, 50, 1.0)
        names = [t["function"]["name"] for t in tools]
        name = "itsm__add_incident_comment" if "itsm__add_incident_comment" in names else names[0]
        self.selections.append((messages[-1]["content"], names, name))
        return LLMResponse("", [ToolCall(name, {"incident_id": "INC-4917", "comment": "x", "channel": "#x", "text": "x"})],
                           700, 20, 1.0)


class Published:
    def __init__(self, tool_id, spec):
        self.tool_id, self.spec = tool_id, spec

    def definition(self):
        server, name = self.tool_id.split(".", 1)
        return {"type": "function", "function": {"name": f"{server}__{name}", "description": self.spec[2], "parameters": self.spec[3]}}


@pytest.fixture(scope="module")
def setup():
    manifest = json.loads((CATALOG_DIR / "catalog_500.json").read_text())
    tools = {f"{t['server']}.{t['name']}": (t["server"], t["name"], t["description"], t["input_schema"]) for t in manifest["tools"]}
    model = Model()
    svc = DiscoveryService(tools, CapabilityRegistry.load(), embedder=None, profile="v5", rewriter=QueryRewriter(model))
    return svc, {t: Published(t, spec) for t, spec in tools.items()}, model


def case(intent):
    return Case("H999", "cross_domain", NOTE, "collaboration.post_message", (), {}, "ALLOW", "oncall-1", ("sre-oncall",),
                kind="ambiguous", intent=intent)


def first_pick(svc, by_id, model, c):
    first = svc.resolve(c.prompt)
    sel = select_tool(model, runner.v5_definitions(first.tool_ids, by_id, svc.catalog), c.prompt, ONCALL)
    return first, sel


ARGS = argparse.Namespace(ask="intent", k=5)


def test_definitions_carry_the_capability_guidance(setup):
    svc, by_id, _ = setup
    [d] = runner.v5_definitions(["collaboration.post_message"], by_id, svc.catalog)
    assert "Use for: telling people something in a chat channel" in d["function"]["description"]


class FirstToolModel(Model):
    """Reads the request as a chat post, and picks the first tool shown."""

    def chat(self, messages, tools=None, options=None):
        if tools is None:
            chat = json.dumps({"first_step": "post a message in the incident channel", "operation": "write", "system": "chat"})
            return LLMResponse(chat, [], 600, 50, 1.0)
        return LLMResponse("", [ToolCall(tools[0]["function"]["name"], {})], 700, 20, 1.0)


def test_a_confident_pick_is_not_questioned(setup, monkeypatch):
    _, by_id, _ = setup
    monkeypatch.setattr(runner, "V5_THRESHOLDS", {"READ_ONLY": 0.0, "LOW_RISK_WRITE": 0.0, "HIGH_RISK_WRITE": 0.0})
    manifest = json.loads((CATALOG_DIR / "catalog_500.json").read_text())
    tools = {f"{t['server']}.{t['name']}": (t["server"], t["name"], t["description"], t["input_schema"]) for t in manifest["tools"]}
    model = FirstToolModel()
    svc = DiscoveryService(tools, CapabilityRegistry.load(), embedder=None, profile="v5", rewriter=QueryRewriter(model))
    c = case({"system": "chat"})
    first, sel = first_pick(svc, by_id, model, c)
    assert sel.tool_id == "collaboration.post_message"
    final, info = runner.resolve_with_one_question(ARGS, svc, by_id, model, c, ONCALL, first, sel)
    assert info["v5_decision"]["agreement"] and info["v5_decision"]["auto"]
    assert final is sel and not info["asked"] and info["selection_calls"] == 1


def test_an_uncertain_pick_asks_once_and_selects_again(setup, monkeypatch):
    svc, by_id, model = setup
    monkeypatch.setattr(runner, "V5_THRESHOLDS", {"READ_ONLY": None, "LOW_RISK_WRITE": None, "HIGH_RISK_WRITE": None})
    c = case({"system": "chat", "resource": "chat message", "action": "post"})
    first, sel = first_pick(svc, by_id, model, c)
    assert sel.tool_id == "itsm.add_incident_comment"
    final, info = runner.resolve_with_one_question(ARGS, svc, by_id, model, c, ONCALL, first, sel)
    assert info["asked"] and info["question"]["dimension"] == "system"
    assert info["answer"] == {"kind": "option", "value": "chat", "text": "The team chat."}
    assert final.tool_id == "collaboration.post_message" and final.calls == 2
    assert final.prompt_tokens == 1400 and info["selection_calls"] == 2
    request, names, _ = model.selections[-1]
    assert "The user answered: The team chat." in request and "itsm__add_incident_comment" not in names
    assert info["v5_final_candidates"] == info["v5_second"]["tool_ids"]


def test_an_unsure_user_with_only_writes_on_offer_gets_no_call(setup, monkeypatch):
    svc, by_id, model = setup
    monkeypatch.setattr(runner, "V5_THRESHOLDS", {"READ_ONLY": None, "LOW_RISK_WRITE": None, "HIGH_RISK_WRITE": None})
    c = case({})
    first, sel = first_pick(svc, by_id, model, c)
    final, info = runner.resolve_with_one_question(ARGS, svc, by_id, model, c, ONCALL, first, sel)
    assert info["asked"] and info["abstained"] and final.tool_id is None and final.exposed_name is None


def test_asking_can_be_switched_off(setup, monkeypatch):
    svc, by_id, model = setup
    monkeypatch.setattr(runner, "V5_THRESHOLDS", {"READ_ONLY": None, "LOW_RISK_WRITE": None, "HIGH_RISK_WRITE": None})
    c = case({"system": "chat"})
    first, sel = first_pick(svc, by_id, model, c)
    final, info = runner.resolve_with_one_question(argparse.Namespace(ask="off", k=5), svc, by_id, model, c, ONCALL, first, sel)
    assert final is sel and not info["asked"] and info["v5_decision"]["auto"] is False


def test_the_policy_version_follows_the_case_set(tmp_path, monkeypatch):
    third = tmp_path / "holdout3_cases.yaml"
    third.write_text("defaults:\n  identity: { user_id: oncall-1, roles: [sre-oncall] }\n  split: holdout3\n"
                     "  policy_version: v2\ncases: []\n")
    monkeypatch.setattr(metrics, "HOLDOUT3_FILE", third)
    ns = argparse.Namespace
    assert runner.policy_version(ns(case_set="main", policy="auto")) == "v1"
    assert runner.policy_version(ns(case_set="holdout3", policy="auto")) == "v2"
    assert runner.policy_version(ns(case_set="holdout3", policy="v1")) == "v1"
    assert runner.policy_version(ns(case_set="holdout3", policy="auto", command="agent")) == "v1"
    config = runner._base_config(ns(case_set="holdout3", policy="auto", k=5), ["catalog_50"])
    assert config["policy_version"] == "v2" and len(config["policy_sha256"]) == 64


def test_v5_with_questions_needs_calibrated_thresholds(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(runner, "V5_THRESHOLDS", {"READ_ONLY": None, "LOW_RISK_WRITE": None, "HIGH_RISK_WRITE": None})
    args = argparse.Namespace(run_id="x", discovery="v5", ask="intent", policy="auto", case_set="main", catalogs="catalog_50",
                              modes="control_plane")
    with pytest.raises(ValueError, match="calibrat"):
        import anyio
        anyio.run(runner.run_selection, args)
