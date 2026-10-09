"""The audit manifest: every candidate, its content hash, gate decision, reason, rank and token cost.

It is written to the run folder for operators and never sent to the model (see assembler.model_manifest for the
model-visible counterpart, which carries counts only).
"""

from __future__ import annotations

from typing import Any

from governed_memory.context.assembler import Admission


def audit_manifest(a: Admission) -> dict[str, Any]:
    return {
        "arm": a.arm, "evidence_tokens": a.tokens,
        "admitted": [c.record.id for c in a.admitted], "historical": [c.record.id for c in a.historical],
        "excluded_counts": a.excluded_counts(),
        "candidates": [{"id": d.record_id, "content_sha256": d.content_sha256, "similarity": d.similarity,
                        "outcome": d.outcome, "reason": d.reason, "rank": d.rank, "tokens": d.tokens, "tier": d.tier}
                       for d in a.decisions],
    }
