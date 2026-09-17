"""REST channel: the contract over HTTP, for services and integrations (ITSM, portals, scripts).

    POST /v1/capabilities/{capability}/workflows                 X-Subject: api|alice   {"input": {...}}
    GET  /v1/capabilities/{capability}/workflows/{workflow_id}    X-Subject: api|alice
    POST /v1/capabilities/{capability}/workflows/{workflow_id}/actions   {"action_id": "...", "binding": "..."}
    POST /v1/capability-requests                                  a full CapabilityRequest (channel "rest" only)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from headless_ai_platform.channels import gateway, http_error
from headless_ai_platform.contracts import CapabilityError
from headless_ai_platform.renderers import api

router = APIRouter()
CHANNEL = "rest"


class StartBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: dict[str, Any]
    reply_to: str | None = None
    idempotency_key: str | None = None


class ActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str
    binding: str | None = None
    input: dict[str, Any] = {}


async def _call(request: Request, payload: dict[str, Any], created: bool = False) -> JSONResponse:
    try:
        resp = await gateway(request).handle(payload)
    except CapabilityError as exc:
        raise http_error(exc) from exc
    return JSONResponse(api.render(resp), status_code=api.status_code(resp, created))


@router.post("/v1/capabilities/{capability}/workflows")
async def start(capability: str, body: StartBody, request: Request, x_subject: str = Header(...)) -> JSONResponse:
    return await _call(request, {"capability": capability, "operation": "start",
                                 "actor": {"channel": CHANNEL, "channel_subject": x_subject}, "input": body.input,
                                 "channel_context": {"reply_to": body.reply_to, "idempotency_key": body.idempotency_key}},
                       created=True)


@router.get("/v1/capabilities/{capability}/workflows/{workflow_id}")
async def get(capability: str, workflow_id: str, request: Request, x_subject: str = Header(...)) -> JSONResponse:
    return await _call(request, {"capability": capability, "operation": "get", "workflow_id": workflow_id,
                                 "actor": {"channel": CHANNEL, "channel_subject": x_subject}})


@router.post("/v1/capabilities/{capability}/workflows/{workflow_id}/actions")
async def act(capability: str, workflow_id: str, body: ActionBody, request: Request,
              x_subject: str = Header(...)) -> JSONResponse:
    return await _call(request, {"capability": capability, "operation": "act", "workflow_id": workflow_id,
                                 "action_id": body.action_id, "binding": body.binding, "input": body.input,
                                 "actor": {"channel": CHANNEL, "channel_subject": x_subject}}, created=True)


@router.post("/v1/capability-requests")
async def raw(request: Request, x_subject: str = Header(...)) -> JSONResponse:
    """The contract as-is. The actor is still taken from the caller's credential, never from the body."""
    payload = await request.json()
    if isinstance(payload, dict):
        payload["actor"] = {"channel": CHANNEL, "channel_subject": x_subject}
    return await _call(request, payload, created=isinstance(payload, dict) and payload.get("operation") != "get")


async def send(address: str, thread_ref: str | None, response: dict[str, Any]) -> None:
    """Webhook delivery for API consumers that asked for one (`reply_to`)."""
    import httpx

    async with httpx.AsyncClient(timeout=5) as client:
        (await client.post(address, json=response)).raise_for_status()
