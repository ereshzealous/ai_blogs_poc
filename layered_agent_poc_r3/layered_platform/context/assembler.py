"""Context assembly: the working material a model gets for one invocation.

    CONTEXT    assembled here, per call, and thrown away
    STATE      the workflow's authoritative record (runtime checkpoints); facts are copied from it, never back
    MEMORY     recalled from memory/, labelled with its source
    KNOWLEDGE  retrieved runbook sections, labelled with their source

Models consume context.  The platform owns state and memory.
"""

from __future__ import annotations

import json
from typing import Any

from layered_platform.context.knowledge import KnowledgeBase
from layered_platform.memory.store import MemoryStore


class ContextAssembler:
    def __init__(self, knowledge: KnowledgeBase, memory: MemoryStore, top_k: int = 3, budget_chars: int = 12000):
        self.knowledge, self.memory, self.top_k, self.budget = knowledge, memory, top_k, budget_chars

    def build(self, instructions: str, task: str, facts: dict[str, Any], query: str, subject: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        sections = self.knowledge.search(query, self.top_k, doc_hint=subject.split("-")[0])
        memories = self.memory.recall(subject)
        parts = [f"## Facts from the workflow record\n{json.dumps(facts, indent=1, default=str)}"]
        if sections:
            parts.append("## Runbook excerpts\n" + "\n\n".join(f"[{s['source']}] {s['heading']}\n{s['text']}" for s in sections))
        if memories:
            parts.append("## Memory from earlier incidents (advisory, may be stale)\n" + "\n".join(f"- [{m['source']}] {m['text']}" for m in memories))
        body = "\n\n".join(parts)[: self.budget]
        manifest = {"knowledge": [s["source"] for s in sections], "memory": [m["id"] for m in memories], "chars": len(body)}
        return [{"role": "system", "content": instructions}, {"role": "user", "content": f"{task}\n\n{body}"}], manifest
