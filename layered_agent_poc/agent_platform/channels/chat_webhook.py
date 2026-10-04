"""Chat channel: Slack-shaped webhook payloads (simulated; no Slack app). Renders replies as blocks.

    POST /v1/chat/events    {"type": "event_callback", "event": {"type": "app_mention", "user": "U04ALICE", "text": "..."}}
    POST /v1/chat/actions   {"type": "block_actions", "user": {"id": "U04ALICE"}, "actions": [{"action_id": "approve", "value": "wf-..."}]}
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from agent_platform.contracts import ApprovalDecision, StartInvestigation
from agent_platform.identity.principals import resolve_chat_user
from agent_platform.service import Forbidden

router = APIRouter()
INCIDENT = re.compile(r"\bINC-\d+\b")


def blocks(view: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"type": "section", "text": {"type": "mrkdwn",
                                  "text": f"*{view['incident_id']}* · `{view['workflow_id']}` · *{view['status']}*"}}]
    a = view.get("approval")
    if a and a["status"] == "PENDING":
        out.append({"type": "section", "text": {"type": "mrkdwn",
                    "text": f"Approval needed ({a['required_role']}): `{a['tool_id']}` {a['arguments']}"}})
        out.append({"type": "actions", "elements": [
            {"type": "button", "action_id": "approve", "value": view["workflow_id"], "style": "primary", "text": {"type": "plain_text", "text": "Approve"}},
            {"type": "button", "action_id": "reject", "value": view["workflow_id"], "style": "danger", "text": {"type": "plain_text", "text": "Reject"}}]})
    return out


@router.post("/events")
async def events(request: Request) -> dict[str, Any]:
    body = await request.json()
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}
    event = body.get("event", {})
    match = INCIDENT.search(event.get("text", ""))
    if event.get("type") != "app_mention" or not match:
        return {"response_type": "ephemeral", "text": "Mention me with an incident id, e.g. INC-4917."}
    try:
        user = resolve_chat_user(event.get("user", ""))
    except Forbidden as exc:
        raise HTTPException(403, str(exc)) from exc
    app = request.app
    svc = app.state.svc
    text = INCIDENT.sub("", re.sub(r"<@[^>]+>", "", event["text"])).strip(" :,-") or "Investigate this incident."
    wf_id, run = svc.submit(StartInvestigation(incident_id=match.group(0), request=text, user_id=user.user_id,
                                               channel="chat", session_id=f"chat-{event.get('channel', 'dm')}"))
    from agent_platform.channels.rest import background

    background(app, run)
    return {"response_type": "in_channel", "blocks": blocks(svc.workflow(wf_id))}


@router.post("/actions")
async def actions(request: Request) -> dict[str, Any]:
    body = await request.json()
    action = (body.get("actions") or [{}])[0]
    if action.get("action_id") not in ("approve", "reject"):
        raise HTTPException(400, "unsupported action")
    try:
        user = resolve_chat_user(body.get("user", {}).get("id", ""))
        cmd = ApprovalDecision(workflow_id=action["value"], approver_id=user.user_id, approve=action["action_id"] == "approve")
        svc = request.app.state.svc
        svc.check_approver(cmd)
    except Forbidden as exc:
        return {"response_type": "ephemeral", "text": f"Not allowed: {exc}"}
    except ValueError as exc:
        return {"response_type": "ephemeral", "text": str(exc)}
    from agent_platform.channels.rest import background

    background(request.app, svc.decide_approval(cmd))
    return {"response_type": "in_channel", "text": f"{user.display_name} {'approved' if cmd.approve else 'rejected'} {cmd.workflow_id}."}
