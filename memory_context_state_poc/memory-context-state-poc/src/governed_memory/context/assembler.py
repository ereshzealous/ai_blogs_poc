"""Working-context assembly. This is the only place the two arms differ.

    naive:     candidates in similarity order until the evidence budget is full (or the first K)
    governed:  scope -> lifecycle -> provenance/trust -> authority + freshness rank -> conflicts -> budget

Conversation and workflow facts are rendered identically for both arms: they come from their own stores (F2's
SessionStore and WorkflowStore), never from memory retrieval. Working context is built per call and never persisted.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from governed_memory.context.budget import fill, tokens
from governed_memory.models.authority import AuthorityPolicy
from governed_memory.models.record import MemoryRecord, Query
from governed_memory.retrieval.conflicts import contradicted_by
from governed_memory.retrieval.gates import lifecycle_gate, provenance_gate, scope_gate
from governed_memory.retrieval.ranking import rank
from governed_memory.retrieval.semantic import Candidate


@dataclass(frozen=True)
class Decision:
    record_id: str
    similarity: float
    outcome: str                 # admitted | historical | excluded
    reason: str | None           # why excluded / historical; None when admitted
    rank: int | None             # position after ranking (governed) or similarity order (naive); None if gated out
    tokens: int
    content_sha256: str
    tier: str | None = None      # governed only


@dataclass
class Admission:
    arm: str
    admitted: list[Candidate]
    historical: list[Candidate] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    tokens: int = 0

    def excluded_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(d.reason for d in self.decisions if d.outcome == "excluded").items()))


def _sha(r: MemoryRecord) -> str:
    return hashlib.sha256(r.content.encode()).hexdigest()


def _cost(c: Candidate) -> int:
    return tokens(c.record.content)


def naive_admission(candidates: list[Candidate], budget: int, k: int | None = None) -> Admission:
    ordered = sorted(candidates, key=lambda c: (-c.similarity, c.record.id))
    if k is not None:
        taken, skipped = ordered[:k], ordered[k:]
        used = sum(_cost(c) for c in taken)
    else:
        taken, skipped, used = fill(ordered, budget, _cost)
    ids = {c.record.id for c in taken}
    decisions = [Decision(c.record.id, c.similarity, "admitted" if c.record.id in ids else "excluded",
                          None if c.record.id in ids else ("top_k" if k is not None else "over_budget"),
                          i, _cost(c), _sha(c.record)) for i, c in enumerate(ordered)]
    return Admission("naive" if k is None else f"naive_k{k}", taken, [], decisions, used)


def governed_admission(candidates: list[Candidate], query: Query, policy: AuthorityPolicy, budget: int,
                       corpus: dict[str, MemoryRecord] | None = None) -> Admission:
    corpus = corpus if corpus is not None else {c.record.id: c.record for c in candidates}
    present = set(corpus)
    decisions: dict[str, Decision] = {}
    survivors: list[Candidate] = []
    for c in sorted(candidates, key=lambda c: c.record.id):
        r = c.record
        reason = scope_gate(r, query) or lifecycle_gate(r, query, present) or provenance_gate(r, query, policy)
        if reason:
            decisions[r.id] = Decision(r.id, c.similarity, "excluded", reason, None, _cost(c), _sha(r), policy.tier(r).label)
        else:
            survivors.append(c)

    ranked = rank(survivors, policy)
    clean, contested = [], []
    for c in ranked:
        by = contradicted_by(c.record, corpus, policy)
        (contested if by else clean).append((c, by))

    taken, skipped, used = fill([c for c, _ in clean], budget, _cost)
    hist, hist_skipped, used_h = fill([c for c, _ in contested], budget - used, _cost)
    order = {c.record.id: i for i, c in enumerate(ranked)}
    by_of = {c.record.id: by for c, by in contested}
    for c in taken:
        decisions[c.record.id] = Decision(c.record.id, c.similarity, "admitted", None, order[c.record.id], _cost(c), _sha(c.record), policy.tier(c.record).label)
    for c in hist:
        decisions[c.record.id] = Decision(c.record.id, c.similarity, "historical", f"contradicted_by:{by_of[c.record.id]}",
                                          order[c.record.id], _cost(c), _sha(c.record), policy.tier(c.record).label)
    for c in skipped:
        decisions[c.record.id] = Decision(c.record.id, c.similarity, "excluded", "over_budget", order[c.record.id], _cost(c), _sha(c.record), policy.tier(c.record).label)
    for c in hist_skipped:  # still marked: the audit shows it was contradicted, not merely crowded out
        decisions[c.record.id] = Decision(c.record.id, c.similarity, "excluded", f"over_budget:contradicted_by:{by_of[c.record.id]}",
                                          order[c.record.id], _cost(c), _sha(c.record), policy.tier(c.record).label)
    ordered_decisions = sorted(decisions.values(), key=lambda d: (-d.similarity, d.record_id))
    return Admission("governed", taken, hist, ordered_decisions, used + used_h)


# ---------------------------------------------------------------- prompt rendering
def _line(r: MemoryRecord) -> str:
    return f"[{r.id}] ({r.source_label()}, created {r.created_at.date().isoformat()}) {r.content}"


def model_manifest(a: Admission) -> str:
    """The model-visible manifest: admitted ids and exclusion COUNTS. Excluded content is never copied here."""
    excluded = ", ".join(f"{n} {reason}" for reason, n in a.excluded_counts().items()) or "none"
    return f"admitted: {len(a.admitted)} ({', '.join(c.record.id for c in a.admitted)}); historical: {len(a.historical)}; excluded: {excluded}"


def render_messages(prompt: dict[str, Any], query_text: str, workflow: dict[str, Any], conversation: list[dict[str, str]],
                    a: Admission, arm: str) -> list[dict[str, str]]:
    wf = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in workflow.items())
    conv = "\n".join(f"{m['role']}: {m['content']}" for m in conversation) or "(none)"
    evidence = "\n".join(_line(c.record) for c in a.admitted) or "(none)"
    parts = [f"## Incident\n{query_text}", f"## Workflow facts (from the workflow store)\n{wf}",
             f"## Conversation (this session)\n{conv}", f"## Evidence\n{evidence}"]
    if arm == "governed":
        if a.historical:
            hist = "\n".join(f"{_line(c.record)} [contradicted by {d.reason.split(':', 1)[1]}]"
                             for c in a.historical for d in a.decisions if d.record_id == c.record.id)
            parts.append(f"## Historical, contradicted by more authoritative evidence (do not act on)\n{hist}")
        parts.append(f"## Evidence manifest\n{model_manifest(a)}")
    return [{"role": "system", "content": prompt["system"]}, {"role": "user", "content": "\n\n".join(parts)}]
