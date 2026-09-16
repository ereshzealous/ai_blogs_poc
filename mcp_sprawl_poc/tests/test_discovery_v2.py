"""Discovery v2 (opt-in): scope-aware and write-aware reranking. v1 stays the default and unchanged.

The examples are dev-split requests; the test split is never used to shape discovery.
"""

from __future__ import annotations

import json

import pytest

from control_plane.discovery.pipeline import DiscoveryService
from control_plane.paths import CATALOG_DIR
from control_plane.policy.engine import Identity
from control_plane.ranking.reranker import V2_WEIGHTS, RerankWeights, identifier_params

ONCALL = Identity("oncall-1", ("sre-oncall",))


@pytest.fixture(scope="module")
def tools():
    manifest = json.loads((CATALOG_DIR / "catalog_500.json").read_text())
    return {f"{t['server']}.{t['name']}": (t["server"], t["name"], t["description"], t["input_schema"]) for t in manifest["tools"]}


@pytest.fixture(scope="module")
def v1(tools, registry):
    return DiscoveryService(tools, registry, embedder=None)


@pytest.fixture(scope="module")
def v2(tools, registry, policy):
    return DiscoveryService(tools, registry, embedder=None, profile="v2", policy=policy)


def test_v1_is_the_default_and_keeps_its_weights(v1):
    assert v1.profile == "v1" and v1.weights == RerankWeights()
    assert (RerankWeights().scope_mismatch, RerankWeights().write_side_effect, RerankWeights().verb_match) == (0, 0, 0)
    assert V2_WEIGHTS.scope_mismatch > 0 and V2_WEIGHTS.write_side_effect > 0 and V2_WEIGHTS.verb_match > 0


def test_v2_needs_a_policy_engine(tools, registry):
    with pytest.raises(ValueError, match="policy"):
        DiscoveryService(tools, registry, embedder=None, profile="v2")


def test_v1_ignores_the_caller(v1):
    request = "Did anyone change anything on checkout in the last hour?"
    assert v1.control_plane(request, k=5, identity=ONCALL).tool_ids == v1.control_plane(request, k=5).tool_ids


def test_v2_keeps_tools_the_caller_cannot_run_out_of_an_unroutable_request(v2, registry, policy):
    for request in ("Did anyone change anything on checkout in the last hour?", "Have we seen checkout problems like this before?"):
        top = v2.control_plane(request, k=5, identity=ONCALL).tool_ids
        assert top and all(not policy.missing_scopes(ONCALL, registry.get(t).required_scopes) for t in top), top


def test_v2_ranks_the_named_write_first_for_write_requests(v2):
    assert "collaboration.create_incident_channel" in v2.control_plane("Create an incident channel for INC-4917.", k=5, identity=ONCALL).tool_ids
    post = v2.control_plane("Post in #inc-4917-checkout-latency that checkout latency has recovered.", k=5, identity=ONCALL).tool_ids
    assert "collaboration.post_message" in post


def test_v2_still_surfaces_an_out_of_scope_tool_the_request_names(v2):
    top = v2.control_plane("Terminate the checkout batch worker VM i-0c41e7a9d2b3f5812 in production.", k=5, identity=ONCALL).tool_ids
    assert "cloud.terminate_instance" in top


def test_v2_without_a_caller_applies_no_scope_penalty(v2):
    ranked = v2.control_plane("Did anyone change anything on checkout in the last hour?", k=5).ranking
    assert all(r["scope_ok"] is None for r in ranked)


@pytest.mark.parametrize(("request_text", "params"), [
    ("Get the logs for pod checkout-api-7d9f8c6b5-2kq8x.", {"pod"}),
    ("Terminate instance i-0c41e7a9d2b3f5812.", {"instance_id"}),
    ("Create an incident channel for INC-4917.", {"incident_id"}),
    ("Post in #inc-4917-checkout-latency that checkout latency has recovered.", {"channel"}),
    ("Show the diff for commit a91f3c2.", {"sha", "commit"}),
    ("Is checkout-api healthy in production after v4.17 at 10:15?", set()),
])
def test_identifiers_in_a_request_name_the_parameters_they_fill(request_text, params):
    assert identifier_params(request_text) == params


def test_v2_ranks_the_tool_that_takes_a_named_identifier(v1, v2):
    request = "Get the logs for pod checkout-api-7d9f8c6b5-2kq8x."
    assert "kubernetes.get_pod_logs" not in v1.control_plane(request, k=5).tool_ids
    assert "kubernetes.get_pod_logs" in v2.control_plane(request, k=5, identity=ONCALL).tool_ids
