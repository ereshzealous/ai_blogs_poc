"""Discovery v3 (opt-in): router fixes, a soft read filter and an adaptive top-K. v1 stays unchanged.

The router examples are requests from the main case set whose failures were analysed after the published run; the
held-out set (benchmark/prompts/holdout_cases.yaml) is what measures v3.
"""

from __future__ import annotations

import json

import pytest

from control_plane.discovery.hybrid import Scored
from control_plane.discovery.pipeline import DiscoveryService
from control_plane.paths import CATALOG_DIR
from control_plane.ranking.reranker import RerankWeights, adaptive_cut, rerank
from control_plane.routing.router import IntentRouter

V1, V3 = IntentRouter(), IntentRouter(profile="v3")


@pytest.mark.parametrize("request_text", [
    "Add a work note to INC-4917 saying we are investigating the database connection pool.",
    "Record in the incident that the likely cause is the v4.17 connection pool change.",
    "Undo the last checkout release in production.",
])
def test_v3_reads_these_requests_as_writes(request_text):
    assert V1.route(request_text).operation == "read"
    assert V3.route(request_text).operation == "write"


def test_v3_matches_plural_domain_terms():
    assert "itsm" not in V1.route("Find tickets about slow checkout.").domains
    assert "itsm" in V3.route("Find tickets about slow checkout.").domains


@pytest.mark.parametrize("request_text", [
    "Figure out whether we should roll back checkout.",
    "Should we restart checkout-api?",
    "Check whether payment-gateway is involved in INC-4917, then update the incident.",
])
def test_v3_routes_a_check_before_an_action_as_a_read(request_text):
    route = V3.route(request_text)
    assert route.operation == "read" and route.operation_source == "evaluate"


def test_v3_keeps_an_action_that_comes_first():
    route = V3.route("Roll back checkout-api to the previous production release, then verify that latency has recovered.")
    assert route.operation == "write" and route.operation_source == "terms"


def test_an_explicit_read_only_request_is_marked():
    route = V3.route("Investigate INC-4917 and determine the most likely root cause. Do not change anything.")
    assert route.operation == "read" and route.operation_source == "read_only"


def test_a_request_without_signals_is_an_unconfirmed_read():
    route = V3.route("Checkout needs attention.")
    assert route.operation == "read" and route.operation_source == "default"


def test_v1_routes_are_unchanged_apart_from_the_source_label():
    route = V1.route("Should we restart checkout-api?")
    assert route.operation == "write" and route.operation_source == "terms"


# ---------------------------------------------------------------------------------------------- ranking
def scored(*pairs):
    return [Scored(tool_id, score, None, None) for tool_id, score in pairs]


def test_adaptive_cut_adds_close_runners_up_only():
    ranked = rerank(scored(("a", 1.0), ("b", 0.95), ("c", 0.9), ("d", 0.85), ("e", 0.8), ("f", 0.78), ("g", 0.5), ("h", 0.49)),
                    registry=_EmptyRegistry(), route=V1.route("x"))
    assert [r.tool_id for r in adaptive_cut(ranked, k=5, max_k=8, margin=0.05)] == ["a", "b", "c", "d", "e", "f"]
    assert len(adaptive_cut(ranked, k=5, max_k=5, margin=0.05)) == 5
    assert len(adaptive_cut(ranked[:3], k=5, max_k=8, margin=0.05)) == 3


def test_v3_keeps_the_v1_weights(services):
    _, v3 = services
    assert v3.weights == RerankWeights()


class _EmptyRegistry:
    def get(self, tool_id):
        return None


@pytest.fixture(scope="module")
def tools():
    manifest = json.loads((CATALOG_DIR / "catalog_100.json").read_text())
    return {f"{t['server']}.{t['name']}": (t["server"], t["name"], t["description"], t["input_schema"]) for t in manifest["tools"]}


@pytest.fixture(scope="module")
def services(tools, registry):
    return DiscoveryService(tools, registry, embedder=None), DiscoveryService(tools, registry, embedder=None, profile="v3")


def test_v3_adds_write_slots_after_the_reads_for_an_unconfirmed_read(services, registry):
    v1, v3 = services
    request = "The checkout-api deployment in production needs a fresh start."
    old, new = v1.control_plane(request, k=5), v3.control_plane(request, k=5)
    assert not any(registry.get(t).side_effect for t in old.tool_ids)
    reads = [t for t in new.tool_ids if not registry.get(t).side_effect]
    writes = [t for t in new.tool_ids if registry.get(t).side_effect]
    assert len(writes) == 1 and new.tool_ids[-1] == writes[0]
    assert reads[:5] == old.tool_ids[: len(reads[:5])]
    assert new.stages["write_slots"] == len(writes)


def test_v3_adds_no_write_slots_when_the_route_is_confirmed(services):
    _, v3 = services
    for request in ("Restart the checkout-api deployment in production.", "Should we restart checkout-api?"):
        assert v3.control_plane(request, k=5).stages["write_slots"] == 0


def test_v3_still_removes_write_tools_when_told_not_to_change_anything(services, registry):
    _, v3 = services
    result = v3.control_plane("Look at checkout-api pods in production. Do not change anything.", k=5)
    assert result.stages["after_filters"] < result.stages["published"]
    assert all(not registry.get(t).side_effect for t in result.tool_ids)


def test_v3_returns_between_five_and_eight_tools(services):
    _, v3 = services
    for request in ("Restart the checkout-api deployment in production.", "Show me what's slow inside a checkout request."):
        assert 5 <= len(v3.control_plane(request, k=5).tool_ids) <= 8


def test_v1_is_still_the_default(services):
    v1, _ = services
    assert v1.profile == "v1" and v1.router.profile == "v1" and v1.weights == RerankWeights()


def test_v3_counts_a_plural_once():
    assert V3.route("Show pods").domain_scores == V1.route("Show pods").domain_scores
