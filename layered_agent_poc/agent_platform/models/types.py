"""The model interface the rest of the platform depends on. No provider, SDK or model name appears here."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

Message = dict[str, Any]  # {"role": system|user|assistant|tool, "content": str, "tool_calls"?: [...], "tool_name"?: str}


class ModelUnavailable(RuntimeError):
    """The provider failed or timed out; the gateway may fall back."""


class BudgetExceeded(RuntimeError):
    """The workflow spent its token budget."""


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCall]
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    fallback_used: bool = False
    raw_message: Message = field(default_factory=dict)


class ModelPort(Protocol):
    async def chat(self, route: str, messages: list[Message], *, tools: list[dict[str, Any]] | None = None,
                   schema: dict[str, Any] | None = None, workflow_id: str, agent: str) -> ChatResult: ...


class EmbeddingPort(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
