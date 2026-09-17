"""Discovery v4 (opt-in): a model-written search query and intent, duplicate collapse, and v3's router and cut.

The model is a scripted stand-in here; the held-out sets measure the real one.
"""

from __future__ import annotations

import json

import pytest

from agent.llm import LLMResponse
from control_plane.discovery.hybrid import Scored
from control_plane.discovery.pipeline import DiscoveryService
from control_plane.discovery.rewrite import QueryRewriter, Rewrite
from control_plane.paths import CATALOG_DIR
from control_plane.ranking.reranker import collapse_equivalents, rerank
from control_plane.routing.router import IntentRouter


class ScriptedModel:
    def __init__(self, replies):
        self.replies = dict(replies)
        self.calls = 0

    def chat(self, messages, tools=None, options=None):
        self.calls += 1
        assert tools is None, "the rewrite call must not send tools"
        request = messages[-1]["content"]
        return LLMResponse(self.replies.get(request, "not json"), [], 120, 30, 5.0)


def reply(first_step, operation, system, environment=None):
    body = {"first_step": first_step, "operation": operation, "system": system}
    if environment:
        body["environment"] = environment
    return f"Here you go: {json.dumps(body)}"


# ---------------------------------------------------------------------------------------------- rewriter
def test_the_rewrite_is_parsed_and_mapped_to_a_domain():
    model = ScriptedModel({"INC-4916 needs a war room.": reply("create chat channel for the incident", "write", "chat")})
    rewrite = QueryRewriter(model).rewrite("INC-4916 needs a war room.")
    assert rewrite == Rewrite("create chat channel for the incident", "write", "chat", "collaboration", 120, 30, 5.0, None)


def test_an_unusable_reply_gives_no_rewrite():
    model = ScriptedModel({"x": json.dumps({"first_step": "", "operation": "maybe", "system": "chat"})})
    assert QueryRewriter(model).rewrite("x") is None
    assert QueryRewriter(model).rewrite("never scripted") is None


def test_an_unknown_system_keeps_the_rewrite_without_a_domain():
    model = ScriptedModel({"y": reply("get invoice", "read", "business application")})
    rewrite = QueryRewriter(model).rewrite("y")
    assert rewrite.domain is None and rewrite.operation == "read"


def test_rewrites_are_cached_per_request():
    model = ScriptedModel({"z": reply("get pods", "read", "kubernetes")})
    rewriter = QueryRewriter(model)
    assert rewriter.rewrite("z") == rewriter.rewrite("z") and model.calls == 1


# ---------------------------------------------------------------------------------------------- collapse
def test_equivalent_tools_collapse_to_the_authoritative_one_at_the_best_rank(registry):
    ranked = rerank([Scored("apm.query_apm_latency", 1.0, None, None), Scored("kubernetes.get_pods", 0.9, None, None),
                     Scored("observability.query_latency", 0.8, None, None), Scored("observability.search_logs", 0.7, None, None)],
                    registry, IntentRouter().route("x"))
    collapsed = collapse_equivalents(ranked, registry)
    ids = [r.tool_id for r in collapsed]
    assert "apm.query_apm_latency" not in ids
    assert set(ids) == {"observability.query_latency", "kubernetes.get_pods", "observability.search_logs"}
    best_latency = max(r.score for r in ranked if r.tool_id in ("apm.query_apm_latency", "observability.query_latency"))
    assert next(r.score for r in collapsed if r.tool_id == "observability.query_latency") == best_latency
    assert [r.score for r in collapsed] == sorted((r.score for r in collapsed), reverse=True)


def test_different_operations_on_the_same_system_are_not_collapsed(registry):
    ranked = rerank([Scored("kubernetes.get_pod_logs", 1.0, None, None), Scored("observability.search_logs", 0.9, None, None),
                     Scored("kubernetes.get_pods", 0.8, None, None)], registry, IntentRouter().route("x"))
    assert len(collapse_equivalents(ranked, registry)) == 3


# ---------------------------------------------------------------------------------------------- pipeline
@pytest.fixture(scope="module")
def tools():
    manifest = json.loads((CATALOG_DIR / "catalog_500.json").read_text())
    return {f"{t['server']}.{t['name']}": (t["server"], t["name"], t["description"], t["input_schema"]) for t in manifest["tools"]}


def service(tools, registry, replies):
    return DiscoveryService(tools, registry, embedder=None, profile="v4", rewriter=QueryRewriter(ScriptedModel(replies)))


def test_v4_routes_by_the_models_intent(tools, registry):
    request = "INC-4916 needs a war room. Can you set one up?"
    v4 = service(tools, registry, {request: reply("create incident chat channel", "write", "chat")})
    result = v4.control_plane(request, k=5)
    assert result.route.operation == "write" and result.route.operation_source == "model"
    assert result.route.domains[0] == "collaboration"
    assert "collaboration.create_incident_channel" in result.tool_ids
    assert result.rewrite["first_step"] == "create incident chat channel" and result.rewrite["prompt_tokens"] == 120


def test_v4_filters_writes_when_the_model_says_read(tools, registry):
    request = "is i-0c41e7a9d2b3f5812 even up?"
    v4 = service(tools, registry, {request: reply("get cloud instance status", "read", "cloud")})
    result = v4.control_plane(request, k=5)
    assert "cloud.get_instance" in result.tool_ids
    reads = result.tool_ids[: len(result.tool_ids) - result.stages["write_slots"]]
    assert result.stages["after_filters"] < result.stages["published"]
    assert all(not registry.get(t).side_effect for t in reads)


def test_v4_keeps_writes_when_the_request_itself_has_a_write_signal(tools, registry):
    request = "Restart the checkout-api deployment in production."
    v4 = service(tools, registry, {request: reply("check deployment status", "read", "kubernetes")})
    result = v4.control_plane(request, k=5)
    assert result.stages["after_filters"] > 300  # both the model and the router must agree before writes are removed


def test_v4_never_shows_two_equivalent_tools(tools, registry):
    request = "checkout p95 latency in prod"
    v4 = service(tools, registry, {request: reply("query service p95 latency", "read", "monitoring")})
    ids = v4.control_plane(request, k=5).tool_ids
    assert not ({"observability.query_latency", "apm.query_apm_latency"} <= set(ids))


def test_v4_falls_back_to_v3_when_the_model_gives_no_rewrite(tools, registry):
    v4 = service(tools, registry, {})
    result = v4.control_plane("The checkout-api deployment in production needs a fresh start.", k=5)
    assert result.rewrite is None and result.route.operation_source == "default"
    assert result.stages["write_slots"] == 1


def test_v4_needs_a_rewriter(tools, registry):
    with pytest.raises(ValueError, match="rewriter"):
        DiscoveryService(tools, registry, embedder=None, profile="v4")


def test_the_rewrite_calls_cost_is_reported_even_when_its_reply_is_unusable():
    rewriter = QueryRewriter(ScriptedModel({}))
    assert rewriter.rewrite("unscripted") is None
    assert rewriter.usage("unscripted") == {"prompt_tokens": 120, "completion_tokens": 30, "latency_ms": 5.0, "usable": False}


def test_a_failed_rewrite_still_carries_its_cost_in_the_result(tools, registry):
    result = service(tools, registry, {}).control_plane("Checkout needs attention.", k=5)
    assert result.rewrite is None and result.rewrite_usage["prompt_tokens"] == 120


def test_the_prompt_shows_the_reply_format_and_every_system():
    from control_plane.discovery.rewrite import PROMPT, SYSTEMS
    assert '{"first_step": "...", "operation": "read" or "write", "system": "...", "environment": "..." or null}' in PROMPT
    assert "{{" not in PROMPT
    assert all(f"  - {name}: " in PROMPT for name in SYSTEMS)


def test_v4_ranks_the_tool_that_takes_a_named_identifier(tools, registry):
    request = "We're mid-incident. Pull recent logs from checkout-api-6c7d8e9f0-a1b2c on staging-eu-west-1."
    v4 = service(tools, registry, {request: reply("retrieve pod logs", "read", "monitoring")})
    result = v4.control_plane(request, k=5)
    pod_logs = {"kubernetes.get_pod_logs", "k8s_staging_eu.get_logs"}  # the staging copy is equivalent for a staging request
    assert pod_logs & set(result.tool_ids[:3])
    assert all(r["identifier_match"] for r in result.ranking if r["tool_id"] in pod_logs)


def test_v4_offers_one_write_slot_when_the_model_reads_a_request_without_a_read_only_signal(tools, registry):
    request = "Recycle checkout-api-7d9f8c6b5-2kq8x on prod-eu-west-1, it's the noisy one."
    v4 = service(tools, registry, {request: reply("check pod logs", "read", "kubernetes")})
    result = v4.control_plane(request, k=5)
    assert result.stages["write_slots"] == 1 and registry.get(result.tool_ids[-1]).side_effect


def test_v4_offers_no_write_slot_for_a_read_only_request(tools, registry):
    request = "Look at checkout-api pods in production. Do not change anything."
    v4 = service(tools, registry, {request: reply("list pods", "read", "kubernetes")})
    assert v4.control_plane(request, k=5).stages["write_slots"] == 0


def test_the_rewrite_may_name_the_target_environment():
    model = ScriptedModel({"q": reply("get pod logs", "read", "kubernetes", "staging"), "r": reply("get pods", "read", "kubernetes", "moon")})
    rewriter = QueryRewriter(model)
    assert rewriter.rewrite("q").environment == "staging" and rewriter.rewrite("r").environment is None


def test_v4_routes_to_the_environment_the_first_step_targets(tools, registry):
    request = "We're mid-incident in prod, but pull recent logs from checkout-api-6c7d8e9f0-a1b2c on staging-eu-west-1."
    v4 = service(tools, registry, {request: reply("retrieve pod logs", "read", "kubernetes", "staging")})
    result = v4.control_plane(request, k=5)
    assert result.route.environment == "staging"
    assert {"kubernetes.get_pod_logs", "k8s_staging_eu.get_logs"} & set(result.tool_ids)


def test_tools_that_take_a_named_identifier_join_the_candidates(tools, registry):
    request = "Look up ticket INC-4916 in the service desk for me."
    v4 = service(tools, registry, {request: reply("search for ticket INC-4916", "read", "incident management")})
    result = v4.control_plane(request, k=5)
    assert "itsm.get_incident" in result.tool_ids
    assert result.stages["identifier_candidates"] > 0
