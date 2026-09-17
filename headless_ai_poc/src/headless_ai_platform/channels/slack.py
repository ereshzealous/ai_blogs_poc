"""Slack-shaped channel (simulated payloads; no Slack app is installed).

    POST /slack/events    Events API envelope with an app_mention
    POST /slack/actions   block_actions interaction (a button press)

Slack expects an answer within 3 seconds and retries events, so the adapter replies at once, uses the event id as the
idempotency key and delivers later updates into the thread through `reply_to`.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Request

from headless_ai_platform.channels import CAPABILITY, gateway
from headless_ai_platform.contracts import CapabilityError, ErrorCode
from headless_ai_platform.renderers import slack

router = APIRouter()
CHANNEL = "slack"
INCIDENT = re.compile(r"\bINC-\d+\b")


def _thread(event: dict[str, Any]) -> str:
    return f"{event.get('team', 'T0')}/{event.get('channel', 'D0')}/{event.get('thread_ts') or event.get('ts', '0')}"


def _ephemeral(text: str) -> dict[str, Any]:
    return {"response_type": "ephemeral", "text": text}


def _explain(exc: CapabilityError) -> str:
    return {ErrorCode.FORBIDDEN: f"You can't do that: {exc.message}",
            ErrorCode.UNKNOWN_IDENTITY: "Your Slack account isn't linked to a company identity yet.",
            ErrorCode.CONFLICT: f"That button is out of date: {exc.message}"}.get(exc.code, exc.message)


@router.post("/slack/events")
async def events(request: Request) -> dict[str, Any]:
    body = await request.json()
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}
    event = body.get("event", {})
    match = INCIDENT.search(event.get("text", ""))
    if event.get("type") != "app_mention" or not match:
        return _ephemeral("Mention me with an incident id, for example `@ops investigate INC-4917`.")
    text = INCIDENT.sub("", re.sub(r"<@[^>]+>", "", event["text"])).strip(" :,-")
    reply_to = request.app.state.channel_urls.get(CHANNEL)
    try:
        resp = await gateway(request).handle({
            "capability": CAPABILITY, "operation": "start",
            "actor": {"channel": CHANNEL, "channel_subject": event.get("user", "")},
            "input": {"incident_id": match.group(0), **({"request": text} if len(text) > 12 else {})},
            "channel_context": {"thread_ref": _thread(event), "reply_to": reply_to,
                                "idempotency_key": body.get("event_id")}})
    except CapabilityError as exc:
        return _ephemeral(_explain(exc))
    return {"response_type": "in_channel", "thread_ts": event.get("thread_ts") or event.get("ts"), **slack.render(resp)}


@router.post("/slack/actions")
async def actions(request: Request) -> dict[str, Any]:
    body = await request.json()
    action = (body.get("actions") or [{}])[0]
    workflow_id, _, binding = str(action.get("value", "")).partition("|")
    container = body.get("container", {})
    thread = f"{body.get('team', {}).get('id', 'T0')}/{container.get('channel_id', 'D0')}/{container.get('thread_ts', '0')}"
    try:
        resp = await gateway(request).handle({
            "capability": CAPABILITY, "operation": "act", "workflow_id": workflow_id,
            "action_id": action.get("action_id"), "binding": binding or None,
            "actor": {"channel": CHANNEL, "channel_subject": body.get("user", {}).get("id", "")},
            "channel_context": {"thread_ref": thread, "reply_to": request.app.state.channel_urls.get(CHANNEL)}})
    except CapabilityError as exc:
        return _ephemeral(_explain(exc))
    return {"response_type": "in_channel", "replace_original": True, **slack.render(resp)}


async def send(address: str, thread_ref: str | None, response: dict[str, Any]) -> None:
    """Post a thread reply (chat.postMessage-shaped) to the workspace URL the adapter was configured with."""
    import httpx

    from headless_ai_platform.contracts import CapabilityResponse

    message = slack.render(CapabilityResponse.model_validate(response))
    channel, _, ts = (thread_ref or "T0/D0/0").partition("/")[2].partition("/")
    async with httpx.AsyncClient(timeout=5) as client:
        (await client.post(address, json={"channel": channel, "thread_ts": ts, **message})).raise_for_status()
