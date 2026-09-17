"""Slack incident bot. Owns everything it needs to answer an @mention and act on a button press."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

log = logging.getLogger("slack-assistant")

# ------------------------------------------------------------------ prompt (Slack flavour: short, emoji-free)
SYSTEM_PROMPT = """You are the on-call incident assistant in Slack.
Investigate the incident with the tools, then answer in at most five short lines.
Recommend exactly one remediation. For services released by the release pipeline, recommend
source_control.rollback_release to the previous version. Never change production yourself."""
PROMPT_VERSION = "slack-v3"

# ------------------------------------------------------------------ model
MODEL = "gpt-oss:20b"
OLLAMA = "http://localhost:11434"
MODEL_OPTIONS = {"temperature": 0, "num_ctx": 16384}

# ------------------------------------------------------------------ tools
TOOLS = ["itsm.get_incident", "source_control.list_deployments", "observability.query_latency",
         "database.get_connection_pool_stats", "source_control.rollback_release", "itsm.update_incident"]
HIGH_RISK = {"source_control.rollback_release", "kubernetes.rollback_deployment"}


def call_tool(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    resp = httpx.post(f"http://localhost:8700/tools/{tool}", json=args, timeout=8)
    resp.raise_for_status()
    return resp.json()


# ------------------------------------------------------------------ identity and policy
SLACK_GROUPS = {"U04ALICE": ["sre", "incident-commander"], "U04BOB": ["developer"]}  # synced from Slack user groups


def roles_of(slack_user: str) -> list[str]:
    return SLACK_GROUPS.get(slack_user, [])


def approval_role(tool: str, environment: str) -> str | None:
    """Production rollbacks need an incident commander."""
    if tool in HIGH_RISK and environment == "production":
        return "incident-commander"
    return None


def may_approve(slack_user: str, tool: str, environment: str) -> bool:
    role = approval_role(tool, environment)
    return role is None or role in roles_of(slack_user)


# ------------------------------------------------------------------ memory (per Slack thread)
THREADS: dict[str, list[dict[str, str]]] = {}
PENDING: dict[str, dict[str, Any]] = {}  # thread_ts -> proposed action waiting for a button


# ------------------------------------------------------------------ workflow
def investigate(thread_ts: str, user: str, text: str) -> dict[str, Any]:
    history = THREADS.setdefault(thread_ts, [{"role": "system", "content": SYSTEM_PROMPT}])
    history.append({"role": "user", "content": text})
    started = time.monotonic()
    for _ in range(8):
        reply = httpx.post(f"{OLLAMA}/api/chat", timeout=240, json={
            "model": MODEL, "messages": history, "stream": False, "options": MODEL_OPTIONS,
            "tools": [{"type": "function", "function": {"name": t, "parameters": {"type": "object"}}} for t in TOOLS]}).json()
        msg = reply["message"]
        history.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            break
        for c in calls:
            name, args = c["function"]["name"], c["function"].get("arguments", {})
            if name in HIGH_RISK:
                PENDING[thread_ts] = {"tool": name, "args": args, "requested_by": user}
                history.append({"role": "tool", "content": "queued for approval"})
                continue
            history.append({"role": "tool", "content": json.dumps(call_tool(name, args))[:2000]})
    log.info("slack investigate thread=%s user=%s ms=%d prompt=%s", thread_ts, user,
             (time.monotonic() - started) * 1000, PROMPT_VERSION)
    return {"text": history[-1].get("content", ""), "pending": PENDING.get(thread_ts)}


def on_button(thread_ts: str, user: str, approve: bool) -> str:
    action = PENDING.get(thread_ts)
    if action is None:
        return "Nothing is waiting for approval in this thread."
    env = action["args"].get("environment", "production")
    if not may_approve(user, action["tool"], env):
        return "Only an incident commander can approve production rollbacks."
    PENDING.pop(thread_ts)
    if not approve:
        return "Rejected."
    result = call_tool(action["tool"], action["args"])
    call_tool("itsm.update_incident", {"incident_id": action["args"].get("incident_id"), "status": "mitigated",
                                       "note": f"Rolled back via Slack by {user}"})
    log.info("slack approved thread=%s user=%s tool=%s", thread_ts, user, action["tool"])
    return f"Done: {result.get('status', 'ok')}"


# ------------------------------------------------------------------ rendering
def blocks(answer: dict[str, Any]) -> list[dict[str, Any]]:
    out = [{"type": "section", "text": {"type": "mrkdwn", "text": answer["text"]}}]
    if answer.get("pending"):
        out.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "Needs an incident commander."}]})
        out.append({"type": "actions", "elements": [
            {"type": "button", "action_id": "approve", "text": {"type": "plain_text", "text": "Approve"}},
            {"type": "button", "action_id": "reject", "text": {"type": "plain_text", "text": "Reject"}}]})
    return out
