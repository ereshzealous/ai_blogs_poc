"""Ollama /api/chat client with the guarantees the benchmark depends on.

* ``truncate: false`` — Ollama's default silently drops the head of an over-long
  prompt (measured: an 8,087-token prompt was evaluated as 514 tokens).  With
  truncation disabled the server returns ``exceed_context_size_error`` and we raise
  :class:`ContextOverflow`, which the runner records as a failed row, never a retry.
* fixed temperature / seed / num_ctx / think level, recorded per call.
* every raw request/response is kept so a row can be replayed without the model
  (see :class:`RecordedChat`).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from ..util import sha256_obj


class ContextOverflow(Exception):
    def __init__(self, n_prompt_tokens: int | None, n_ctx: int | None, raw: str):
        super().__init__(f"prompt of {n_prompt_tokens} tokens exceeds context {n_ctx}")
        self.n_prompt_tokens = n_prompt_tokens
        self.n_ctx = n_ctx
        self.raw = raw


class ModelCallError(Exception):
    """Transport/runtime failure talking to Ollama (infrastructure, not model behaviour)."""


class MalformedToolCall(Exception):
    """The model emitted a tool call the runtime could not parse (Ollama: "error parsing tool call").

    This is a MODEL failure and is scored, not an infrastructure invalidation.
    """


@dataclass(frozen=True)
class ModelConfig:
    model: str = "gpt-oss:20b"
    host: str = "http://localhost:11434"
    num_ctx: int = 131072
    temperature: float = 0.0
    seed: int = 4917
    think: str | bool = "low"
    num_predict: int = 4096
    timeout_s: float = 1800.0

    def options(self) -> dict[str, Any]:
        return {
            "num_ctx": self.num_ctx,
            "temperature": self.temperature,
            "seed": self.seed,
            "num_predict": self.num_predict,
        }

    def as_record(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "host": self.host,
            "num_ctx": self.num_ctx,
            "temperature": self.temperature,
            "seed": self.seed,
            "think": self.think,
            "num_predict": self.num_predict,
            "truncate": False,
        }


@dataclass
class ChatResult:
    message: dict[str, Any]
    prompt_eval_count: int | None
    eval_count: int | None
    prompt_eval_s: float | None
    eval_s: float | None
    load_s: float | None
    wall_s: float
    done_reason: str | None
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return list(self.message.get("tool_calls") or [])


def _post(url: str, body: dict[str, Any], timeout: float) -> tuple[int, str]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:  # infrastructure
        raise ModelCallError(str(e)) from e


def _parse_overflow(text: str) -> ContextOverflow | None:
    if "exceed" not in text or "context" not in text:
        return None
    n_prompt = n_ctx = None
    try:
        outer = json.loads(text)
        inner = outer.get("error")
        if isinstance(inner, str):
            inner = json.loads(inner)
        err = inner.get("error", inner) if isinstance(inner, dict) else {}
        n_prompt = err.get("n_prompt_tokens")
        n_ctx = err.get("n_ctx")
    except (ValueError, AttributeError):
        pass
    return ContextOverflow(n_prompt, n_ctx, text)


class OllamaChat:
    """Live model client."""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.calls: list[dict[str, Any]] = []  # raw call log for recording/replay

    def request_body(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, fmt: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "truncate": False,
            "think": self.config.think,
            "options": self.config.options(),
        }
        if tools:
            body["tools"] = tools
        if fmt is not None:
            body["format"] = fmt
        return body

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, fmt: dict[str, Any] | None = None) -> ChatResult:
        body = self.request_body(messages, tools, fmt)
        t0 = time.time()
        status, text = _post(f"{self.config.host}/api/chat", body, self.config.timeout_s)
        wall = time.time() - t0
        record = {
            "request_hash": sha256_obj(body),
            "tool_names": [t["function"]["name"] for t in (tools or [])],
            "status": status,
            "wall_s": round(wall, 3),
        }
        if status != 200:
            overflow = _parse_overflow(text)
            record["error"] = text[:2000]
            self.calls.append(record)
            if overflow is not None:
                raise overflow
            if "error parsing tool call" in text:
                raise MalformedToolCall(text[:1000])
            raise ModelCallError(f"HTTP {status}: {text[:500]}")
        raw = json.loads(text)
        record["response"] = raw
        self.calls.append(record)
        return _to_result(raw, wall)

    def count_prompt_tokens(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> int:
        """Exact prompt size as the runtime tokenises it (one generated token, cache-busted by caller)."""
        body = self.request_body(messages, tools)
        body["options"] = {**body["options"], "num_predict": 1}
        status, text = _post(f"{self.config.host}/api/chat", body, self.config.timeout_s)
        if status != 200:
            overflow = _parse_overflow(text)
            if overflow is not None and overflow.n_prompt_tokens:
                return int(overflow.n_prompt_tokens)
            raise ModelCallError(f"HTTP {status}: {text[:300]}")
        return int(json.loads(text).get("prompt_eval_count") or 0)


def _to_result(raw: dict[str, Any], wall: float) -> ChatResult:
    ns = 1e9
    return ChatResult(
        message=raw.get("message", {}),
        prompt_eval_count=raw.get("prompt_eval_count"),
        eval_count=raw.get("eval_count"),
        prompt_eval_s=(raw["prompt_eval_duration"] / ns) if raw.get("prompt_eval_duration") else None,
        eval_s=(raw["eval_duration"] / ns) if raw.get("eval_duration") else None,
        load_s=(raw["load_duration"] / ns) if raw.get("load_duration") else None,
        wall_s=wall,
        done_reason=raw.get("done_reason"),
        raw=raw,
    )


class RecordedChat:
    """Replays recorded model responses in order — no model required.

    Everything downstream of the model (MCP servers, discovery, binding, policy,
    approval, gateway, simulated systems) still runs for real during replay.
    """

    def __init__(self, recorded_calls: list[dict[str, Any]], config: ModelConfig):
        self._calls = list(recorded_calls)
        self._i = 0
        self.config = config
        self.calls: list[dict[str, Any]] = []
        self.request_mismatches = 0

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, fmt: dict[str, Any] | None = None) -> ChatResult:
        if self._i >= len(self._calls):
            raise ModelCallError("replay exhausted: more model calls than were recorded")
        rec = self._calls[self._i]
        self._i += 1
        body = OllamaChat(self.config).request_body(messages, tools, fmt)
        if sha256_obj(body) != rec.get("request_hash"):
            self.request_mismatches += 1
        self.calls.append({**rec, "replayed": True})
        if "error" in rec:
            overflow = _parse_overflow(rec["error"])
            if overflow is not None:
                raise overflow
            if "error parsing tool call" in rec["error"]:
                raise MalformedToolCall(rec["error"][:1000])
            raise ModelCallError(rec["error"][:500])
        return _to_result(rec["response"], rec.get("wall_s", 0.0))
