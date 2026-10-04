"""Scripted ModelPort for tests that must not depend on a live model."""

from __future__ import annotations

import json
from typing import Any

from layered_platform.contracts import ModelReply, ToolCall

DIAGNOSIS = {"summary": "Pool exhaustion after release", "root_cause": "rel-2031 lowered maximumPoolSize to 10; connection pool exhausted",
             "suspect_service": "checkout-api", "suspect_release": "rel-2031", "evidence": ["db_pool_wait_ms 1810"], "confidence": "high"}
PROPOSAL = {"action": "rollback_release", "service": "checkout-api", "environment": "production", "target_release": "rel-2030",
            "rationale": "runbook RB-CHK-007"}


class ScriptedModel:
    """Diagnostician: two tool calls, then text, then JSON.  Remediator: JSON.  Records every request."""

    def __init__(self, proposal: dict[str, Any] | None = None, bad_first_json: bool = False):
        self.calls: list[dict[str, Any]] = []
        self.proposal = proposal or PROPOSAL
        self.bad_first_json = bad_first_json

    async def generate(self, route, messages, *, tools=None, schema=None, caller="", workflow_id=""):
        self.calls.append({"route": route, "caller": caller, "tools": bool(tools), "schema": bool(schema)})
        n_tool_msgs = sum(1 for m in messages if m["role"] == "tool")
        if caller == "diagnostician" and tools:
            if n_tool_msgs == 0:
                return ModelReply(content="", tool_calls=[ToolCall(name="deploy_history", arguments={"service": "checkout-api", "environment": "production"})], model="scripted")
            if n_tool_msgs == 1:
                return ModelReply(content="", tool_calls=[ToolCall(name="telemetry_metrics", arguments={"service": "checkout-api", "environment": "production", "metric": "db_pool_wait_ms", "minutes": 10})], model="scripted")
            return ModelReply(content="Pool exhaustion after rel-2031.", model="scripted")
        if self.bad_first_json and not any("invalid" in (m.get("content") or "") for m in messages):
            return ModelReply(content='{"action": "rollback_release"}', model="scripted")
        body = DIAGNOSIS if caller == "diagnostician" else self.proposal
        return ModelReply(content=json.dumps(body), model="scripted", prompt_tokens=100, completion_tokens=20)
