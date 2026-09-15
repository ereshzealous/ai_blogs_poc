"""Discovery pipelines for the benchmark modes.

* `search`         (mode B): hybrid retrieval over what MCP servers publish (name, description, parameters).
* `control_plane`  (mode C): intent routing -> registry filters -> hybrid retrieval over registry-enriched
                    documents -> registry-aware rerank.

Both use the same retriever implementation and the same K, so the difference between them is what the
registry and router add, not a better search algorithm.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from control_plane.discovery.bm25 import BM25Index
from control_plane.discovery.hybrid import HybridRetriever
from control_plane.discovery.semantic import EmbeddingIndex, OllamaEmbedder
from control_plane.ranking.reranker import RerankWeights, rerank
from control_plane.registry.registry import CapabilityRegistry, RegistryRecord
from control_plane.routing.router import IntentRouter, Route
from control_plane.telemetry import span


class PublishedLike(Protocol):
    server: str

    @property
    def tool_id(self) -> str: ...


def mcp_document(name: str, server: str, description: str, input_schema: Mapping[str, Any]) -> str:
    params = " ".join(input_schema.get("properties", {}).keys())
    return f"{server} {name} {name.replace('_', ' ')}. {description} Parameters: {params}"


def registry_document(base: str, rec: RegistryRecord | None) -> str:
    if rec is None:
        return base
    return f"{base} Domain: {rec.domain}. Capability: {rec.capability}. Resource: {rec.resource_type}."


@dataclass
class DiscoveryResult:
    mode: str
    tool_ids: list[str]
    latency_ms: float
    route: Route | None = None
    stages: dict[str, int] = field(default_factory=dict)
    ranking: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "tool_ids": self.tool_ids, "latency_ms": round(self.latency_ms, 3),
                "route": self.route.to_dict() if self.route else None, "stages": self.stages, "ranking": self.ranking}


class DiscoveryService:
    def __init__(self, tools: Mapping[str, tuple[str, str, str, Mapping[str, Any]]], registry: CapabilityRegistry,
                 embedder: OllamaEmbedder | None, *, router: IntentRouter | None = None, weights: RerankWeights = RerankWeights(),
                 depth: int = 30):
        """`tools` maps tool_id -> (server, name, description, input_schema), as published over MCP."""
        self.registry = registry
        self.router = router or IntentRouter()
        self.weights = weights
        self.depth = depth
        self.tool_ids = sorted(tools)
        plain = {tid: mcp_document(name, server, desc, schema) for tid, (server, name, desc, schema) in tools.items()}
        enriched = {tid: registry_document(doc, registry.get(tid)) for tid, doc in plain.items()}
        self.search_retriever = HybridRetriever(BM25Index(plain), EmbeddingIndex(plain, embedder) if embedder else None)
        self.cp_retriever = HybridRetriever(BM25Index(enriched), EmbeddingIndex(enriched, embedder) if embedder else None)

    # -- mode B ---------------------------------------------------------------------------------
    def search(self, request: str, k: int = 5, retrieval: str = "hybrid") -> DiscoveryResult:
        t0 = time.perf_counter()
        with span("discovery.search", k=k, retrieval=retrieval, catalog_size=len(self.tool_ids)):
            hits = self.search_retriever.search(request, k=k, mode=retrieval)
        return DiscoveryResult("search", [h.tool_id for h in hits], (time.perf_counter() - t0) * 1000,
                               stages={"published": len(self.tool_ids), "returned": len(hits)},
                               ranking=[{"tool_id": h.tool_id, "rrf": round(h.score, 5), "bm25_rank": h.lexical_rank,
                                         "semantic_rank": h.semantic_rank} for h in hits])

    # -- mode C ---------------------------------------------------------------------------------
    def filter_candidates(self, route: Route) -> list[str]:
        records = self.registry.find(
            tool_ids=self.tool_ids,
            lifecycles=["active"],
            environment=route.environment,
            max_risk="READ_ONLY" if route.operation == "read" else None,
        )
        return [r.tool_id for r in records]

    def control_plane(self, request: str, k: int = 5, default_environment: str | None = "production",
                      retrieval: str = "hybrid") -> DiscoveryResult:
        t0 = time.perf_counter()
        with span("discovery.control_plane", k=k, retrieval=retrieval, catalog_size=len(self.tool_ids)) as s:
            route = self.router.route(request, default_environment=default_environment)
            allowed = self.filter_candidates(route)
            hits = self.cp_retriever.search(request, k=self.depth, restrict_to=allowed, mode=retrieval)
            ranked = rerank(hits, self.registry, route, self.weights)[:k]
            s.set_attribute("route.domains", ",".join(route.domains))
            s.set_attribute("route.operation", route.operation)
            s.set_attribute("candidates.after_filters", len(allowed))
        return DiscoveryResult(
            "control_plane", [r.tool_id for r in ranked], (time.perf_counter() - t0) * 1000, route,
            stages={"published": len(self.tool_ids), "after_filters": len(allowed), "retrieved": len(hits), "returned": len(ranked)},
            ranking=[{"tool_id": r.tool_id, "score": r.score, "retrieval": r.retrieval, "domain_match": r.domain_match,
                      "authoritative": r.authoritative} for r in ranked],
        )
