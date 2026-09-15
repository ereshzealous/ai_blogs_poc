"""Multi-step incident agent running through the MCP gateway.

Tool exposure depends on the mode:

* baseline       - every published tool is in the prompt on every step;
* search         - the top-K tools for the request, plus a `find_tools` meta-tool backed by hybrid search;
* control_plane  - the top-K tools from capability discovery, plus `find_tools` backed by the same pipeline.

`find_tools` mirrors deferred tool loading as used in practice: the model asks for more tools and the
results are added to the tools it can call. Every real tool call goes through `Gateway.call_tool`.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agent.llm import ChatModel
from agent.prompts import system_prompt
from control_plane.gateway.gateway import Gateway, InvocationContext
from control_plane.policy.approvals import ApprovalRequest
from control_plane.policy.engine import PolicyResult

FIND_TOOLS = {
    "type": "function",
    "function": {
        "name": "find_tools",
        "description": "Search the tool catalogue for tools matching a need (e.g. 'database connection pool stats') and "
                       "load them so you can call them. Returns tool names and descriptions.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
}
MAX_RESULT_CHARS = 2500


@dataclass
class AgentStep:
    index: int
    tool: str | None
    arguments: dict[str, Any]
    status: str
    policy: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    llm_latency_ms: float
    tools_in_prompt: int
    result_preview: str = ""
    is_error: bool = False


@dataclass
class AgentRun:
    mode: str
    steps: list[AgentStep] = field(default_factory=list)
    final_answer: str | None = None
    stopped: str = ""
    wall_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "final_answer": self.final_answer, "stopped": self.stopped, "wall_ms": round(self.wall_ms, 1),
                "steps": [s.__dict__ for s in self.steps]}


def scripted_approver(approve_if: Callable[[ApprovalRequest], bool]):
    """A human stand-in with a fixed decision table, so runs are reproducible."""

    async def approver(req: ApprovalRequest, decision: PolicyResult) -> bool:
        return approve_if(req)

    return approver


async def run_incident_agent(llm: ChatModel,gateway: Gateway, request: str, ctx: InvocationContext, *, mode: str,
                             discover: Callable[[str], list[str]] | None = None, max_steps: int = 16) -> AgentRun:
    """`discover(query)` returns exposed tool names (search / control_plane modes only)."""
    t0 = time.perf_counter()
    run = AgentRun(mode)
    loaded: list[str] = list(gateway.tools) if mode == "baseline" else list(dict.fromkeys(discover(request) if discover else []))
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt(ctx.identity.user_id, ctx.identity.roles, agent=True)},
        {"role": "user", "content": request},
    ]
    for i in range(max_steps):
        defs = [gateway.tools[n].definition() for n in loaded if n in gateway.tools]
        if mode != "baseline":
            defs.append(FIND_TOOLS)
        resp = llm.chat(messages, defs)
        if resp.error:
            run.stopped = f"llm_error: {resp.error}"
            break
        if not resp.tool_calls:
            run.final_answer = resp.content
            run.steps.append(AgentStep(i, None, {}, "final", None, resp.prompt_tokens, resp.completion_tokens, resp.latency_ms, len(defs)))
            run.stopped = "final_answer"
            break
        call = resp.tool_calls[0]
        messages.append({"role": "assistant", "content": resp.content or "",
                         "tool_calls": [{"function": {"name": call.name, "arguments": call.arguments}}]})
        if call.name == "find_tools" and discover is not None:
            found = [n for n in discover(str(call.arguments.get("query", ""))) if n in gateway.tools]
            loaded = list(dict.fromkeys(loaded + found))
            payload = [{"name": n, "description": gateway.tools[n].tool.description} for n in found]
            content, status, policy, is_error = json.dumps({"loaded_tools": payload}), "find_tools", None, False
        else:
            outcome = await gateway.call_tool(call.name, call.arguments, ctx)
            policy = outcome.policy.decision.value if outcome.policy else None
            status = outcome.status
            is_error = outcome.is_error
            body = outcome.result if outcome.executed else {"status": outcome.status, "message": outcome.result}
            content = json.dumps(body, default=str)[:MAX_RESULT_CHARS]
        messages.append({"role": "tool", "content": content, "tool_name": call.name})
        run.steps.append(AgentStep(i, call.name, call.arguments, status, policy, resp.prompt_tokens, resp.completion_tokens,
                                   resp.latency_ms, len(defs), content[:300], is_error))
    else:
        run.stopped = "max_steps"
    run.wall_ms = (time.perf_counter() - t0) * 1000
    return run
