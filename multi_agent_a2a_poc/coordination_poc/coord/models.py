"""Model services: one Ollama provider, one profile, one system-level budget, shared by every reasoning component.

The ModelGateway is constructed in every process (host and each A2A agent).  Before every call it checks the
workflow's token budget and deadline in the shared platform store, so the budget is system-level: tokens spent by the
diagnosis agent in its own process count against the same workflow as the coordinator's in the host.  The seed comes
from the workflow row, so all components of one repeat share it.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from coord.store import Store
from coord.tape import transport_from_env
from coord.telemetry import annotate, current_ids, span
from coord.util import load_config


class BudgetExceeded(RuntimeError):
    pass


class DeadlineExceeded(TimeoutError):
    pass


class ModelUnavailable(RuntimeError):
    pass


@dataclass
class ModelReply:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    wall_ms: float = 0.0


class Provider(Protocol):
    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, schema: dict[str, Any] | None,
                   seed: int, caller: str) -> ModelReply: ...


class OllamaProvider:
    def __init__(self) -> None:
        cfg = load_config("models.yaml")
        self.url = cfg["provider"]["url"].rstrip("/")
        self.profile = cfg["profile"]
        transport = transport_from_env()
        timeout = float(cfg["provider"]["timeout_s"])
        self.http = httpx.AsyncClient(timeout=timeout, transport=transport) if transport else httpx.AsyncClient(timeout=timeout)

    @property
    def model(self) -> str:
        return self.profile["model"]

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, schema: dict[str, Any] | None,
                   seed: int, caller: str) -> ModelReply:
        body: dict[str, Any] = {"model": self.profile["model"], "messages": messages, "stream": False,
                                "options": dict(self.profile.get("options", {}), seed=int(seed))}
        if "think" in self.profile:
            body["think"] = self.profile["think"]
        if tools:
            body["tools"] = tools
        if schema is not None:
            body["format"] = schema
        t0 = time.perf_counter()
        for attempt in range(3):
            try:
                resp = await self.http.post(f"{self.url}/api/chat", json=body, headers={"x-c1-caller": caller})
                resp.raise_for_status()
                data = resp.json()
                break
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise ModelUnavailable(f"{self.profile['model']}: {exc}") from exc
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
        return ModelReply(content=msg.get("content", "") or "", tool_calls=calls, model=data.get("model", self.profile["model"]),
                          prompt_tokens=int(data.get("prompt_eval_count", 0) or 0), completion_tokens=int(data.get("eval_count", 0) or 0),
                          wall_ms=round((time.perf_counter() - t0) * 1000, 1))

    async def close(self) -> None:
        await self.http.aclose()


class ModelGateway:
    def __init__(self, store: Store, provider: Provider | None = None):
        self.store = store
        self.provider = provider or OllamaProvider()

    @property
    def model(self) -> str:
        return getattr(self.provider, "model", "scripted")

    def check(self, workflow_id: str) -> None:
        wf = self.store.workflow(workflow_id)
        if not wf:
            return
        if wf["max_tokens"] and self.store.tokens_used(workflow_id) >= int(wf["max_tokens"]):
            raise BudgetExceeded(f"workflow {workflow_id} used its {wf['max_tokens']}-token budget")
        if wf["deadline"] and time.time() >= float(wf["deadline"]):
            raise DeadlineExceeded(f"workflow {workflow_id} passed its deadline")

    async def generate(self, messages: list[dict[str, Any]], *, component: str, role: str, workflow_id: str,
                       tools: list[dict[str, Any]] | None = None, schema: dict[str, Any] | None = None,
                       delegation_id: str | None = None) -> ModelReply:
        self.check(workflow_id)
        wf = self.store.workflow(workflow_id) or {}
        seed = int(wf.get("seed") or 7)
        with span("chat", **{"gen_ai.operation.name": "chat", "gen_ai.request.model": self.model, "c1.component": component,
                             "c1.role": role, "c1.workflow_id": workflow_id, "c1.delegation_id": delegation_id}):
            try:
                out = await self.provider.chat(messages, tools, schema, seed, caller=f"{component}:{workflow_id}")
            except Exception as exc:
                trace_id, _ = current_ids()
                self.store.record_usage(workflow_id=workflow_id, component=component, role=role, model=self.model, prompt_tokens=0,
                                        completion_tokens=0, wall_ms=0, ok=0, error=f"{type(exc).__name__}: {exc}"[:300],
                                        trace_id=trace_id, delegation_id=delegation_id)
                raise
            annotate(**{"gen_ai.usage.input_tokens": out.prompt_tokens, "gen_ai.usage.output_tokens": out.completion_tokens})
            trace_id, _ = current_ids()
        self.store.record_usage(workflow_id=workflow_id, component=component, role=role, model=out.model or self.model,
                                prompt_tokens=out.prompt_tokens, completion_tokens=out.completion_tokens, wall_ms=out.wall_ms, ok=1,
                                error=None, trace_id=trace_id, delegation_id=delegation_id)
        return out

    async def close(self) -> None:
        close = getattr(self.provider, "close", None)
        if close:
            await close()
