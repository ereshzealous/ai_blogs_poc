"""Ollama provider: the only module that knows Ollama's HTTP API."""

from __future__ import annotations

import time
from typing import Any

import httpx

from agent_platform.models.types import ModelUnavailable


class OllamaProvider:
    name = "ollama"

    def __init__(self, url: str, timeout_s: float):
        self.url = url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=timeout_s)

    async def close(self) -> None:
        await self.client.aclose()

    async def chat(self, model: str, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]] | None,
                   fmt: dict[str, Any] | None, profile: dict[str, Any], caller: str = "") -> tuple[dict[str, Any], float]:
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False,
                                "options": profile.get("options", {})}
        if "think" in profile:
            body["think"] = profile["think"]
        if tools:
            body["tools"] = tools
        if fmt is not None:
            body["format"] = fmt
        t0 = time.perf_counter()
        try:
            resp = await self.client.post(f"{self.url}/api/chat", json=body)
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"ollama {model}: {type(exc).__name__}: {exc}") from exc
        latency = (time.perf_counter() - t0) * 1000
        if resp.status_code >= 400:
            raise ModelUnavailable(f"ollama {model}: HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json(), latency

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        try:
            resp = await self.client.post(f"{self.url}/api/embed", json={"model": model, "input": texts})
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"ollama {model}: {type(exc).__name__}: {exc}") from exc
        if resp.status_code >= 400:
            raise ModelUnavailable(f"ollama {model}: HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()["embeddings"]

    async def available_models(self) -> set[str]:
        try:
            resp = await self.client.get(f"{self.url}/api/tags", timeout=3)
            return {m["name"] for m in resp.json().get("models", [])}
        except (httpx.HTTPError, ValueError):
            return set()
