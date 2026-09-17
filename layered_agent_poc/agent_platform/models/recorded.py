"""Record or replay the Ollama provider's traffic (see the `traffic` package). Chosen by LAP_MODEL_TRAFFIC.

The gateway above does not change: spans, token usage, budgets and fallback all see the same responses, recorded or
replayed. In replay mode no model server is contacted.
"""

from __future__ import annotations

from typing import Any

import traffic
from agent_platform.models.ollama import OllamaProvider
from agent_platform.models.types import ModelUnavailable


def _request(model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, fmt: Any) -> dict[str, Any]:
    return {"model": model, "messages": messages, "tools": sorted(t["function"]["name"] for t in tools or []),
            "structured": fmt is not None}


class RecordingProvider:
    def __init__(self, inner: OllamaProvider, tape: traffic.Traffic):
        self.inner, self.tape = inner, tape
        self.name = inner.name

    async def close(self) -> None:
        await self.inner.close()

    async def chat(self, model: str, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]] | None,
                   fmt: dict[str, Any] | None, profile: dict[str, Any], caller: str = "") -> tuple[dict[str, Any], float]:
        data, latency = await self.inner.chat(model, messages, tools=tools, fmt=fmt, profile=profile)
        self.tape.record_chat(caller, model, _request(model, messages, tools, fmt), data, latency)
        return data, latency

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        vectors = await self.inner.embed(model, texts)
        self.tape.record_embed(model, texts, vectors)
        return vectors

    async def available_models(self) -> set[str]:
        return await self.inner.available_models()


class ReplayProvider:
    name = "ollama"  # the recorded provider; spans keep the same attributes

    def __init__(self, tape: traffic.Traffic):
        self.tape = tape

    async def close(self) -> None:
        return None

    async def chat(self, model: str, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]] | None,
                   fmt: dict[str, Any] | None, profile: dict[str, Any], caller: str = "") -> tuple[dict[str, Any], float]:
        try:
            return self.tape.replay_chat(caller, model, _request(model, messages, tools, fmt))
        except traffic.TrafficMissing as exc:
            raise ModelUnavailable(f"replay: {exc}") from exc

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        try:
            return self.tape.replay_embed(model, texts)
        except traffic.TrafficMissing as exc:
            raise ModelUnavailable(f"replay: {exc}") from exc

    async def available_models(self) -> set[str]:
        return self.tape.models()


def provider(url: str, timeout_s: float):
    tape = traffic.from_env()
    if tape is None:
        return OllamaProvider(url, timeout_s)
    if tape.mode == "replay":
        return ReplayProvider(tape)
    return RecordingProvider(OllamaProvider(url, timeout_s), tape)
