"""Model Services: routes, profiles, token accounting and budget behind one capability interface (ModelPort).

Callers ask for a route ("reasoning", "structured"), never a model.  Which model serves a route, with which provider
options, is config/models.yaml.  Usage is recorded per workflow and checked against the budget before each call.
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any

from layered_platform.config import load
from layered_platform.contracts import ModelReply, ToolCall
from layered_platform.models.ollama import OllamaProvider
from layered_platform.telemetry.tracing import annotate, current_ids, span


class BudgetExceeded(RuntimeError):
    pass


class ModelGateway:
    def __init__(self, db: sqlite3.Connection, spec: dict[str, Any] | None = None):
        self.db = db
        self.spec = spec or load("models.yaml")
        p = self.spec["provider"]
        self.provider = OllamaProvider(p["url"], float(p.get("timeout_s", 300)))
        self.budget = int(self.spec.get("budget", {}).get("tokens_per_workflow", 0))

    def profile(self, route: str) -> dict[str, Any]:
        return self.spec["profiles"][self.spec["routes"][route]["profile"]]

    def used(self, workflow_id: str) -> int:
        row = self.db.execute("SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0) FROM model_usage WHERE workflow_id=?", (workflow_id,)).fetchone()
        return int(row[0])

    async def generate(self, route: str, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]] | None = None,
                       schema: dict[str, Any] | None = None, caller: str = "", workflow_id: str = "") -> ModelReply:
        if self.budget and workflow_id and self.used(workflow_id) >= self.budget:
            raise BudgetExceeded(f"workflow {workflow_id} used its {self.budget}-token budget")
        prof = self.profile(route)
        t0 = time.perf_counter()
        with span("chat", **{"gen_ai.operation.name": "chat", "gen_ai.request.model": prof["model"], "f2.route": route,
                             "f2.agent": caller, "f2.workflow_id": workflow_id}):
            out = await self.provider.chat(prof, messages, tools, schema, caller=f"layered:{caller}")
            annotate(**{"gen_ai.usage.input_tokens": out["prompt_tokens"], "gen_ai.usage.output_tokens": out["completion_tokens"]})
        trace_id, _ = current_ids()
        self.db.execute("INSERT INTO model_usage (workflow_id, agent, route, model, prompt_tokens, completion_tokens, wall_s, trace_id, pid, ts) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (workflow_id, caller, route, out["model"], out["prompt_tokens"], out["completion_tokens"], round(time.perf_counter() - t0, 3),
                         trace_id, os.getpid(), time.time()))
        return ModelReply(content=out["content"], tool_calls=[ToolCall(**c) for c in out["tool_calls"]], model=out["model"],
                          prompt_tokens=out["prompt_tokens"], completion_tokens=out["completion_tokens"])

    async def close(self) -> None:
        await self.provider.close()
