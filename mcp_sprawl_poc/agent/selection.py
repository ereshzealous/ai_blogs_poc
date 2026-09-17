"""Single-decision tool selection: one request in, one tool call out.

With `ask_user`, the model may instead ask which tool the user means: it lists two or three of the tools it was shown,
the user picks one (or none), and the model then makes the call. The user is asked at most once.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent.llm import ChatModel, LLMResponse
from agent.prompts import system_prompt
from control_plane.policy.engine import Identity

ASK_USER_NAME = "ask_user"
ASK_USER_TOOL = {
    "type": "function",
    "function": {
        "name": ASK_USER_NAME,
        "description": "Ask the user which tool they mean. Use it only when no tool clearly fits the request or two tools "
                       "fit it equally well. List the two or three best tool names from the tools provided.",
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string"},
                           "options": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 3}},
            "required": ["question", "options"],
        },
    },
}
CLARIFY_NOTE = ("If no tool clearly fits the request, or two tools fit it equally well, call ask_user with the two or three "
                "best tool names instead of guessing.")

AskUser = Callable[[list[str], str], str | None]


@dataclass
class Selection:
    exposed_name: str | None
    tool_id: str | None
    arguments: dict[str, Any]
    tool_call_count: int
    response: LLMResponse
    clarification: dict[str, Any] | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    calls: int = 1


def exposed_to_tool_id(exposed_name: str | None) -> str | None:
    if not exposed_name or "__" not in exposed_name:
        return None
    server, name = exposed_name.split("__", 1)
    return f"{server}.{name}"


def _first_call(resp: LLMResponse) -> tuple[str | None, dict[str, Any]]:
    first = resp.tool_calls[0] if resp.tool_calls else None
    return (first.name, first.arguments) if first else (None, {})


def _total(values: list[int | None]) -> int | None:
    return None if all(v is None for v in values) else sum(v or 0 for v in values)


def select_tool(llm: ChatModel, tool_definitions: list[dict[str, Any]], request: str, identity: Identity, *,
                ask_user: AskUser | None = None) -> Selection:
    prompt = system_prompt(identity.user_id, identity.roles) + ("\n" + CLARIFY_NOTE if ask_user else "")
    messages: list[dict[str, Any]] = [{"role": "system", "content": prompt}, {"role": "user", "content": request}]
    resp = llm.chat(messages, tool_definitions + ([ASK_USER_TOOL] if ask_user else []))
    name, arguments = _first_call(resp)
    if not (ask_user and name == ASK_USER_NAME):
        return Selection(name, exposed_to_tool_id(name), arguments, len(resp.tool_calls), resp,
                         prompt_tokens=resp.prompt_tokens, completion_tokens=resp.completion_tokens)

    shown = [d["function"]["name"] for d in tool_definitions]
    options = [str(o) for o in (arguments.get("options") or []) if str(o) in shown][:3]
    question = str(arguments.get("question") or "")
    choice = ask_user(options, question) if options else None
    choice = choice if choice in options else None
    answer = f"The user chose {choice}." if choice else "The user said none of these is right; choose again from the tools provided."
    messages += [{"role": "assistant", "content": resp.content or "", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]},
                 {"role": "tool", "content": answer, "tool_name": ASK_USER_NAME}]
    tools = [d for d in tool_definitions if d["function"]["name"] == choice] if choice else tool_definitions
    second = llm.chat(messages, tools)
    name2, arguments2 = _first_call(second)
    if name2 == ASK_USER_NAME:  # asked twice: no answer, no call
        name2, arguments2 = None, {}
    return Selection(name2, exposed_to_tool_id(name2), arguments2, len(second.tool_calls), second,
                     clarification={"question": question, "options": options, "choice": choice},
                     prompt_tokens=_total([resp.prompt_tokens, second.prompt_tokens]),
                     completion_tokens=_total([resp.completion_tokens, second.completion_tokens]), calls=2)
