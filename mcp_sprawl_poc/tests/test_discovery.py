"""Candidate retrieval, Top-K, routing and metadata filtering (lexical only: no model server needed)."""

from __future__ import annotations

import json

from control_plane.discovery.bm25 import BM25Index
from control_plane.discovery.pipeline import DiscoveryService
from control_plane.discovery.text import tokenize
from control_plane.paths import CATALOG_DIR
from control_plane.routing.router import IntentRouter


def _tools(catalog: str) -> dict:
    m = json.loads((CATALOG_DIR / f"{catalog}.json").read_text())
    return {f"{t['server']}.{t['name']}": (t["server"], t["name"], t["description"], t["input_schema"]) for t in m["tools"]}


def test_tokenizer_splits_identifiers():
    assert tokenize("search_application_logs") == ["search", "application", "log"]
    # "get" is a stopword: nearly every read tool starts with it, so it carries no signal
    assert tokenize("getPodLogs for checkout-api") == ["pod", "log", "checkout", "api"]


def test_bm25_ranks_relevant_document_first():
    idx = BM25Index({"a": "query latency percentiles for a service", "b": "restart a pod", "c": "search logs"})
    assert idx.search("p95 latency of checkout", k=1)[0][0] == "a"
    assert idx.search("nothing matches here zzz") == []


def test_router_domains_operation_environment():
    r = IntentRouter().route("Roll back checkout-api in staging to v4.16")
    assert r.operation == "write" and r.environment == "staging" and r.service == "checkout-api"
    assert "delivery" in r.domains
    r = IntentRouter().route("Get checkout-api p95 latency", default_environment="production")
    assert r.operation == "read" and r.environment == "production" and r.domains[0] == "observability"


def test_search_returns_top_k():
    svc = DiscoveryService(_tools("catalog_500"), registry=_registry(), embedder=None)
    res = svc.search("search checkout-api logs for errors", k=5)
    assert len(res.tool_ids) == 5
    assert len(set(res.tool_ids)) == 5


def test_control_plane_filters_deprecated_shadow_and_writes_for_reads(registry):
    svc = DiscoveryService(_tools("catalog_500"), registry, embedder=None)
    route = svc.router.route("Get the checkout-api latency report from monitoring", default_environment="production")
    allowed = set(svc.filter_candidates(route))
    assert "legacy_monitoring.get_latency_report" not in allowed  # deprecated
    assert "ops_debug.tail_logs" not in allowed  # unregistered shadow tool
    assert all(registry.get(t).read_only for t in allowed)  # read intent: no side-effecting tools surfaced
    res = svc.control_plane("Get the checkout-api latency report from monitoring", k=5)
    assert len(res.tool_ids) <= 5 and all(t in allowed for t in res.tool_ids)


def test_control_plane_environment_filter(registry):
    svc = DiscoveryService(_tools("catalog_500"), registry, embedder=None)
    route = svc.router.route("Restart checkout-api pods in production")
    allowed = set(svc.filter_candidates(route))
    assert not any(t.startswith(("k8s_staging_eu.", "k8s_dev_eu.")) for t in allowed)
    assert "kubernetes.restart_deployment" in allowed


def test_search_mode_does_not_filter(registry):
    svc = DiscoveryService(_tools("catalog_500"), registry, embedder=None)
    res = svc.search("latency report monitoring", k=10)
    assert "legacy_monitoring.get_latency_report" in res.tool_ids  # plain search happily surfaces deprecated tools


def _embedder_or_skip():
    import pytest

    try:
        from control_plane.discovery.semantic import OllamaEmbedder

        return OllamaEmbedder()
    except Exception as exc:  # no Ollama server or model: the documented discovery examples need real embeddings
        pytest.skip(f"Ollama embeddings unavailable: {exc}")


def test_restart_example_ranking(registry):
    import pytest

    pytest.importorskip("httpx")
    svc = DiscoveryService(_tools("catalog_500"), registry, _embedder_or_skip())
    assert svc.search("Restart checkout-api.", k=5).tool_ids[:2] == ["cloud_ops.restart_service", "ops_debug.restart_service"]
    cp = svc.control_plane("Restart checkout-api.", k=5).tool_ids
    assert cp[0] == "kubernetes.restart_deployment" and "ops_debug.restart_service" not in cp


def test_latency_report_example_ranking(registry):
    svc = DiscoveryService(_tools("catalog_500"), registry, _embedder_or_skip())
    request = "Get the checkout-api latency report from monitoring."
    assert svc.search(request, k=5).tool_ids[0] == "legacy_monitoring.get_latency_report"
    cp = svc.control_plane(request, k=5)
    assert cp.tool_ids[0] == "observability.query_latency" and cp.stages["after_filters"] == 205


_REG = None


def _registry():
    global _REG
    if _REG is None:
        from control_plane.registry.registry import CapabilityRegistry

        _REG = CapabilityRegistry.load()
    return _REG
