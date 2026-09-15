"""LLM providers with provider-reported token accounting.

The published benchmark runs local open-weight models through Ollama (no API keys, fixed seed, temperature 0).
Token counts come from the provider (`prompt_eval_count`, `eval_count`), not from estimates.

`OpenAIChat` runs the same harness on an OpenAI model (or any Chat Completions-compatible endpoint). The API key
is read from the `OPENAI_API_KEY` environment variable only, never from a flag, so it cannot end up in shell
history or in a run's `config.json`. Token counts come from the response's `usage` block.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OPENAI_URL = "https://api.openai.com/v1"
DEFAULT_OLLAMA_MODEL = "gpt-oss:20b"
PROVIDERS = ("ollama", "openai")


class ProviderError(RuntimeError):
    """A configuration problem (missing key, unknown model, rejected parameter) that retrying cannot fix."""


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall]
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: float
    prompt_eval_ms: float | None = None
    done_reason: str | None = None
    thinking_chars: int = 0
    error: str | None = None
    raw_message: dict[str, Any] = field(default_factory=dict)


class ChatModel(Protocol):
    model: str

    def model_info(self) -> dict[str, Any]: ...

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
             options: dict[str, Any] | None = None) -> LLMResponse: ...


def _parse_arguments(args: Any) -> dict[str, Any]:
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return {"_unparsed": args}
    return args if isinstance(args, dict) else {}


class OllamaChat:
    def __init__(self, model: str = DEFAULT_OLLAMA_MODEL, *, base_url: str = OLLAMA_URL, temperature: float | None = 0.0, seed: int = 7,
                 num_ctx: int = 131072, think: str | bool | None = "low", keep_alive: str = "2h", timeout_s: float = 1800):
        self.model, self.base_url = model, base_url
        self.options = {k: v for k, v in {"temperature": temperature, "seed": seed, "num_ctx": num_ctx}.items() if v is not None}
        self.think, self.keep_alive = think, keep_alive
        self._client = httpx.Client(timeout=timeout_s)

    def model_info(self) -> dict[str, Any]:
        tags = self._client.get(f"{self.base_url}/api/tags").json().get("models", [])
        tag = next((m for m in tags if m["name"] == self.model), {})
        show = self._client.post(f"{self.base_url}/api/show", json={"model": self.model}).json()
        details = show.get("details", {})
        version = self._client.get(f"{self.base_url}/api/version").json().get("version")
        return {"provider": "ollama", "ollama_version": version, "model": self.model, "digest": tag.get("digest"),
                "parameter_size": details.get("parameter_size"), "quantization": details.get("quantization_level"),
                "family": details.get("family"), "options": self.options, "think": self.think}

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
             options: dict[str, Any] | None = None) -> LLMResponse:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False,
                                "options": self.options | (options or {}), "keep_alive": self.keep_alive}
        if tools:
            body["tools"] = tools
        if self.think is not None:
            body["think"] = self.think
        t0 = time.perf_counter()
        try:
            resp = self._client.post(f"{self.base_url}/api/chat", json=body)
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            return LLMResponse("", [], None, None, (time.perf_counter() - t0) * 1000, error=f"{type(exc).__name__}: {exc}")
        latency = (time.perf_counter() - t0) * 1000
        if "error" in data:
            return LLMResponse("", [], None, None, latency, error=str(data["error"]))
        msg = data.get("message", {})
        calls = [ToolCall(c.get("function", {}).get("name", ""), _parse_arguments(c.get("function", {}).get("arguments", {})))
                 for c in msg.get("tool_calls") or []]
        return LLMResponse(
            content=msg.get("content", ""), tool_calls=calls, prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"), latency_ms=latency,
            prompt_eval_ms=(data["prompt_eval_duration"] / 1e6) if data.get("prompt_eval_duration") else None,
            done_reason=data.get("done_reason"), thinking_chars=len(msg.get("thinking") or ""), raw_message=msg,
        )


def to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert the harness's message history (Ollama shape) to Chat Completions shape.

    Chat Completions pairs every tool result with the assistant tool call it answers through `tool_call_id`, and
    wants arguments as a JSON string. The harness records neither, so ids are assigned in order: call_1, call_2, ...
    """
    out: list[dict[str, Any]] = []
    unanswered: list[str] = []
    n = 0
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            calls = []
            for c in m["tool_calls"]:
                n += 1
                call_id = c.get("id") or f"call_{n}"
                fn = c["function"]
                args = fn.get("arguments", {})
                calls.append({"id": call_id, "type": "function",
                              "function": {"name": fn["name"], "arguments": args if isinstance(args, str) else json.dumps(args)}})
                unanswered.append(call_id)
            out.append({"role": "assistant", "content": m.get("content") or None, "tool_calls": calls})
        elif m["role"] == "tool":
            call_id = m.get("tool_call_id") or (unanswered.pop(0) if unanswered else f"call_{n}")
            out.append({"role": "tool", "tool_call_id": call_id, "content": m["content"]})
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return out


class OpenAIChat:
    """OpenAI Chat Completions, or any compatible endpoint set through `OPENAI_BASE_URL`.

    Rate limits and server errors are retried with backoff. Errors that retrying cannot fix (bad key, unknown model,
    unsupported parameter, exhausted quota) raise `ProviderError`, so a paid run stops at once instead of writing
    hundreds of failed rows.
    """

    def __init__(self, model: str, *, api_key: str | None = None, base_url: str | None = None, temperature: float | None = 0.0,
                 seed: int | None = 7, reasoning_effort: str | None = None, timeout_s: float = 600, max_retries: int = 5,
                 transport: httpx.BaseTransport | None = None):
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ProviderError("OPENAI_API_KEY is not set. Put it in a .env file (see .env.example) and run with "
                                "`uv run --env-file .env ...`, or export it in your shell.")
        self.model = model
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or OPENAI_URL).rstrip("/")
        self.temperature, self.seed, self.reasoning_effort = temperature, seed, reasoning_effort
        self.max_retries = max_retries
        self._client = httpx.Client(timeout=timeout_s, transport=transport, headers={"Authorization": f"Bearer {key}"})

    def _settings(self) -> dict[str, Any]:
        return {k: v for k, v in {"temperature": self.temperature, "seed": self.seed, "reasoning_effort": self.reasoning_effort}.items()
                if v is not None}

    @staticmethod
    def _error(resp: httpx.Response) -> tuple[str, str | None]:
        try:
            err = resp.json().get("error") or {}
            return f"OpenAI API {resp.status_code}: {err.get('message') or resp.text[:300]}", err.get("code")
        except (json.JSONDecodeError, AttributeError):
            return f"OpenAI API {resp.status_code}: {resp.text[:300]}", None

    def model_info(self) -> dict[str, Any]:
        resp = self._client.get(f"{self.base_url}/models/{self.model}")
        if resp.status_code != 200:
            raise ProviderError(self._error(resp)[0])
        data = resp.json()
        return {"provider": "openai", "base_url": self.base_url, "model": self.model, "owned_by": data.get("owned_by"),
                "created": data.get("created"), "options": self._settings()}

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
             options: dict[str, Any] | None = None) -> LLMResponse:
        body: dict[str, Any] = {"model": self.model, "messages": to_openai_messages(messages), **self._settings()}
        if tools:
            body["tools"] = tools
        if options and "num_predict" in options:
            # Only used to measure prompt size without tools; a very small cap can be refused, and prompt_tokens is unaffected.
            body["max_completion_tokens"] = max(int(options["num_predict"]), 16)
        error, latency = "", 0.0
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = self._client.post(f"{self.base_url}/chat/completions", json=body)
            except httpx.HTTPError as exc:
                error, wait = f"{type(exc).__name__}: {exc}", 2.0 ** attempt
            else:
                latency = (time.perf_counter() - t0) * 1000
                if resp.status_code == 200:
                    return self._parse(resp.json(), latency)
                error, code = self._error(resp)
                if code == "insufficient_quota" or (resp.status_code < 500 and resp.status_code != 429):
                    raise ProviderError(error)
                wait = float(resp.headers.get("retry-after") or 2.0 ** attempt)
            if attempt < self.max_retries:
                time.sleep(min(wait, 60.0))
        return LLMResponse("", [], None, None, latency, error=error)

    @staticmethod
    def _parse(data: dict[str, Any], latency: float) -> LLMResponse:
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        usage = data.get("usage") or {}
        calls = [ToolCall(c["function"].get("name", ""), _parse_arguments(c["function"].get("arguments", "{}")))
                 for c in msg.get("tool_calls") or [] if c.get("type", "function") == "function" and "function" in c]
        return LLMResponse(content=msg.get("content") or "", tool_calls=calls, prompt_tokens=usage.get("prompt_tokens"),
                           completion_tokens=usage.get("completion_tokens"), latency_ms=latency,
                           done_reason=choice.get("finish_reason"), raw_message=msg)


def make_llm(provider: str, model: str | None, *, seed: int = 7, num_ctx: int = 131072, think: str | None = None,
             temperature: float | None = 0.0) -> ChatModel:
    """`think` is Ollama's think level (default "low") or OpenAI's `reasoning_effort` (omitted unless given)."""
    if provider == "ollama":
        return OllamaChat(model or DEFAULT_OLLAMA_MODEL, seed=seed, num_ctx=num_ctx, think="low" if think is None else think,
                          temperature=temperature)
    if provider == "openai":
        if not model or model == DEFAULT_OLLAMA_MODEL:
            raise ValueError("--provider openai needs --model with an OpenAI model id")
        return OpenAIChat(model, seed=seed, temperature=temperature, reasoning_effort=think)
    raise ValueError(f"unknown provider {provider!r}; choose one of {', '.join(PROVIDERS)}")


def describe_connect_error(exc: httpx.ConnectError) -> str:
    """One line for a refused connection, naming the server that could not be reached."""
    try:
        url = exc.request.url
        where = f"{url.scheme}://{url.host}" + (f":{url.port}" if url.port else "")
    except RuntimeError:
        where = "the model server"
    return f"cannot reach {where} ({exc}). If this is Ollama, start it with `ollama serve` or set OLLAMA_URL."


def temperature_arg(value: str) -> float | None:
    """argparse type for --temperature: a number, or "none" to leave the provider's default."""
    return None if value.lower() == "none" else float(value)
