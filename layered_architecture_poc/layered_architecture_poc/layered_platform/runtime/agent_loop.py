"""The agent execution loop: bounded tool use, then a structured answer validated against a contract.

The loop knows ModelPort and ToolPort only.  It cannot name a model, reach a provider, open MCP, or cause a side
effect: the tools it is given are read capabilities, and its output is data the orchestrator decides what to do with.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from layered_platform.contracts import ModelPort, ToolPort
from layered_platform.telemetry.tracing import annotate, span


@dataclass
class AgentSpec:
    name: str
    route: str
    instructions: str
    max_turns: int = 8


class AgentFailed(RuntimeError):
    pass


async def run_agent(spec: AgentSpec, messages: list[dict[str, Any]], model: ModelPort, tools: ToolPort | None,
                    output: type[BaseModel], workflow_id: str) -> tuple[BaseModel, dict[str, Any]]:
    stats = {"model_calls": 0, "tool_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "repairs": 0}
    msgs = list(messages)
    with span("invoke_agent", **{"gen_ai.agent.name": spec.name, "f2.workflow_id": workflow_id}):
        defs = tools.definitions() if tools else None
        if defs:
            for _ in range(spec.max_turns):
                reply = await model.generate(spec.route, msgs, tools=defs, caller=spec.name, workflow_id=workflow_id)
                _count(stats, reply)
                msgs.append({"role": "assistant", "content": reply.content,
                             **({"tool_calls": [{"function": {"name": c.name, "arguments": c.arguments}} for c in reply.tool_calls]} if reply.tool_calls else {})})
                if not reply.tool_calls:
                    break
                for call in reply.tool_calls:
                    stats["tool_calls"] += 1
                    msgs.append({"role": "tool", "tool_name": call.name, "content": await tools.call(call.name, call.arguments)})
        schema = output.model_json_schema()
        msgs.append({"role": "user", "content": "Give your final answer now as one JSON object matching this schema. No prose.\n" + json.dumps(schema)})
        for attempt in range(2):
            reply = await model.generate(spec.route, msgs, schema=schema, caller=spec.name, workflow_id=workflow_id)
            _count(stats, reply)
            try:
                result = output.model_validate_json(reply.content)
                annotate(**{"f2.agent.repairs": stats["repairs"], "f2.agent.model_calls": stats["model_calls"]})
                return result, stats
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
