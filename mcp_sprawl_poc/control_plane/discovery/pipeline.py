"""Discovery pipelines for the benchmark modes.

* `search`         (mode B): hybrid retrieval over what MCP servers publish (name, description, parameters).
* `control_plane`  (mode C): intent routing -> registry filters -> hybrid retrieval over registry-enriched
                    documents -> registry-aware rerank.

Profiles: `v1` (default, the published benchmark) and `v2`, an experimental profile that adds scope-aware, write-aware
and identifier-aware reranking (control_plane/ranking/reranker.py) and needs the policy engine to check the caller's
scopes. v2 improved the dev split but not the test split; see docs/EVIDENCE_IMPROVEMENTS.md. `v3` (opt-in) keeps v1's
weights and adds the v3 router, an adaptive top-K of up to 7 tools, and, when the router assumed a read without any
signal, one write tool after the reads (from a separate search over write tools, so they never displace a read).
`v4` (opt-in) adds a model-written first step and read/write judgement before retrieval (control_plane/discovery/
rewrite.py), collapses equivalent tools to the authoritative one, adds the named-identifier signal, and keeps v3's
write slot when the model judged the request a read; without a usable rewrite it behaves like v3 plus the collapse and
the identifier signal.
`v5` (opt-in) is capability resolution: entity lookup, declared canonical capabilities, capability-level scores and a
confidence decision with one meaning-based question (control_plane/discovery/resolver.py, clarify.py;
docs/CAPABILITY_RESOLUTION_V5.md). Use `resolve()`; `control_plane()` returns its shortlist.

Both use the same retriever implementation and the same K, so the difference between them is what the
registry and router add, not a better search algorithm.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from control_plane.discovery.bm25 import BM25Index
from control_plane.discovery.hybrid import HybridRetriever, Scored
from control_plane.discovery.semantic import EmbeddingIndex, OllamaEmbedder
from control_plane.ranking.reranker import (V2_WEIGHTS, V3_MARGIN, V3_MAX_K, V3_WRITE_SLOTS, V4_WEIGHTS, RerankWeights,
                                            adaptive_cut, collapse_equivalents, identifier_params, rerank)
from control_plane.registry.registry import CapabilityRegistry, RegistryRecord
from control_plane.routing.router import IntentRouter, Route
from control_plane.telemetry import span


PROFILES = ("v1", "v2", "v3", "v4", "v5")


class PublishedLike(Protocol):
    server: str

    @property
    def tool_id(self) -> str: ...


def mcp_document(name: str, server: str, description: str, input_schema: Mapping[str, Any]) -> str:
    params = " ".join(input_schema.get("properties", {}).keys())
    return f"{server} {name} {name.replace('_', ' ')}. {description} Parameters: {params}"


def capability_document(base: str, catalog: Any, tool_id: str) -> str:
    """Discovery v5: the registry document plus the tool's declared job and its guidance."""
    cap = catalog.get(tool_id)
    if cap is None:
        return base
    return f"{base} Job: {cap.action} {cap.resource} in {cap.system}. {catalog.guidance(tool_id)}".rstrip()


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
    rewrite: dict[str, Any] | None = None
    rewrite_usage: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "tool_ids": self.tool_ids, "latency_ms": round(self.latency_ms, 3),
                "route": self.route.to_dict() if self.route else None, "stages": self.stages, "ranking": self.ranking} \
            | ({"rewrite": self.rewrite, "rewrite_usage": self.rewrite_usage} if self.rewrite_usage is not None else {})


class DiscoveryService:
    def __init__(self, tools: Mapping[str, tuple[str, str, str, Mapping[str, Any]]], registry: CapabilityRegistry,
                 embedder: OllamaEmbedder | None, *, router: IntentRouter | None = None, weights: RerankWeights | None = None,
                 depth: int = 30, profile: str = "v1", policy: Any | None = None, rewriter: Any | None = None,
                 ablation: str | None = None):
        """`tools` maps tool_id -> (server, name, description, input_schema), as published over MCP."""
        self.registry = registry
        self.router = router or IntentRouter(profile="v3" if profile in ("v3", "v4", "v5") else "v1")
        if profile not in PROFILES:
            raise ValueError(f"unknown discovery profile {profile!r}; choose one of {', '.join(PROFILES)}")
        if profile == "v2" and policy is None:
            raise ValueError("discovery v2 needs the policy engine to check the caller's scopes")
        if profile in ("v4", "v5") and rewriter is None:
            raise ValueError(f"discovery {profile} needs a rewriter (control_plane.discovery.rewrite.QueryRewriter)")
        if ablation is not None and profile != "v5":
            raise ValueError("ablations apply to discovery v5 only")
        self.rewriter = rewriter
        self.weights = weights or {"v2": V2_WEIGHTS, "v4": V4_WEIGHTS}.get(profile, RerankWeights())
        self.depth = depth
        self.profile = profile
        self.policy = policy
        self.tool_ids = sorted(tools)
        self.required_params = {tid: frozenset(schema.get("required") or ()) for tid, (_, _, _, schema) in tools.items()}
        plain = {tid: mcp_document(name, server, desc, schema) for tid, (server, name, desc, schema) in tools.items()}
        enriched = {tid: registry_document(doc, registry.get(tid)) for tid, doc in plain.items()}
        self.search_retriever = HybridRetriever(BM25Index(plain), EmbeddingIndex(plain, embedder) if embedder else None)
        self.cp_retriever = HybridRetriever(BM25Index(enriched), EmbeddingIndex(enriched, embedder) if embedder else None)
        self.resolver = None
        if profile == "v5":
            from control_plane.discovery.entities import EntityResolver
            from control_plane.discovery.resolver import CapabilityResolver
            from control_plane.registry.capabilities import CapabilityCatalog

            self.catalog = CapabilityCatalog.load()
            documents = {tid: capability_document(doc, self.catalog, tid) for tid, doc in enriched.items()}
            retriever = HybridRetriever(BM25Index(documents), EmbeddingIndex(documents, embedder) if embedder else None)
            self.resolver = CapabilityResolver(self, self.catalog, EntityResolver.from_scenario(), retriever, ablation)

    def resolve(self, request: str, k: int = 5, retrieval: str = "hybrid", constraint: Any | None = None,
                default_environment: str | None = "production") -> Any:
        """Discovery v5 (control_plane/discovery/resolver.py)."""
        if self.resolver is None:
            raise ValueError("resolve() needs discovery profile v5")
        return self.resolver.resolve(request, k=k, retrieval=retrieval, constraint=constraint,
                                     default_environment=default_environment)

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
    def filter_candidates(self, route: Route, *, reads_only: bool | None = None) -> list[str]:
        reads_only = route.operation == "read" if reads_only is None else reads_only
        records = self.registry.find(
            tool_ids=self.tool_ids,
            lifecycles=["active"],
            environment=route.environment,
            max_risk="READ_ONLY" if reads_only else None,
        )
        return [r.tool_id for r in records]

    def control_plane(self, request: str, k: int = 5, default_environment: str | None = "production",
                      retrieval: str = "hybrid", identity: Any | None = None) -> DiscoveryResult:
        """`identity` (v2 only) is the caller whose scopes the scope-aware rerank checks."""
        if self.resolver is not None:
            res = self.resolve(request, k=k, retrieval=retrieval, default_environment=default_environment)
            return DiscoveryResult("control_plane", res.tool_ids, res.latency_ms, res.route, res.stages, res.capabilities,
                                   res.rewrite, res.rewrite_usage)
        t0 = time.perf_counter()
        with span("discovery.control_plane", k=k, retrieval=retrieval, catalog_size=len(self.tool_ids)) as s:
            route = self.router.route(request, default_environment=default_environment)
            rewrite = self.rewriter.rewrite(request) if self.profile == "v4" else None
            query = request
            if rewrite is not None:
                route = self._model_route(route, rewrite, default_environment)
                query = f"{rewrite.first_step}. {request}"
            allowed = self.filter_candidates(route)
            hits = self.cp_retriever.search(query, k=self.depth, restrict_to=allowed, mode=retrieval)
            injected = self._identifier_candidates(request, query, allowed, hits, retrieval) if self.profile == "v4" else []
            hits = hits + injected
            can_run = None
            if self.profile == "v2" and identity is not None:
                def can_run(rec, _identity=identity):
                    return not self.policy.missing_scopes(_identity, rec.required_scopes)
            ranked = rerank(hits, self.registry, route, self.weights, request=request, can_run=can_run,
                            required_params=self.required_params)
            write_slots = 0
            if self.profile in ("v3", "v4"):
                if self.profile == "v4":
                    ranked = collapse_equivalents(ranked, self.registry)
                ranked = adaptive_cut(ranked, k, V3_MAX_K, V3_MARGIN)
                unconfirmed_read = route.operation == "read" and (
                    route.operation_source == "default" or (self.profile == "v4" and route.operation_source == "model"))
                if unconfirmed_read:
                    # no read-only signal in the request: offer the best write tool too, after the reads
                    readable = set(allowed)
                    writes = [t for t in self.filter_candidates(route, reads_only=False) if t not in readable]
                    write_hits = self.cp_retriever.search(query, k=V3_WRITE_SLOTS, restrict_to=writes, mode=retrieval)
                    extra = rerank(write_hits, self.registry, route, self.weights, request=request,
                                   required_params=self.required_params)[:V3_WRITE_SLOTS]
                    ranked, write_slots = ranked + extra, len(extra)
            else:
                ranked = ranked[:k]
            s.set_attribute("route.domains", ",".join(route.domains))
            s.set_attribute("route.operation", route.operation)
            s.set_attribute("candidates.after_filters", len(allowed))
        return DiscoveryResult(
            "control_plane", [r.tool_id for r in ranked], (time.perf_counter() - t0) * 1000, route,
            stages={"published": len(self.tool_ids), "after_filters": len(allowed), "retrieved": len(hits), "returned": len(ranked)}
            | ({"write_slots": write_slots} if self.profile in ("v3", "v4") else {})
            | ({"identifier_candidates": len(injected)} if self.profile == "v4" else {}),
            ranking=[{"tool_id": r.tool_id, "score": r.score, "retrieval": r.retrieval, "domain_match": r.domain_match,
                      "authoritative": r.authoritative, "scope_ok": r.scope_ok, "verb_match": r.verb_match,
                      "identifier_match": r.identifier_match} for r in ranked],
            rewrite=rewrite.to_dict() if rewrite is not None else None,
            rewrite_usage=self.rewriter.usage(request) if self.profile == "v4" else None,
        )

    def _identifier_candidates(self, request: str, query: str, allowed: list[str], hits: list[Scored],
                               retrieval: str) -> list[Scored]:
        """Tools whose published schema requires a parameter that an identifier in the request fills (an incident id,
        a channel, a pod) join the candidates even when text search ranked them outside the window. They enter at the
        window's lowest retrieval score, so the registry and identifier signals decide whether they rise."""
        named = identifier_params(request)
        if not named:
            return []
        seen = {h.tool_id for h in hits}
        pool = [t for t in allowed if t not in seen and self.required_params.get(t, frozenset()) & named]
        if not pool:
            return []
        floor = min((h.score for h in hits), default=1.0)
        found = self.cp_retriever.search(query, k=5, restrict_to=pool, mode=retrieval)
        return [Scored(h.tool_id, floor, h.lexical_rank, h.semantic_rank) for h in found]

    def _model_route(self, lexical: Route, rewrite: Any, default_environment: str | None) -> Route:
        """The model's first step and system decide the route; an explicit read-only request or a write signal in the
        request itself still wins, so writes are only removed when the model and the router agree on a read."""
        step = self.router.route(rewrite.first_step, default_environment=default_environment)
        domains = list(dict.fromkeys(([rewrite.domain] if rewrite.domain else []) + lexical.domains + step.domains))
        if lexical.operation_source == "read_only":
            operation, source = "read", "read_only"
        elif rewrite.operation == "read" and lexical.operation == "write":
            operation, source = "write", "terms"
        else:
            operation, source = rewrite.operation, "model"
        return Route(domains[: self.router.max_domains], lexical.domain_scores, operation,
                     rewrite.environment or lexical.environment, lexical.service,
                     lexical.matched | {"_model": [rewrite.first_step]}, source)
