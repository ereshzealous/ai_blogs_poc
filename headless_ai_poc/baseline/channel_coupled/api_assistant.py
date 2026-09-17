"""Incident assistant API for integrations (ITSM, portals). Owns its own agent loop, policy and state."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import httpx

log = logging.getLogger("api-assistant")

# ------------------------------------------------------------------ prompt (API flavour: JSON output)
SYSTEM_PROMPT = """You are an incident remediation service. Investigate with the tools and return JSON:
{"root_cause": str, "recommended_tool": str, "arguments": object, "confidence": "low|medium|high"}.
For services released by the release pipeline, recommend source_control.rollback_release
to the previous version."""
PROMPT_VERSION = "api-v3"

# ------------------------------------------------------------------ model
MODEL = "qwen3:8b"  # the API team picked the faster model
OLLAMA = "http://localhost:11434"
MODEL_OPTIONS = {"temperature": 0, "num_ctx": 32768}

# ------------------------------------------------------------------ tools
TOOLS = ["itsm.get_incident", "source_control.list_deployments", "observability.query_latency",
         "database.get_connection_pool_stats"]
WRITE_TOOLS = {"source_control.rollback_release": "HIGH", "kubernetes.rollback_deployment": "HIGH",
               "itsm.update_incident": "LOW"}


def call_tool(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    resp = httpx.post(f"http://localhost:8700/tools/{tool}", json=args, timeout=8)
    resp.raise_for_status()
    return resp.json()


# ------------------------------------------------------------------ identity and policy
TOKEN_SCOPES = {"api|alice": ["incidents:write", "role:incident-commander"], "api|bob": ["incidents:read"]}


def roles_of(subject: str) -> list[str]:
    return [s.removeprefix("role:") for s in TOKEN_SCOPES.get(subject, []) if s.startswith("role:")]


def approval_role(tool: str, environment: str) -> str | None:
    """High-risk production writes need an incident commander."""
    if WRITE_TOOLS.get(tool) == "HIGH" and environment == "production":
        return "incident-commander"
    return None


def may_approve(subject: str, tool: str, environment: str) -> bool:
    role = approval_role(tool, environment)
    return role is None or role in roles_of(subject)


# ------------------------------------------------------------------ memory / job state (process-local)
JOBS: dict[str, dict[str, Any]] = {}


# ------------------------------------------------------------------ workflow
def create_job(subject: str, incident_id: str) -> dict[str, Any]:
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": incident_id}]
    started = time.monotonic()
    for _ in range(8):
        reply = httpx.post(f"{OLLAMA}/api/chat", timeout=240, json={
            "model": MODEL, "messages": messages, "stream": False, "format": "json", "options": MODEL_OPTIONS,
            "tools": [{"type": "function", "function": {"name": t, "parameters": {"type": "object"}}} for t in TOOLS]}).json()
        msg = reply["message"]
        messages.append(msg)
        if not msg.get("tool_calls"):
            break
        for c in msg["tool_calls"]:
            messages.append({"role": "tool", "content": json.dumps(call_tool(c["function"]["name"],
                                                                                 c["function"].get("arguments", {})))[:3000]})
    plan = json.loads(messages[-1].get("content") or "{}")
    env = plan.get("arguments", {}).get("environment", "production")
    role = approval_role(plan.get("recommended_tool", ""), env)
    JOBS[job_id] = {"incident_id": incident_id, "plan": plan, "status": "WAITING_APPROVAL" if role else "READY",
                    "requested_by": subject}
    log.info("api job=%s sub=%s ms=%d prompt=%s", job_id, subject, (time.monotonic() - started) * 1000, PROMPT_VERSION)
    return {"job_id": job_id, **JOBS[job_id], "approval_role": role}


def approve_job(subject: str, job_id: str) -> dict[str, Any]:
    job = JOBS.get(job_id)
    if job is None:
        return {"status": 404}
    plan = job["plan"]
    env = plan.get("arguments", {}).get("environment", "production")
    if not may_approve(subject, plan.get("recommended_tool", ""), env):
        return {"status": 403, "error": "forbidden"}
    call_tool(plan["recommended_tool"], plan.get("arguments", {}))
    call_tool("itsm.update_incident", {"incident_id": job["incident_id"], "status": "mitigated",
                                       "note": f"Remediated via API by {subject}"})
    job["status"] = "COMPLETED"
    log.info("api approved job=%s sub=%s", job_id, subject)
    return {"status": 200, "job": job}


# ------------------------------------------------------------------ rendering
def to_json(job: dict[str, Any]) -> dict[str, Any]:
    return {"job_id": job.get("job_id"), "status": job["status"], "plan": job["plan"]}
