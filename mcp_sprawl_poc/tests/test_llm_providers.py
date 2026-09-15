"""The OpenAI provider, tested offline against a mock transport: no key, no network, no cost."""

from __future__ import annotations

import json

import httpx
import pytest

from agent.llm import OllamaChat, OpenAIChat, ProviderError, make_llm, temperature_arg, to_openai_messages

TOOLS = [{"type": "function", "function": {"name": "itsm__get_incident", "description": "Get an incident.",
                                           "parameters": {"type": "object", "properties": {"incident_id": {"type": "string"}}}}}]
MESSAGES = [{"role": "system", "content": "You are an incident agent."}, {"role": "user", "content": "Summarise INC-4917."}]
TOOL_CALL_REPLY = {
    "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_abc", "type": "function", "function": {"name": "itsm__get_incident", "arguments": "{\"incident_id\": \"INC-4917\"}"}}]},
        "finish_reason": "tool_calls"}],
    "usage": {"prompt_tokens": 812, "completion_tokens": 40, "completion_tokens_details": {"reasoning_tokens": 24}},
}


def _openai(handler, **kwargs) -> OpenAIChat:
    return OpenAIChat("gpt-test", api_key="sk-test-key", base_url="https://example.test/v1",
                      transport=httpx.MockTransport(handler), **kwargs)


def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        OpenAIChat("gpt-test")


def test_request_and_response_mapping():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), auth=request.headers["authorization"], body=json.loads(request.content))
        return httpx.Response(200, json=TOOL_CALL_REPLY)

    r = _openai(handler, reasoning_effort="low").chat(MESSAGES, TOOLS)
    assert seen["url"] == "https://example.test/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-test-key"
    body = seen["body"]
    assert (body["model"], body["temperature"], body["seed"], body["reasoning_effort"]) == ("gpt-test", 0.0, 7, "low")
    assert body["tools"] == TOOLS and body["messages"] == MESSAGES
    assert [(c.name, c.arguments) for c in r.tool_calls] == [("itsm__get_incident", {"incident_id": "INC-4917"})]
    assert (r.prompt_tokens, r.completion_tokens, r.done_reason, r.error) == (812, 40, "tool_calls", None)


def test_unset_settings_are_omitted():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=TOOL_CALL_REPLY)

    _openai(handler, temperature=None).chat(MESSAGES, None, {"num_predict": 1})
    assert "temperature" not in seen["body"] and "reasoning_effort" not in seen["body"] and "tools" not in seen["body"]
    assert seen["body"]["max_completion_tokens"] == 16


def test_agent_history_gets_matching_tool_call_ids():
    history = MESSAGES + [
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "itsm__get_incident", "arguments": {"incident_id": "INC-4917"}}}]},
        {"role": "tool", "content": "{\"status\": \"investigating\"}", "tool_name": "itsm__get_incident"},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "find_tools", "arguments": {"query": "pool stats"}}}]},
        {"role": "tool", "content": "{\"loaded_tools\": []}", "tool_name": "find_tools"},
    ]
    out = to_openai_messages(history)
    assert out[:2] == MESSAGES
    assert out[2] == {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_1", "type": "function", "function": {"name": "itsm__get_incident", "arguments": "{\"incident_id\": \"INC-4917\"}"}}]}
    assert out[3] == {"role": "tool", "tool_call_id": "call_1", "content": "{\"status\": \"investigating\"}"}
    assert out[4]["tool_calls"][0]["id"] == "call_2" and out[5]["tool_call_id"] == "call_2"


def test_rate_limits_are_retried(monkeypatch):
    monkeypatch.setattr("agent.llm.time.sleep", lambda s: None)
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(429, json={"error": {"message": "Rate limit reached", "code": "rate_limit_exceeded"}})
        return httpx.Response(200, json=TOOL_CALL_REPLY)

    r = _openai(handler).chat(MESSAGES, TOOLS)
    assert len(attempts) == 3 and r.error is None and r.tool_calls


@pytest.mark.parametrize("status, error", [
    (401, {"message": "Incorrect API key provided", "code": "invalid_api_key"}),
    (400, {"message": "Unsupported parameter: 'temperature'", "code": "unsupported_parameter"}),
    (429, {"message": "You exceeded your current quota", "code": "insufficient_quota"}),
])
def test_errors_that_retrying_cannot_fix_stop_the_run(status, error):
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(status, json={"error": error})

    with pytest.raises(ProviderError, match=str(status)):
        _openai(handler).chat(MESSAGES, TOOLS)
    assert len(attempts) == 1


def test_model_info_never_contains_the_key():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models/gpt-test"
        return httpx.Response(200, json={"id": "gpt-test", "object": "model", "created": 1, "owned_by": "openai"})

    info = _openai(handler, reasoning_effort="low").model_info()
    assert info["provider"] == "openai" and info["options"] == {"temperature": 0.0, "seed": 7, "reasoning_effort": "low"}
    assert "sk-test-key" not in json.dumps(info)


def test_make_llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    with pytest.raises(ValueError, match="--model"):
        make_llm("openai", None)
    assert isinstance(make_llm("openai", "gpt-test"), OpenAIChat)
    ollama = make_llm("ollama", None)
    assert isinstance(ollama, OllamaChat) and (ollama.model, ollama.think) == ("gpt-oss:20b", "low")
    assert ollama.options == {"temperature": 0.0, "seed": 7, "num_ctx": 131072}  # unchanged from the published run
    assert temperature_arg("none") is None and temperature_arg("0") == 0.0
