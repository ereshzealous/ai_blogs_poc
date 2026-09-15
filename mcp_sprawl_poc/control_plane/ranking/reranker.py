"""Registry-aware reranking of retrieval candidates.

Retrieval says "this text looks relevant". The registry can add what text cannot: whether the tool
belongs to a routed domain, and whether it is the authoritative tool for its resource.
"""

from __future__ import annotations

from dataclasses import dataclass

from control_plane.discovery.hybrid import Scored
from control_plane.registry.registry import CapabilityRegistry
from control_plane.routing.router import Route


@dataclass(frozen=True)
class RerankWeights:
    retrieval: float = 1.0  # multiplier on the normalised RRF score (0..1)
    domain_match: float = 0.35  # tool's domain is one of the routed domains
    primary_domain: float = 0.15  # ... and it is the top routed domain
    authoritative: float = 0.2  # registry marks the tool authoritative for its resource


@dataclass(frozen=True)
class Ranked:
    tool_id: str
    score: float
    retrieval: float
    domain_match: bool
    authoritative: bool


def rerank(candidates: list[Scored], registry: CapabilityRegistry, route: Route, weights: RerankWeights = RerankWeights()) -> list[Ranked]:
    if not candidates:
        return []
    top = max(c.score for c in candidates)
    ranked = []
    for c in candidates:
        rec = registry.get(c.tool_id)
        retrieval = c.score / top if top else 0.0
        in_domain = bool(rec and rec.domain in route.domains)
        primary = bool(rec and route.domains and rec.domain == route.domains[0])
        authoritative = bool(rec and rec.authoritative)
        score = (weights.retrieval * retrieval + weights.domain_match * in_domain + weights.primary_domain * primary
                 + weights.authoritative * authoritative)
        ranked.append(Ranked(c.tool_id, round(score, 6), round(retrieval, 6), in_domain, authoritative))
    ranked.sort(key=lambda r: (-r.score, r.tool_id))
    return ranked
