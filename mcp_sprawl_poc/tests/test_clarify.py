"""Ask the user when no tool clearly fits: the model lists options, the user picks, the model then calls the tool."""

from __future__ import annotations

from agent.llm import LLMResponse, ToolCall
from agent.selection import ASK_USER_NAME, select_tool
from control_plane.policy.engine import Identity

ONCALL = Identity("oncall-1", ("sre-oncall",))


def tool(name):
    return {"type": "function", "function": {"name": name, "description": name, "parameters": {"type": "object", "properties": {}}}}


TOOLS = [tool("itsm__get_incident"), tool("collaboration__create_incident_channel"), tool("itsm__create_change")]


class ScriptedModel:
    def __init__(self, *turns):
        self.turns = list(turns)
        self.seen: list[tuple[list[dict], list[str]]] = []

    def chat(self, messages, tools=None, options=None):
        self.seen.append(([dict(m) for m in messages], [t["function"]["name"] for t in tools or []]))
        name, args = self.turns.pop(0)
        return LLMResponse("", [ToolCall(name, args)] if name else [], 100, 10, 1.0)


def test_without_clarification_nothing_changes():
    model = ScriptedModel(("itsm__get_incident", {"incident_id": "INC-1"}))
    sel = select_tool(model, TOOLS, "show INC-1", ONCALL)
    assert sel.tool_id == "itsm.get_incident" and sel.clarification is None
    assert ASK_USER_NAME not in model.seen[0][1] and "ask_user" not in model.seen[0][0][0]["content"]


def test_the_user_picks_an_option_and_the_model_calls_it():
    model = ScriptedModel((ASK_USER_NAME, {"question": "Which one?", "options": ["itsm__create_change", "collaboration__create_incident_channel"]}),
                          ("collaboration__create_incident_channel", {"incident_id": "INC-4916"}))
    sel = select_tool(model, TOOLS, "INC-4916 needs a war room", ONCALL,
                      ask_user=lambda options, question: "collaboration__create_incident_channel")
    assert sel.tool_id == "collaboration.create_incident_channel" and sel.arguments == {"incident_id": "INC-4916"}
    assert sel.clarification == {"question": "Which one?", "options": ["itsm__create_change", "collaboration__create_incident_channel"],
                                 "choice": "collaboration__create_incident_channel"}
    assert model.seen[1][1] == ["collaboration__create_incident_channel"]
    assert "ask_user" in model.seen[0][0][0]["content"]
    assert (sel.prompt_tokens, sel.completion_tokens, sel.calls) == (200, 20, 2)


def test_when_no_option_is_right_the_model_chooses_again_from_all_tools():
    model = ScriptedModel((ASK_USER_NAME, {"question": "?", "options": ["itsm__create_change", "itsm__get_incident"]}),
                          ("collaboration__create_incident_channel", {}))
    sel = select_tool(model, TOOLS, "war room", ONCALL, ask_user=lambda options, question: None)
    assert sel.tool_id == "collaboration.create_incident_channel" and sel.clarification["choice"] is None
    assert model.seen[1][1] == [t["function"]["name"] for t in TOOLS]
    assert "none of these" in model.seen[1][0][-1]["content"]


def test_an_option_that_was_not_shown_cannot_be_chosen():
    model = ScriptedModel((ASK_USER_NAME, {"question": "?", "options": ["made_up__tool", "itsm__get_incident"]}), (None, {}))
    seen_options = []
    sel = select_tool(model, TOOLS, "x", ONCALL, ask_user=lambda options, question: seen_options.extend(options) or "made_up__tool")
    assert seen_options == ["itsm__get_incident"] and sel.tool_id is None


def test_a_second_request_for_clarification_is_not_answered():
    model = ScriptedModel((ASK_USER_NAME, {"question": "?", "options": ["itsm__get_incident", "itsm__create_change"]}),
                          (ASK_USER_NAME, {"question": "again?", "options": ["itsm__get_incident", "itsm__create_change"]}))
    sel = select_tool(model, TOOLS, "x", ONCALL, ask_user=lambda options, question: None)
    assert sel.tool_id is None and sel.calls == 2
