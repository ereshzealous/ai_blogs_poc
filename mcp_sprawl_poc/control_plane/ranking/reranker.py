"""Registry-aware reranking of retrieval candidates.

Retrieval says "this text looks relevant". The registry can add what text cannot: whether the tool
belongs to a routed domain, and whether it is the authoritative tool for its resource.

Discovery v2 (experimental, opt-in; see control_plane/discovery/pipeline.py) adds four signals, written from dev-split
failures before the test split was run:
* scope: tools the caller's scopes cannot run are dropped unless their domain is routed, and then only penalised, so a
  request that names such a tool still surfaces it and policy denies it visibly;
* write intent: on write requests, a boost for tools with side effects;
* operation verb: on write requests, a boost for tools whose registry operation verb appears in the request;
* named identifier: a boost for tools whose published schema requires the parameter a concrete identifier in the
  request fills (a pod, an instance, an incident, a channel, a commit).
With the default weights these terms are zero, so v1 rankings are unchanged. v2 did not improve the test split
(docs/EVIDENCE_IMPROVEMENTS.md); the write-intent boost lifted non-authoritative write tools.

Discovery v3 (opt-in) keeps v1's weights. `adaptive_cut` returns up to `max_k` tools when the runners-up score within
`margin` of the k-th tool.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

from control_plane.discovery.hybrid import Scored
from control_plane.registry.registry import CapabilityRegistry, RegistryRecord
from control_plane.routing.router import Route


@dataclass(frozen=True)
class RerankWeights:
    retrieval: float = 1.0  # multiplier on the normalised RRF score (0..1)
    domain_match: float = 0.35  # tool's domain is one of the routed domains
    primary_domain: float = 0.15  # ... and it is the top routed domain
    authoritative: float = 0.2  # registry marks the tool authoritative for its resource
    scope_mismatch: float = 0.0  # v2 penalty: the caller's scopes cannot run the tool, whose domain the request names
    exclude_unrunnable_off_domain: bool = False  # v2: drop tools the caller cannot run whose domain the request does not name
    write_side_effect: float = 0.0  # v2: a write request, and the tool has side effects
    verb_match: float = 0.0  # v2: a write request that names one of the tool's registry operations
    identifier_param: float = 0.0  # v2: the request names an identifier that fills one of the tool's required parameters


V2_WEIGHTS = RerankWeights(scope_mismatch=0.3, exclude_unrunnable_off_domain=True, write_side_effect=0.2, verb_match=0.25,
                           identifier_param=0.25)

V3_MAX_K, V3_MARGIN, V3_WRITE_SLOTS = 7, 0.1, 1  # chosen on the main case set; see docs/EVIDENCE_IMPROVEMENTS.md
V4_WEIGHTS = RerankWeights(identifier_param=0.25)  # v1's weights plus the named-identifier signal (no write boost)

# Identifier shapes and the parameter names they fill in published tool schemas.
IDENTIFIER_SHAPES: tuple[tuple[re.Pattern[str], frozenset[str]], ...] = (
    (re.compile(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)*-[a-z0-9]{8,10}-[a-z0-9]{5}\b"), frozenset({"pod"})),
    (re.compile(r"\bi-[0-9a-f]{8,17}\b"), frozenset({"instance_id"})),
    (re.compile(r"(?<![#\w-])INC-\d+\b"), frozenset({"incident_id"})),
    (re.compile(r"(?<![#\w-])DEP-\d+\b"), frozenset({"deployment_id"})),
    (re.compile(r"(?<![\w&])#[a-z0-9][a-z0-9_-]*"), frozenset({"channel"})),
    (re.compile(r"(?<![\w-])(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}(?![\w-])"), frozenset({"sha", "commit"})),
)


def identifier_params(request: str) -> set[str]:
    """Parameter names that the concrete identifiers in `request` would fill."""
    return {name for pattern, names in IDENTIFIER_SHAPES if pattern.search(request) for name in names}


@dataclass(frozen=True)
class Ranked:
    tool_id: str
    score: float
    retrieval: float
    domain_match: bool
    authoritative: bool
    scope_ok: bool | None = None
    verb_match: bool = False
    identifier_match: bool = False


def _names_operation(text: str, rec: RegistryRecord) -> bool:
    return any(re.search(r"(?<![a-z])" + re.escape(op.lower()) + r"(?![a-z])", text) for op in rec.operations)


def rerank(candidates: list[Scored], registry: CapabilityRegistry, route: Route, weights: RerankWeights = RerankWeights(), *,
           request: str = "", can_run: Callable[[RegistryRecord], bool] | None = None,
           required_params: Mapping[str, frozenset[str]] | None = None) -> list[Ranked]:
    """`required_params` maps tool_id to the required parameters of its published schema (for the identifier signal)."""
    if not candidates:
        return []
    top = max(c.score for c in candidates)
    text = request.lower()
    named = identifier_params(request) if weights.identifier_param and required_params else set()
    write = route.operation == "write"
    ranked = []
    for c in candidates:
        rec = registry.get(c.tool_id)
        retrieval = c.score / top if top else 0.0
        in_domain = bool(rec and rec.domain in route.domains)
        primary = bool(rec and route.domains and rec.domain == route.domains[0])
        authoritative = bool(rec and rec.authoritative)
        scope_ok = None if can_run is None or rec is None else bool(can_run(rec))
        if scope_ok is False and not in_domain and weights.exclude_unrunnable_off_domain:
            continue
        side_effect = bool(write and rec and rec.side_effect)
        verb = bool(write and rec and _names_operation(text, rec))
        identifier = bool(named & required_params.get(c.tool_id, frozenset())) if named else False
        score = (weights.retrieval * retrieval + weights.domain_match * in_domain + weights.primary_domain * primary
                 + weights.authoritative * authoritative + weights.write_side_effect * side_effect + weights.verb_match * verb
                 + weights.identifier_param * identifier - weights.scope_mismatch * (scope_ok is False))
        ranked.append(Ranked(c.tool_id, round(score, 6), round(retrieval, 6), in_domain, authoritative, scope_ok, verb, identifier))
    ranked.sort(key=lambda r: (-r.score, r.tool_id))
    return ranked


def adaptive_cut(ranked: list[Ranked], k: int, max_k: int, margin: float) -> list[Ranked]:
    """The top k, plus runners-up (up to max_k in total) whose score is within `margin` of the k-th."""
    if len(ranked) <= k:
        return ranked
    floor = ranked[k - 1].score - margin
    extra = [r for r in ranked[k:max_k] if r.score >= floor]
    return ranked[:k] + extra[: max(0, max_k - k)]


def equivalence_key(rec: RegistryRecord) -> tuple:
    """Tools with the same key do the same job on the same kind of resource: vendor mirrors, per-cluster copies."""
    return (rec.collision_group or rec.tool_id, rec.resource_type, tuple(sorted(rec.operations)), rec.side_effect)


def collapse_equivalents(ranked: list[Ranked], registry: CapabilityRegistry) -> list[Ranked]:
    """Discovery v4: one tool per equivalence group, the authoritative one if present, at the group's best rank and score."""
    groups: dict[tuple, list[Ranked]] = {}
    for r in ranked:
        rec = registry.get(r.tool_id)
        groups.setdefault(equivalence_key(rec) if rec else ("unregistered", r.tool_id), []).append(r)
    out = []
    for members in groups.values():
        keep = next((m for m in members if m.authoritative), members[0])
        out.append(replace(keep, score=members[0].score))
    return out
