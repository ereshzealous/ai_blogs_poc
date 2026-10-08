"""A deterministic stand-in for the model: used by tests (no Ollama) and by E7 (to isolate the A2A boundary's cost).

It answers by role, from the conversation so far: with tools offered and no tool result yet, it makes one read call;
asked for a schema, it returns a fixed valid instance.  The coordinator script delegates evidence -> diagnosis ->
finish(escalated).  Token counts are a fixed function of message length (len // 4).  Nothing here reasons.
"""

from __future__ import annotations

import json
import re
from typing import Any

from coord.models import ModelReply

CANNED: dict[str, dict[str, Any]] = {
    "IncidentReport": {"root_cause": {"category": "undetermined", "summary": "scripted", "affected_service": "", "evidence": [], "confidence": "low"},
                       "alternatives": [], "decision": "escalate", "action_taken": None, "rationale": "scripted"},
    "Diagnosis": {"root_cause": {"category": "undetermined", "summary": "scripted diagnosis", "affected_service": "", "evidence": ["ev-1"],
                                 "confidence": "low"}, "alternatives": [], "recommendation": "escalate", "evidence_request": []},
    "RemediationProposal": {"decision": "escalate", "tool": "none", "args": {}, "rationale": "scripted", "risk": "low"},
    "RemediationResult": {"decision": "escalate", "tool": "none", "args": {}, "executed": False, "result_summary": "scripted", "rationale": "scripted"},
    "ReviewVerdict": {"verdict": "approve", "reasons": ["scripted"], "concerns": [], "evidence_request": []},
    "EvidenceArtifact": {"items": [{"ref": "ev-1", "finding": "scripted finding"}], "summary": "scripted evidence", "suspected_causes": []},
}


def _service(messages: list[dict[str, Any]]) -> tuple[str, str]:
    text = " ".join(str(m.get("content", "")) for m in messages if m.get("role") == "user")
    m = re.search(r"on ([a-z0-9-]+) \((production|staging)\)", text)
    return (m.group(1), m.group(2)) if m else ("checkout-api", "production")


class ScriptedProvider:
    model = "scripted-v1"

    def __init__(self, overrides: dict[str, dict[str, Any]] | None = None):
        self.canned = dict(CANNED, **(overrides or {}))

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, schema: dict[str, Any] | None,
                   seed: int, caller: str) -> ModelReply:
        prompt_tokens = len(json.dumps(messages)) // 4
        if schema is not None:
            body = self.canned.get(schema.get("title", ""), {})
            content = json.dumps(body)
            return ModelReply(content=content, model=self.model, prompt_tokens=prompt_tokens, completion_tokens=len(content) // 4)
        names = [t["function"]["name"] for t in tools or []]
        tool_results = sum(1 for m in messages if m.get("role") == "tool")
        if "delegate" in names:  # the coordinator
            script = [("delegate", {"agent": "evidence", "objective": "Gather evidence for the incident.", "input_artifact_ids": [], "authorize_execution": False}),
                      ("delegate", {"agent": "diagnosis", "objective": "Diagnose the incident.", "input_artifact_ids": [], "authorize_execution": False}),
                      ("finish", {"outcome": "escalated", "root_cause_category": "undetermined", "affected_service": "", "summary": "scripted"})]
            name, args = script[min(tool_results, len(script) - 1)]
            if name == "delegate" and tool_results == 1:
                ids = re.findall(r'"artifact_id":\s*"([^"]+)"', " ".join(str(m.get("content", "")) for m in messages if m.get("role") == "tool"))
                args = dict(args, input_artifact_ids=ids[:1])
            call = {"name": name, "arguments": args}
            return ModelReply(content="", tool_calls=[call], model=self.model, prompt_tokens=prompt_tokens, completion_tokens=20)
        if names and tool_results == 0 and "query_metrics" in names:
            svc, env = _service(messages)
            call = {"name": "query_metrics", "arguments": {"service": svc, "environment": env, "metric": "latency_p95_ms"}}
            return ModelReply(content="", tool_calls=[call], model=self.model, prompt_tokens=prompt_tokens, completion_tokens=15)
        return ModelReply(content="done", model=self.model, prompt_tokens=prompt_tokens, completion_tokens=2)
