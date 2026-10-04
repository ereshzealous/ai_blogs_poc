"""Capability resolution: collapse retrieved implementations into a small decision set.

Retrieval returns implementations (some retired, some staging, some vendor, some
unregistered).  The control plane maps every hit to the capability it implements
(registry), drops hits the registry does not know, and surfaces each capability once —
as a capability-level tool whose schema omits the values the platform will bind.
Which implementation runs is decided later, per invocation, from entity facts.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from ..discovery.index import RRF_K, Hit
from ..mcp_host import ToolInfo
from ..registry.model import Registry

# Per binding profile: which parameters the platform binds from systems of record, and
# how the model-facing schema describes the ones that remain optional.
PLATFORM_BOUND: dict[str, dict[str, str]] = {
    "order_refund": {
        "payment_id": "Omit unless the requester named a specific payment id; the platform binds the charge from the payment record.",
        "amount": "Omit unless the requester asked for a specific partial amount; the platform binds the refundable amount from the payment record.",
    },
    "customer_credit": {
        "customer_id": "Omit if you give order_id; the platform binds the customer from the order.",
    },
    "customer_entity": {
        "customer_id": "Customer id if known; otherwise give lookup_email and the platform resolves the customer.",
    },
    "order_replacement": {
        "sku": "SKU of the item to replace, only as the requester named it. Omit when the order has a single item: the platform binds it.",
    },
}
EXTRA_MODEL_PARAMS: dict[str, dict[str, Any]] = {
    "customer_credit": {"order_id": {"type": "string", "description": "Order id, if the requester referenced an order instead of a customer id"}},
    "customer_entity": {"lookup_email": {"type": "string", "description": "Customer's current email, if no customer id is known"}},
}


def capability_tool_name(capability: str) -> str:
    return capability.replace(".", "_")


@dataclass(frozen=True)
class SurfacedCapability:
    capability: str
    tool_name: str
    description: str
    parameters: dict[str, Any]
    reference_implementation: str
    best_rank: int
    matched_implementations: tuple[str, ...]

    def ollama_tool(self) -> dict[str, Any]:
        return {"type": "function", "function": {"name": self.tool_name, "description": self.description, "parameters": self.parameters}}


def model_facing_schema(schema: dict[str, Any], profile: str | None) -> dict[str, Any]:
    s = copy.deepcopy(schema)
    props = s.setdefault("properties", {})
    required = list(s.get("required", []))
    for name, hint in PLATFORM_BOUND.get(profile or "", {}).items():
        if name in props:
            props[name] = {**props[name], "description": hint}
            if name in required:
                required.remove(name)
    for name, spec in EXTRA_MODEL_PARAMS.get(profile or "", {}).items():
        props[name] = spec
    s["required"] = required
    return s


class CapabilityResolver:
    def __init__(self, registry: Registry, tools: dict[str, ToolInfo], environment: str):
        self.registry = registry
        self.tools = tools
        self.environment = environment

    def reference_implementation(self, capability: str) -> str | None:
        cap = self.registry.capabilities.get(capability)
        if cap is None:
            return None
        for impl in [cap.authoritative.get("us"), cap.authoritative.get("global"), *cap.authoritative.values()]:
            if impl and impl in self.tools:
                return impl
        return None

    def surface(self, capability: str, best_rank: int, matched: tuple[str, ...]) -> SurfacedCapability | None:
        ref = self.reference_implementation(capability)
        if ref is None:
            return None
        rec = self.registry.get(ref)
        cap = self.registry.capabilities[capability]
        desc = cap.description
        if rec and rec.binding_profile in PLATFORM_BOUND:
            desc += " The platform resolves the authoritative implementation and binds record values (ids, amounts) from systems of record."
        return SurfacedCapability(
            capability=capability,
            tool_name=capability_tool_name(capability),
            description=desc,
            parameters=model_facing_schema(self.tools[ref].input_schema, rec.binding_profile if rec else None),
            reference_implementation=ref,
            best_rank=best_rank,
            matched_implementations=matched,
        )

    def collapse(self, hits: list[Hit], limit: int) -> tuple[list[SurfacedCapability], list[dict[str, Any]]]:
        """Return up to ``limit`` capabilities in hit-rank order, plus a trace of dropped hits."""
        order: list[str] = []
        matched: dict[str, list[str]] = {}
        first_rank: dict[str, int] = {}
        dropped: list[dict[str, Any]] = []
        for rank, h in enumerate(hits):
            rec = self.registry.get(h.qualified)
            if rec is None:
                dropped.append({"implementation": h.qualified, "why": "unregistered"})
                continue
            if rec.capability not in matched:
                matched[rec.capability] = []
                first_rank[rec.capability] = rank
                order.append(rec.capability)
            matched[rec.capability].append(h.qualified)
        out: list[SurfacedCapability] = []
        for c in order:
            sc = self.surface(c, first_rank[c], tuple(matched[c]))
            if sc is None:
                dropped.append({"capability": c, "why": "no deployable authoritative implementation in this estate"})
                continue
            out.append(sc)
            if len(out) >= limit:
                break
        return out, dropped


# Entity types implied by a referenced entity (an order implies its customer).
ENTITY_DIRECT = {"order": "order", "customer": "customer", "customer email": "customer", "payment": "payment", "ticket": "ticket"}
ENTITY_IMPLIES = {"order": {"customer"}, "customer": set(), "customer email": set(), "payment": {"order"}, "ticket": set()}
ENTITY_BONUS_DIRECT = 1.0 / (RRF_K + 5)  # prior for capabilities acting on a directly referenced entity type
ENTITY_BONUS_IMPLIED = 1.0 / (RRF_K + 20)  # weaker prior for implied types (an order's customer); never a filter
# (weights chosen on development-set recall only; see experiment/design-iterations.md)


def rank_capabilities(resolver: "CapabilityResolver", query_hits: list[tuple[str, list[Hit]]], entity_types: dict[str, float] | set[str], limit: int):
    """Fuse capability ranks across queries (RRF), add an entity-type prior, return the top ``limit``.

    Every retrieved, registered capability stays eligible; the prior only re-orders.  Capabilities of
    the referenced entity types that no query retrieved are eligible on the prior alone.
    """
    score: dict[str, float] = {}
    matched: dict[str, list[str]] = {}
    first_rank: dict[str, int] = {}
    dropped: list[dict[str, Any]] = []
    for _q, hits in query_hits:
        seen_here: set[str] = set()
        rank = 0
        for h in hits:
            rec = resolver.registry.get(h.qualified)
            if rec is None:
                dropped.append({"implementation": h.qualified, "why": "unregistered"})
                continue
            cap = rec.capability
            matched.setdefault(cap, [])
            if h.qualified not in matched[cap]:
                matched[cap].append(h.qualified)
            if cap in seen_here:
                continue
            seen_here.add(cap)
            score[cap] = score.get(cap, 0.0) + 1.0 / (RRF_K + rank + 1)
            first_rank[cap] = min(first_rank.get(cap, 10**6), rank)
            rank += 1
    bonus = entity_types if isinstance(entity_types, dict) else {t: ENTITY_BONUS_DIRECT for t in entity_types}
    for cap, rec in resolver.registry.capabilities.items():
        if rec.entity and rec.entity in bonus:
            score[cap] = score.get(cap, 0.0) + bonus[rec.entity]
            first_rank.setdefault(cap, 10**6)
            matched.setdefault(cap, [])
    ordered = sorted(score, key=lambda c: (-score[c], first_rank.get(c, 10**6), c))
    out: list[SurfacedCapability] = []
    for c in ordered:
        sc = resolver.surface(c, first_rank.get(c, 10**6), tuple(matched.get(c, ())))
        if sc is None:
            continue
        out.append(sc)
        if len(out) >= limit:
            break
    return out, dropped, {c: round(score[c], 5) for c in ordered[: limit * 2]}


def entity_priors(entity_kinds: list[str]) -> dict[str, float]:
    """Map referenced entity kinds to per-entity-type priors (direct beats implied)."""
    out: dict[str, float] = {}
    for k in entity_kinds:
        d = ENTITY_DIRECT.get(k)
        if d:
            out[d] = max(out.get(d, 0.0), ENTITY_BONUS_DIRECT)
        for i in ENTITY_IMPLIES.get(k, ()):
            out[i] = max(out.get(i, 0.0), ENTITY_BONUS_IMPLIED)
    return out
