"""Web console assistant. Owns everything behind the console's chat panel and its approval modal."""

from __future__ import annotations

import json
import logging
import time
from html import escape
from typing import Any

import httpx

log = logging.getLogger("web-assistant")

# ------------------------------------------------------------------ prompt (web flavour: rich, markdown tables)
SYSTEM_PROMPT = """You are the incident assistant in the operations console.
Investigate the incident using the tools. Answer with a short summary, an evidence table in markdown and
one recommended remediation. For services released by the release pipeline, recommend
source_control.rollback_release to the previous version. Do not change production without approval."""
PROMPT_VERSION = "web-v4"

# ------------------------------------------------------------------ model
MODEL = "gpt-oss:20b"
OLLAMA = "http://localhost:11434"
MODEL_OPTIONS = {"temperature": 0, "num_ctx": 32768}

# ------------------------------------------------------------------ tools
TOOLS = ["itsm.get_incident", "source_control.list_deployments", "source_control.get_diff",
         "observability.query_latency", "observability.query_errors", "database.get_connection_pool_stats",
         "source_control.rollback_release", "itsm.update_incident"]
HIGH_RISK = {"source_control.rollback_release", "kubernetes.rollback_deployment"}


def call_tool(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    resp = httpx.post(f"http://localhost:8700/tools/{tool}", json=args, timeout=10)
    resp.raise_for_status()
    return resp.json()


# ------------------------------------------------------------------ identity and policy
def roles_of(oidc_claims: dict[str, Any]) -> list[str]:
    return list(oidc_claims.get("groups", []))  # e.g. ["sre", "incident-commander"] from the IdP


def approval_role(tool: str, environment: str) -> str | None:
    """Production rollbacks need an incident commander."""
    if tool in HIGH_RISK and environment == "production":
        return "incident-commander"
    return None


def may_approve(oidc_claims: dict[str, Any], tool: str, environment: str) -> bool:
    role = approval_role(tool, environment)
    return role is None or role in roles_of(oidc_claims)


# ------------------------------------------------------------------ memory (per browser session)
SESSIONS: dict[str, dict[str, Any]] = {}


# ------------------------------------------------------------------ workflow
def investigate(session_id: str, claims: dict[str, Any], incident_id: str, text: str) -> dict[str, Any]:
    s = SESSIONS.setdefault(session_id, {"messages": [{"role": "system", "content": SYSTEM_PROMPT}], "pending": None})
    s["messages"].append({"role": "user", "content": f"{incident_id}: {text}"})
    started = time.monotonic()
    for _ in range(10):
        reply = httpx.post(f"{OLLAMA}/api/chat", timeout=240, json={
            "model": MODEL, "messages": s["messages"], "stream": False, "options": MODEL_OPTIONS,
            "tools": [{"type": "function", "function": {"name": t, "parameters": {"type": "object"}}} for t in TOOLS]}).json()
        msg = reply["message"]
        s["messages"].append(msg)
        if not msg.get("tool_calls"):
            break
        for c in msg["tool_calls"]:
            name, args = c["function"]["name"], c["function"].get("arguments", {})
            if name in HIGH_RISK:
                s["pending"] = {"tool": name, "args": {**args, "incident_id": incident_id}, "by": claims.get("sub")}
                s["messages"].append({"role": "tool", "content": "awaiting approval in the console"})
                continue
            s["messages"].append({"role": "tool", "content": json.dumps(call_tool(name, args))[:4000]})
    log.info("web investigate session=%s sub=%s ms=%d prompt=%s", session_id, claims.get("sub"),
             (time.monotonic() - started) * 1000, PROMPT_VERSION)
    return {"markdown": s["messages"][-1].get("content", ""), "pending": s["pending"]}


def approve(session_id: str, claims: dict[str, Any], approve_it: bool) -> dict[str, Any]:
    s = SESSIONS.get(session_id) or {}
    action = s.get("pending")
    if not action:
        return {"ok": False, "error": "nothing pending"}
    if not may_approve(claims, action["tool"], action["args"].get("environment", "production")):
        return {"ok": False, "error": "incident-commander role required"}
    s["pending"] = None
    if not approve_it:
        return {"ok": True, "status": "rejected"}
    result = call_tool(action["tool"], action["args"])
    check = call_tool("observability.query_latency", {"service": action["args"].get("service"),
                                                      "environment": action["args"].get("environment")})
    call_tool("itsm.update_incident", {"incident_id": action["args"]["incident_id"], "status": "mitigated",
                                       "note": f"Rolled back from the console by {claims.get('sub')}; p95 {check.get('p95_ms')} ms"})
    log.info("web approved session=%s sub=%s tool=%s", session_id, claims.get("sub"), action["tool"])
    return {"ok": True, "status": "completed", "result": result, "p95_ms": check.get("p95_ms")}


# ------------------------------------------------------------------ rendering
def approval_modal(pending: dict[str, Any]) -> str:
    return (f"<dialog open><h3>Approve {escape(pending['tool'])}?</h3>"
            f"<p>Target: {escape(str(pending['args'].get('target_version')))}</p>"
            "<p>Only an incident commander can approve this change.</p>"
            "<button value='approve'>Approve</button><button value='reject'>Reject</button></dialog>")
