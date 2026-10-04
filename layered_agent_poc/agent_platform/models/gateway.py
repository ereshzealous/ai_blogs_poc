"""Model gateway: routes, provider profiles, fallback, token budgets and GenAI spans.

Agents ask for a *route* ("reasoning", "summary"). Which model serves it, and with which provider options, is
configuration. Swapping gpt-oss:20b for qwen3:8b changes config/platform.yaml (or LAP_MODEL_REASONING), not agents.
A swap still changes behaviour, so the evals must be re-run after it.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_platform.models.recorded import provider as make_provider
from agent_platform.models.types import BudgetExceeded, ChatResult, Message, ModelUnavailable, ToolCall
from agent_platform.storage import connect
from agent_platform.telemetry.tracing import set_attrs, span

USAGE_DDL = """
CREATE TABLE IF NOT EXISTS model_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT, agent TEXT, route TEXT, model TEXT,
  input_tokens INTEGER, output_tokens INTEGER, latency_ms REAL, fallback INTEGER, at TEXT);
"""


class ModelGateway:
    def __init__(self, *, url: str, routes: dict[str, dict[str, Any]], profiles: dict[str, dict[str, Any]],
                 db_path: Path, timeout_s: float = 240, workflow_budget: int = 150_000):
        self.provider = make_provider(url, timeout_s)  # Ollama, or recorded/replayed Ollama traffic
        self.routes = routes
        self.profiles = profiles
        self.budget = workflow_budget
        self.db = connect(db_path)
        self.db.executescript(USAGE_DDL)

    async def close(self) -> None:
        await self.provider.close()

    def model_for(self, route: str) -> str:
        return self.routes[route]["model"]

    def tokens_used(self, workflow_id: str) -> int:
        row = self.db.execute("SELECT COALESCE(SUM(input_tokens + output_tokens), 0) FROM model_usage WHERE workflow_id=?",
                              (workflow_id,)).fetchone()
        return int(row[0])

    def usage(self, workflow_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT agent, route, model, input_tokens, output_tokens, latency_ms, fallback FROM model_usage "
                               "WHERE workflow_id=? ORDER BY id", (workflow_id,))
        return [dict(r) for r in rows]

    async def chat(self, route: str, messages: list[Message], *, tools: list[dict[str, Any]] | None = None,
                   schema: dict[str, Any] | None = None, workflow_id: str, agent: str) -> ChatResult:
        used = self.tokens_used(workflow_id)
        if used >= self.budget:
            raise BudgetExceeded(f"workflow {workflow_id} used {used} of {self.budget} tokens")
        cfg = self.routes[route]
        candidates = [(cfg["model"], False)] * 2 + ([(cfg["fallback"], True)] if cfg.get("fallback") else [])
        last: Exception | None = None
        for model, is_fallback in candidates:
            try:
                return await self._chat_once(route, model, is_fallback, messages, tools, schema, workflow_id, agent)
            except ModelUnavailable as exc:
                last = exc
        raise ModelUnavailable(f"route {route}: all models failed: {last}")

    async def _chat_once(self, route: str, model: str, is_fallback: bool, messages: list[Message],
                         tools: list[dict[str, Any]] | None, schema: dict[str, Any] | None,
                         workflow_id: str, agent: str) -> ChatResult:
        profile = self.profiles.get(model, {})
        with span(f"chat {model}", **{"gen_ai.operation.name": "chat", "gen_ai.provider.name": self.provider.name,
                                      "gen_ai.request.model": model, "gen_ai.agent.name": agent,
                                      "lap.model.route": route, "lap.model.fallback": is_fallback,
                                      "lap.workflow.id": workflow_id, "lap.tools.offered": len(tools or []),
                                      "lap.structured_output": schema is not None}) as s:
            data, latency = await self.provider.chat(model, messages, tools=tools, fmt=schema, profile=profile, caller=agent)
            msg = data.get("message", {})
            calls = [ToolCall(c["function"]["name"], _args(c["function"].get("arguments")))
                     for c in msg.get("tool_calls") or []]
            result = ChatResult(content=msg.get("content") or "", tool_calls=calls, model=model,
                                input_tokens=int(data.get("prompt_eval_count") or 0),
                                output_tokens=int(data.get("eval_count") or 0), latency_ms=latency,
                                fallback_used=is_fallback, raw_message=msg)
            set_attrs(s, **{"gen_ai.response.model": data.get("model", model),
                            "gen_ai.usage.input_tokens": result.input_tokens,
                            "gen_ai.usage.output_tokens": result.output_tokens,
                            "gen_ai.response.finish_reasons": [data.get("done_reason") or "stop"],
                            "lap.tool_calls": len(calls), "lap.latency_ms": round(latency, 1)})
            self.db.execute("INSERT INTO model_usage (workflow_id, agent, route, model, input_tokens, output_tokens, "
                            "latency_ms, fallback, at) VALUES (?,?,?,?,?,?,?,?,?)",
                            (workflow_id, agent, route, model, result.input_tokens, result.output_tokens, latency,
                             int(is_fallback), datetime.now(timezone.utc).isoformat()))
            return result

    async def embed(self, texts: list[str]) -> list[list[float]]:
        model = self.routes["embeddings"]["model"]
        with span(f"embeddings {model}", **{"gen_ai.operation.name": "embeddings", "gen_ai.provider.name": self.provider.name,
                                            "gen_ai.request.model": model, "lap.inputs": len(texts)}) as s:
            t0 = time.perf_counter()
            vectors = await self.provider.embed(model, texts)
            set_attrs(s, **{"lap.latency_ms": round((time.perf_counter() - t0) * 1000, 1)})
            return vectors

    async def missing_models(self) -> list[str]:
        have = await self.provider.available_models()
        want = {r["model"] for r in self.routes.values()}
        return sorted(m for m in want if m not in have and f"{m}:latest" not in have)


def _args(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
