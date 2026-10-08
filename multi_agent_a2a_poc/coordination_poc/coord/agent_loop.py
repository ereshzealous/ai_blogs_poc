"""The agent loop shared by every reasoning component in every architecture (adapted from F2's runtime/agent_loop.py).

Bounded tool use (max_turns), then one structured answer validated against a pydantic contract, with one repair
attempt.  The loop can only reach tools through the ToolPort it is given (a GatewayTools bound to one token), so
an agent's authority is exactly its token's scopes, enforced by the gateway, never by the prompt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from coord.models import ModelGateway
from coord.telemetry import annotate, span


class ToolPort(Protocol):
    def definitions(self) -> list[dict[str, Any]]: ...
    async def call(self, name: str, arguments: dict[str, Any]) -> str: ...


@dataclass
class AgentSpec:
    name: str
    instructions: str
    max_turns: int = 8
    role: str = "work"          # "work" or "coordination": how its tokens are counted in the coordination-tax analysis


class AgentFailed(RuntimeError):
    pass


Guard = Callable[[BaseModel], Awaitable[str | None]]


async def run_agent(spec: AgentSpec, user: str, model: ModelGateway, tools: ToolPort | None, output: type[BaseModel], *,
                    workflow_id: str, delegation_id: str | None = None, guard: Guard | None = None,
                    guard_turns: int = 4) -> tuple[BaseModel, dict[str, Any]]:
    """`guard` checks the validated answer against the platform's ledgers (never against the model's prose).  If it
    returns a message, the agent gets it once, a few more tool turns, and one more final answer."""
    stats: dict[str, Any] = {"model_calls": 0, "tool_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "repairs": 0,
                             "max_prompt_tokens": 0, "guard_fired": 0}
    msgs: list[dict[str, Any]] = [{"role": "system", "content": spec.instructions}, {"role": "user", "content": user}]
    kw = dict(component=spec.name, role=spec.role, workflow_id=workflow_id, delegation_id=delegation_id)
    with span("invoke_agent", **{"gen_ai.agent.name": spec.name, "c1.workflow_id": workflow_id, "c1.delegation_id": delegation_id}):
        defs = tools.definitions() if tools else None
        await _tool_loop(msgs, defs, tools, model, kw, stats, spec.max_turns)
        result = await _final(spec, output, msgs, model, kw, stats)
        if guard is not None:
            problem = await guard(result)
            if problem:
                stats["guard_fired"] += 1
                annotate(**{"c1.guard": problem[:200]})
                msgs += [{"role": "assistant", "content": result.model_dump_json()}, {"role": "user", "content": problem}]
                await _tool_loop(msgs, defs, tools, model, kw, stats, guard_turns)
                result = await _final(spec, output, msgs, model, kw, stats)
        annotate(**{"c1.agent.repairs": stats["repairs"], "c1.agent.model_calls": stats["model_calls"]})
        return result, stats


async def _tool_loop(msgs: list[dict[str, Any]], defs: list[dict[str, Any]] | None, tools: ToolPort | None, model: ModelGateway,
                     kw: dict[str, Any], stats: dict[str, Any], turns: int) -> None:
    if not defs or tools is None:
        return
    for _ in range(turns):
        reply = await model.generate(msgs, tools=defs, **kw)
        _count(stats, reply)
        msgs.append({"role": "assistant", "content": reply.content,
                     **({"tool_calls": [{"function": {"name": c["name"], "arguments": c["arguments"]}} for c in reply.tool_calls]}
                        if reply.tool_calls else {})})
        if not reply.tool_calls:
            return
        for call in reply.tool_calls:
            stats["tool_calls"] += 1
            msgs.append({"role": "tool", "tool_name": call["name"], "content": await tools.call(call["name"], call["arguments"])})


async def _final(spec: AgentSpec, output: type[BaseModel], msgs: list[dict[str, Any]], model: ModelGateway, kw: dict[str, Any],
                 stats: dict[str, Any]) -> BaseModel:
    schema = output.model_json_schema()
    msgs.append({"role": "user", "content": "Give your final answer now as one JSON object matching this schema. No prose.\n"
                 + json.dumps(schema, separators=(",", ":"))})
    for attempt in range(2):
        reply = await model.generate(msgs, schema=schema, **kw)
        _count(stats, reply)
        try:
            return output.model_validate_json(reply.content)
        except ValidationError as exc:
            if attempt == 1:
                raise AgentFailed(f"{spec.name}: answer did not match {output.__name__}: {exc.errors()[:2]}") from None
            stats["repairs"] += 1
            msgs += [{"role": "assistant", "content": reply.content},
                     {"role": "user", "content": f"That answer is invalid: {exc.errors()[:3]}. Return corrected JSON only."}]
    raise AgentFailed(spec.name)


def _count(stats: dict[str, Any], reply: Any) -> None:
    stats["model_calls"] += 1
    stats["prompt_tokens"] += reply.prompt_tokens
    stats["completion_tokens"] += reply.completion_tokens
    stats["max_prompt_tokens"] = max(stats["max_prompt_tokens"], reply.prompt_tokens)
