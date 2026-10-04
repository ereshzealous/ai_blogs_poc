"""Context assembler: builds the working context an agent sees on one step, then throws it away.

It combines four kinds of state that live elsewhere, each with its own lifecycle:
  task + step   (a read-only view handed over by orchestration)
  conversation  (session store)
  memory        (episodic memory: provenance, confidence, expiry)
  knowledge     (runbook passages, cited)
and fits them into a token budget. Tool results are added by the agent runtime during the step.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agent_platform.context.session import SessionStore
from agent_platform.knowledge.retrieval import KnowledgeBase
from agent_platform.memory.store import MemoryStore
from agent_platform.telemetry.tracing import span


def tokens(text: str) -> int:
    return max(1, len(text) // 4)  # rough estimate; the model gateway records exact usage


@dataclass
class Section:
    kind: str  # task | conversation | memory | knowledge
    title: str
    text: str
    sources: list[str] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return tokens(self.text)


@dataclass
class WorkingContext:
    agent: str
    instructions: str
    sections: list[Section]
    budget: int

    def messages(self) -> list[dict[str, Any]]:
        body = "\n\n".join(f"## {s.title}\n{s.text}" for s in self.sections if s.text)
        return [{"role": "system", "content": self.instructions}, {"role": "user", "content": body}]

    def manifest(self) -> dict[str, Any]:
        by_kind: dict[str, int] = {}
        for s in self.sections:
            by_kind[s.kind] = by_kind.get(s.kind, 0) + s.tokens
        return {"agent": self.agent, "budget": self.budget, "instructions": tokens(self.instructions),
                "tokens_by_kind": by_kind, "sources": [src for s in self.sections for src in s.sources]}


class ContextAssembler:
    def __init__(self, sessions: SessionStore, memory: MemoryStore, knowledge: KnowledgeBase, budget_tokens: int = 6000):
        self.sessions = sessions
        self.memory = memory
        self.knowledge = knowledge
        self.budget = budget_tokens

    async def build(self, *, agent: str, instructions: str, task: str, step_view: dict[str, Any],
                    session_id: str | None, memory_scope: str | None, knowledge_query: str | None,
                    history_limit: int = 8, knowledge_k: int = 3) -> WorkingContext:
        with span("context.assemble", **{"gen_ai.agent.name": agent, "gen_ai.conversation.id": session_id}) as s:
            sections = [Section("task", "Task", task + "\n\nWorkflow step (read-only):\n" + json.dumps(step_view, indent=1),
                                [f"workflow:{step_view.get('workflow_id')}"])]
            if session_id:
                hist = self.sessions.history(session_id, history_limit)
                if hist:
                    sections.append(Section("conversation", "Conversation so far",
                                            "\n".join(f"{m['role']}: {m['content']}" for m in hist), [f"session:{session_id}"]))
            if memory_scope:
                mems = self.memory.recall(memory_scope)
                if mems:
                    sections.append(Section("memory", "Memory from earlier incidents (may be stale; verify before relying on it)",
                                            "\n".join(f"- {m.content} (source: {m.source}; confidence {m.confidence:.1f})"
                                                      for m in mems), [f"memory:{m.id}" for m in mems]))
            if knowledge_query:
                passages = await self.knowledge.retrieve(knowledge_query, knowledge_k)
                sections.append(Section("knowledge", "Runbooks (authoritative; cite them)",
                                        "\n".join(f"[{p.citation}] {p.text}" for p in passages),
                                        [p.citation for p in passages]))
            ctx = WorkingContext(agent, instructions, sections, self.budget)
            self._fit(ctx)
            m = ctx.manifest()
            s.set_attribute("lap.context.tokens", sum(m["tokens_by_kind"].values()) + m["instructions"])
            for kind, n in m["tokens_by_kind"].items():
                s.set_attribute(f"lap.context.{kind}_tokens", n)
            s.set_attribute("lap.context.sources", m["sources"])
            return ctx

    def _fit(self, ctx: WorkingContext) -> None:
        """Trim the least authoritative content first: old conversation, then memory."""
        order = ["conversation", "memory", "knowledge"]
        while sum(s.tokens for s in ctx.sections) + tokens(ctx.instructions) > ctx.budget:
            victim = next((s for kind in order for s in ctx.sections if s.kind == kind and s.text), None)
            if victim is None:
                break
            lines = victim.text.splitlines()
            victim.text = "\n".join(lines[1:]) if len(lines) > 1 else ""
