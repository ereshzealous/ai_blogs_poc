"""Discovery v5: capability resolution (docs/CAPABILITY_RESOLUTION_V5.md).

    request -> route (keywords + model rewrite) + entities -> registry filter (+ answer constraint)
            -> hybrid search over capability-enriched documents + identifier/entity candidates -> rerank
            -> one canonical implementation per capability -> capability scores -> adaptive cut (+ write slot)

`decide` then compares the model's pick with the leading capability and says whether the decision may be automatic
or needs one question (control_plane/discovery/clarify.py).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from control_plane.discovery.clarify import Constraint
from control_plane.discovery.entities import EntityResolver
from control_plane.discovery.hybrid import HybridRetriever, Scored
from control_plane.ranking.reranker import (V3_MARGIN, V3_MAX_K, V3_WRITE_SLOTS, RerankWeights, collapse_equivalents,
                                            identifier_params, rerank)
from control_plane.registry.capabilities import CapabilityCatalog
from control_plane.registry.vocabulary import READ_ACTIONS, SYSTEM_DOMAIN
from control_plane.routing.router import Route

ABLATIONS = ("no-entities", "no-canonical")
# v1's ranking without the tool-level authority term (authority is decided per capability below) and without v4's
# identifier term (the entity boost below uses the same evidence)
V5_WEIGHTS = RerankWeights(authoritative=0.0, identifier_param=0.0)
AUTHORITATIVE_BOOST, ENTITY_BOOST, OPERATION_BOOST = 0.20, 0.30, 0.20  # set before calibration
DEPTH, EXTRA_CANDIDATES, MAX_DOMAINS, WRITE_SLOT_DEPTH = 30, 8, 4, 10
# entity types that name the thing a tool acts on; releases, commits and traces are values, not targets
TARGET_TYPES = frozenset({"pod", "instance", "task", "database", "cache", "flag", "channel", "incident", "deployment"})


@dataclass
class Resolution:
    tool_ids: list[str]
    capabilities: list[dict[str, Any]]  # every candidate capability, best first
    margin: float | None
    route: Route
    entities: list[dict[str, Any]]
    evidence_types: list[str]
    rewrite: dict[str, Any] | None
    rewrite_usage: dict[str, Any] | None
    stages: dict[str, int]
    latency_ms: float
    constraint: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"mode": "control_plane", "tool_ids": self.tool_ids, "latency_ms": round(self.latency_ms, 3),
                "route": self.route.to_dict(), "stages": self.stages, "ranking": self.capabilities[:12],
                "margin": self.margin, "entities": self.entities, "evidence_types": self.evidence_types,
                "rewrite": self.rewrite, "rewrite_usage": self.rewrite_usage, "constraint": self.constraint}


@dataclass
class Decision:
    auto: bool
    agreement: bool
    top: str | None
    picked: str | None
    tier: str | None
    margin: float | None
    threshold: float | None
    structural: bool
    checks: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"auto": self.auto, "agreement": self.agreement, "top": self.top, "picked": self.picked, "tier": self.tier,
                "margin": self.margin, "threshold": self.threshold, "structural": self.structural, "checks": self.checks}


def _dedupe(items: list[str | None]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


class CapabilityResolver:
    def __init__(self, service: Any, catalog: CapabilityCatalog, entities: EntityResolver, retriever: HybridRetriever,
                 ablation: str | None = None):
        if ablation is not None and ablation not in ABLATIONS:
            raise ValueError(f"unknown v5 ablation {ablation!r}; choose one of {', '.join(ABLATIONS)}")
        self.svc, self.catalog, self.entities, self.retriever, self.ablation = service, catalog, entities, retriever, ablation

    # -- resolution -----------------------------------------------------------------------------
    def resolve(self, request: str, k: int = 5, default_environment: str | None = "production", retrieval: str = "hybrid",
                constraint: Constraint | None = None) -> Resolution:
        t0 = time.perf_counter()
        svc = self.svc
        lexical = svc.router.route(request, default_environment=default_environment)
        explicit_env = svc.router.route(request, default_environment=None).environment
        rewrite = svc.rewriter.rewrite(request)
        route = svc._model_route(lexical, rewrite, default_environment) if rewrite is not None else lexical
        ents = [] if self.ablation == "no-entities" else self.entities.resolve(request)
        # only a named or id-shaped entity is evidence for a capability; an unnamed mention only suggests a system
        evidence = EntityResolver.evidence_types([e for e in ents if e.id is not None])
        environment = (explicit_env or (rewrite.environment if rewrite else None) or EntityResolver.environment(ents)
                       or default_environment)
        domains = _dedupe([rewrite.domain if rewrite else None] + EntityResolver.domains(ents) + route.domains)
        operation, source = route.operation, route.operation_source
        if constraint is not None:
            if constraint.dimension == "system":
                domains = _dedupe([SYSTEM_DOMAIN.get(constraint.value or "")] + domains)
            if constraint.dimension == "action":
                operation, source = ("read" if constraint.value in READ_ACTIONS else "write"), "answer"
            if constraint.reads_only:
                operation, source = "read", "answer"
        matched = route.matched | ({"_entities": [e.text for e in ents]} if ents else {})
        route = Route(domains[:MAX_DOMAINS], route.domain_scores, operation, environment, route.service, matched, source)
        # the operation boost follows the intent: an answer or an explicit "change nothing", else the model's judgement;
        # the route's own operation may stay "write" only to keep write tools available
        if source in ("answer", "read_only"):
            intended: str | None = operation
        elif rewrite is not None:
            intended = rewrite.operation
        else:
            intended = operation if source != "default" else None

        allowed = self._allowed(svc.filter_candidates(route), constraint)
        query = f"{rewrite.first_step}. {request}" if rewrite is not None else request
        hits = self.retriever.search(query, k=DEPTH, restrict_to=allowed, mode=retrieval)
        extra = self._extra_candidates(request, query, allowed, hits, evidence, retrieval)
        ranked = rerank(hits + extra, svc.registry, route, V5_WEIGHTS, request=request, required_params=svc.required_params)
        caps = self._capabilities(ranked, set(allowed), route, evidence, intended)
        shown = self._cut(caps, k)
        write_slots = 0
        if route.operation == "read" and source in ("default", "model"):
            # the best write capability after the reads, scored like the others (so a write on a named entity wins)
            readable = set(allowed)
            writes = [t for t in self._allowed(svc.filter_candidates(route, reads_only=False), constraint) if t not in readable]
            write_hits = self.retriever.search(query, k=WRITE_SLOT_DEPTH, restrict_to=writes, mode=retrieval)
            write_hits += self._extra_candidates(request, query, writes, write_hits, evidence, retrieval)
            write_ranked = rerank(write_hits, svc.registry, route, V5_WEIGHTS, request=request, required_params=svc.required_params)
            extra_caps = [c for c in self._capabilities(write_ranked, set(writes), route, evidence, "write")
                          if c["capability"] not in {s["capability"] for s in shown}][:V3_WRITE_SLOTS]
            shown, write_slots = shown + extra_caps, len(extra_caps)
        distinct = list(dict.fromkeys(c["capability"] for c in caps))
        margin = None
        if len(distinct) >= 2:
            best = {c["capability"]: c["score"] for c in reversed(caps)}
            margin = round(best[distinct[0]] - best[distinct[1]], 6)
        return Resolution(
            tool_ids=[c["tool_id"] for c in shown], capabilities=caps, margin=margin, route=route,
            entities=[{"text": e.text, "type": e.type, "id": e.id, "environment": e.environment, "known": e.known} for e in ents],
            evidence_types=sorted(evidence), rewrite=rewrite.to_dict() if rewrite is not None else None,
            rewrite_usage=svc.rewriter.usage(request), latency_ms=(time.perf_counter() - t0) * 1000,
            stages={"published": len(svc.tool_ids), "after_filters": len(allowed), "retrieved": len(hits),
                    "entity_candidates": len(extra), "capabilities": len(distinct), "returned": len(shown),
                    "write_slots": write_slots},
            constraint=constraint.to_dict() if constraint is not None else None,
        )

    def _allowed(self, tool_ids: list[str], constraint: Constraint | None) -> list[str]:
        out = []
        for t in tool_ids:
            cap = self.catalog.get(t)
            if cap is None:
                continue
            if constraint is None or constraint.allows(cap):
                out.append(t)
        return out

    def _extra_candidates(self, request: str, query: str, allowed: list[str], hits: list[Scored], evidence: set[str],
                          retrieval: str) -> list[Scored]:
        """Tools that take a named identifier or act on a resolved entity type join the candidates at the lowest score."""
        named = identifier_params(request)
        seen = {h.tool_id for h in hits}
        pool = []
        for t in allowed:
            if t in seen:
                continue
            cap = self.catalog.get(t)
            if named & self.svc.required_params.get(t, frozenset()) or (cap is not None and evidence & set(cap.entity_types)):
                pool.append(t)
        if not pool:
            return []
        floor = min((h.score for h in hits), default=1.0)
        found = self.retriever.search(query, k=EXTRA_CANDIDATES, restrict_to=pool, mode=retrieval)
        return [Scored(h.tool_id, floor, h.lexical_rank, h.semantic_rank) for h in found]

    def _capabilities(self, ranked: list[Any], allowed: set[str], route: Route, evidence: set[str],
                      intended: str | None) -> list[dict[str, Any]]:
        if self.ablation == "no-canonical":
            entries = [(r, self.catalog.capability_of(r.tool_id), r.tool_id) for r in collapse_equivalents(ranked, self.svc.registry)]
        else:
            best: dict[str, Any] = {}
            for r in ranked:
                cid = self.catalog.capability_of(r.tool_id)
                if cid is not None and (cid not in best or r.score > best[cid].score):
                    best[cid] = r
            entries = [(r, cid, self.catalog.canonical(cid, allowed, route.environment)) for cid, r in best.items()]
        out = []
        for r, cid, shown in entries:
            if cid is None or shown is None:
                continue
            cap = self.catalog.capabilities[cid]
            role = self.catalog.role_of(shown)
            entity = bool(evidence & set(cap.entity_types))
            operation = intended is not None and cap.side_effect == (intended == "write")
            score = r.score + AUTHORITATIVE_BOOST * (role == "authoritative") + ENTITY_BOOST * entity + OPERATION_BOOST * operation
            out.append({"capability": cid, "tool_id": shown, "score": round(score, 6), "retrieval": r.retrieval,
                        "domain_match": r.domain_match, "entity_match": entity, "operation_match": operation,
                        "identifier_match": r.identifier_match, "role": role})
        out.sort(key=lambda c: (-c["score"], c["capability"], c["tool_id"]))
        return out

    @staticmethod
    def _cut(caps: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
        if len(caps) <= k:
            return list(caps)
        floor = caps[k - 1]["score"] - V3_MARGIN
        extra = [c for c in caps[k:V3_MAX_K] if c["score"] >= floor]
        return caps[:k] + extra[: max(0, V3_MAX_K - k)]


def _view(first: Resolution | dict[str, Any]) -> tuple[list[dict[str, Any]], float | None, list[str], dict[str, Any] | None]:
    if isinstance(first, Resolution):
        return first.capabilities, first.margin, first.evidence_types, first.rewrite
    return first.get("ranking") or [], first.get("margin"), first.get("evidence_types") or [], first.get("rewrite")


def decide(first: Resolution | dict[str, Any], selected_tool: str | None, thresholds: dict[str, float | None], *,
           catalog: CapabilityCatalog) -> Decision:
    """Automatic only if the model's pick is discovery's leading capability, the model's rewrite agrees with it (system
    and read/write), the margin clears the tier's threshold and, for a high-risk write, the named target entity is
    resolved and the tool is the authoritative implementation. `first` is a Resolution or its recorded dict."""
    capabilities, margin, evidence, rewrite = _view(first)
    top = capabilities[0]["capability"] if capabilities else None
    picked = catalog.capability_of(selected_tool)
    if top is None:
        return Decision(False, False, None, picked, None, margin, None, False)
    cap = catalog.capabilities[top]
    targets = set(cap.entity_types) & TARGET_TYPES
    rewrite = rewrite or {}
    checks = {"entities": not targets or bool(targets & set(evidence)),
              "authoritative": selected_tool is not None and catalog.role_of(selected_tool) == "authoritative",
              "system": rewrite.get("domain") is not None and rewrite.get("domain") == cap.domain,
              "operation": rewrite.get("operation") == ("write" if cap.side_effect else "read")}
    structural = all(checks.values())
    agreement = selected_tool is not None and picked == top
    threshold = thresholds.get(cap.risk)
    clears = threshold is not None and (margin is None or margin >= threshold)
    consistent = checks["system"] and checks["operation"]
    high_risk_ok = cap.risk != "HIGH_RISK_WRITE" or (checks["entities"] and checks["authoritative"])
    auto = agreement and consistent and clears and high_risk_ok
    return Decision(auto, agreement, top, picked, cap.risk, margin, threshold, structural, checks)
