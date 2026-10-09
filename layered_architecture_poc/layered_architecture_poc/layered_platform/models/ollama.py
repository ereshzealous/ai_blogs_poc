"""Ollama provider adapter: the only module that knows Ollama's wire format (and the only one that imports httpx)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from recordreplay.tape import transport_from_env


class ModelUnavailable(RuntimeError):
    pass


class OllamaProvider:
    def __init__(self, url: str, timeout_s: float):
        self.url = url.rstrip("/")
        transport = transport_from_env()
        self.http = httpx.AsyncClient(timeout=timeout_s, transport=transport) if transport else httpx.AsyncClient(timeout=timeout_s)

    async def chat(self, profile: dict[str, Any], messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None,
                   schema: dict[str, Any] | None, caller: str) -> dict[str, Any]:
        body: dict[str, Any] = {"model": profile["model"], "messages": messages, "stream": False, "options": profile.get("options", {})}
        if "think" in profile:
            body["think"] = profile["think"]
        if tools:
            body["tools"] = tools
        if schema is not None:
            body["format"] = schema
        for attempt in range(3):
            try:
                resp = await self.http.post(f"{self.url}/api/chat", json=body, headers={"x-f2-caller": caller})
                resp.raise_for_status()
                data = resp.json()
                break
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise ModelUnavailable(f"{profile['model']}: {exc}") from exc
                await asyncio.sleep(2 * (attempt + 1))
        msg = data.get("message") or {}
        calls = []
        for c in msg.get("tool_calls") or []:
            args = c.get("function", {}).get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            calls.append({"name": c["function"]["name"], "arguments": args})
        return {"content": msg.get("content", ""), "tool_calls": calls, "model": data.get("model", profile["model"]),
                "prompt_tokens": data.get("prompt_eval_count", 0), "completion_tokens": data.get("eval_count", 0)}

    async def close(self) -> None:
        await self.http.aclose()
