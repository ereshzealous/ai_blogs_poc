"""Single-decision tool selection: one request in, one tool call out."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.llm import ChatModel, LLMResponse
from agent.prompts import system_prompt
from control_plane.policy.engine import Identity


@dataclass
class Selection:
    exposed_name: str | None
    tool_id: str | None
    arguments: dict[str, Any]
    tool_call_count: int
    response: LLMResponse


def exposed_to_tool_id(exposed_name: str | None) -> str | None:
    if not exposed_name or "__" not in exposed_name:
        return None
    server, name = exposed_name.split("__", 1)
    return f"{server}.{name}"


def select_tool(llm: ChatModel,tool_definitions: list[dict[str, Any]], request: str, identity: Identity) -> Selection:
    messages = [
        {"role": "system", "content": system_prompt(identity.user_id, identity.roles)},
        {"role": "user", "content": request},
    ]
    resp = llm.chat(messages, tool_definitions)
    first = resp.tool_calls[0] if resp.tool_calls else None
    name = first.name if first else None
    return Selection(name, exposed_to_tool_id(name), first.arguments if first else {}, len(resp.tool_calls), resp)
