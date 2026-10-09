"""The exclusion gates. Each returns None (pass) or the reason a record may not enter working context.

They read record metadata only, never ground-truth labels, and they are deterministic: the same record, query and
policy always give the same answer.
"""

from __future__ import annotations

from governed_memory.models.authority import AuthorityPolicy
from governed_memory.models.record import MemoryRecord, Query


def scope_gate(r: MemoryRecord, q: Query) -> str | None:
    """Gate 1: tenant, environment, entity, then user and session. Runs before any ranking."""
    s = r.scope
    if s.tenant != q.tenant:
        return "wrong_tenant"
    if s.environment not in ("all", q.environment):
        return "wrong_environment"
    if "*" not in s.entities and not set(s.entities) & set(q.entities):
        return "wrong_entity"
    if s.user and s.user != q.user:
        return "other_user"
    if s.session and s.session != q.session:
        return "other_session"
    return None


def lifecycle_gate(r: MemoryRecord, q: Query, present_ids: set[str]) -> str | None:
    """Gate 2: expired records leave; a superseded record leaves when its replacement exists."""
    if r.expires_at is not None and r.expires_at <= q.clock:
        return "expired"
    if r.superseded_by and r.superseded_by in present_ids:
        return "superseded"
    return None


def provenance_gate(r: MemoryRecord, q: Query, policy: AuthorityPolicy) -> str | None:
    """Gate 3: a record needs provenance and a trusted source class, and may not answer what memory never answers."""
    if r.claim_type in policy.never_from_memory:
        return "workflow_state_not_memory"
    if r.provenance is None or not r.provenance.created_by or not r.source.get("id"):
        return "no_provenance"
    if policy.tier(r).label == "unverified" and not policy.admit_unverified:
        return "unverified"
    return None
