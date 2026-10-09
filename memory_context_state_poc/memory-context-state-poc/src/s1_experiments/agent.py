"""The remediation agent: one structured-output call through F2's model gateway. The same prompt for both arms."""

from __future__ import annotations

import json
from typing import Any

from agent_platform.models.types import ModelUnavailable


async def decide(gateway, messages: list[dict[str, str]], schema: dict[str, Any], caller: str) -> dict[str, Any]:
    try:
        res = await gateway.chat("reasoning", messages, schema=schema, workflow_id="wf-s1-5208", agent=caller)
    except ModelUnavailable as exc:
        return {"action": "error", "rationale": str(exc)[:200], "cited_ids": [], "input_tokens": 0, "output_tokens": 0, "latency_ms": 0}
    try:
        out = json.loads(res.content)
        action, rationale, cited = str(out.get("action", "invalid")), str(out.get("rationale", "")), [str(x) for x in out.get("cited_ids") or []]
    except (json.JSONDecodeError, AttributeError):
        action, rationale, cited = "invalid", res.content[:300], []
    return {"action": action, "rationale": rationale, "cited_ids": cited, "model": res.model,
            "input_tokens": res.input_tokens, "output_tokens": res.output_tokens, "latency_ms": round(res.latency_ms, 1)}
