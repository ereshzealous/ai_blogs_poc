"""Agent runtime: a bounded tool-use loop that ends in a validated structured output.

It knows nothing about MCP, providers, policy or persistence. It talks to a `ModelPort` and a `ToolPort`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from agent_platform.actions.types import ToolPort
from agent_platform.agents.contracts import AgentOutcome
from agent_platform.context.assembler import WorkingContext
from agent_platform.models.types import ModelPort
from agent_platform.telemetry.tracing import set_attrs, span

T = TypeVar("T", bound=BaseModel)


class AgentFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentSpec:
    name: str
    route: str
    max_steps: int = 10


class AgentRuntime:
    def __init__(self, models: ModelPort):
        self.models = models

    async def run(self, spec: AgentSpec, ctx: WorkingContext, output: type[T], *, workflow_id: str,
                  tools: ToolPort | None = None, session_id: str | None = None) -> AgentOutcome:
        with span(f"invoke_agent {spec.name}", **{"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": spec.name,
                                                  "gen_ai.conversation.id": session_id, "lap.workflow.id": workflow_id}) as s:
            messages = ctx.messages()
            steps, calls = 0, []
            if tools is not None:
                defs = tools.definitions()
                messages[-1]["content"] += ("\n\nUse the tools to gather evidence. Call several tools per turn when you can. "
                                            "When you have enough evidence, reply with a short plain-text conclusion and no tool calls.")
                while steps < spec.max_steps:
                    r = await self.models.chat(spec.route, messages, tools=defs, workflow_id=workflow_id, agent=spec.name)
                    steps += 1
                    if not r.tool_calls:
                        messages.append({"role": "assistant", "content": r.content})
                        break
                    messages.append({"role": "assistant", "content": r.content or "",
                                     "tool_calls": [{"function": {"name": c.name, "arguments": c.arguments}} for c in r.tool_calls]})
                    for c in r.tool_calls:
                        observation = await tools.call(c.name, c.arguments)
                        calls.append({"name": c.name, "arguments": c.arguments, "observation": observation[:160]})
                        messages.append({"role": "tool", "tool_name": c.name, "content": observation})
            result, repaired = await self._final(spec, messages, output, workflow_id)
            set_attrs(s, **{"lap.agent.steps": steps, "lap.agent.tool_calls": len(calls), "lap.agent.repaired": repaired})
            return AgentOutcome(result, steps, calls, ctx.manifest(), repaired)

    async def _final(self, spec: AgentSpec, messages: list[dict[str, Any]], output: type[T],
                     workflow_id: str) -> tuple[T, bool]:
        schema = output.model_json_schema()
        ask = {"role": "user", "content": f"Return your answer now as a single JSON object for `{output.__name__}` that "
                                          f"matches this JSON Schema. Use only facts from this conversation.\n"
                                          f"{json.dumps(schema)}"}
        convo = messages + [ask]
        last_error = ""
        for attempt in range(2):  # one bounded repair
            r = await self.models.chat(spec.route, convo, schema=schema, workflow_id=workflow_id, agent=spec.name)
            try:
                return output.model_validate_json(_json_block(r.content)), attempt > 0
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)[:600]
                convo = convo + [{"role": "assistant", "content": r.content},
                                 {"role": "user", "content": f"That JSON was invalid: {last_error}\nReturn corrected JSON only."}]
        raise AgentFailed(f"{spec.name}: no valid {output.__name__}: {last_error}")


def _json_block(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in model output")
    return text[start:end + 1]
