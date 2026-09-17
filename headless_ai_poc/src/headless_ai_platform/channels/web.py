"""Web console channel: a small static page plus a JSON API made for it.

    GET  /console                                  the page (static HTML/JS, no build step)
    GET  /web/api/me                               who the signed-in subject resolves to
    GET  /web/api/workflows/{workflow_id}          {"response": CapabilityResponse, "card": "<article>..."}
    POST /web/api/workflows/{workflow_id}/actions  {"action_id": "...", "binding": "..."}

Sign-in is simulated: the page sends the OIDC subject it was "issued" in `X-OIDC-Subject`. A real deployment would
validate an ID token here; the boundary above would not change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from headless_ai_platform.channels import CAPABILITY, gateway, http_error
from headless_ai_platform.contracts import Actor, CapabilityError, ErrorCode
from headless_ai_platform.renderers import web

router = APIRouter()
CHANNEL = "web"
STATIC = Path(__file__).resolve().parent.parent / "static"


class ActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str
    binding: str | None = None
    comment: str = ""


def _page(resp: Any) -> dict[str, Any]:
    return {"response": resp.model_dump(mode="json"), "card": web.render(resp)}


@router.get("/console")
async def console() -> FileResponse:
    return FileResponse(STATIC / "console.html")


@router.get("/console/{name}")
async def asset(name: str) -> FileResponse:
    path = (STATIC / name).resolve()
    if path.parent != STATIC or not path.exists():
        raise http_error(CapabilityError(ErrorCode.NOT_FOUND, f"no asset {name}"))
    return FileResponse(path)


@router.get("/web/api/me")
async def me(request: Request, x_oidc_subject: str = Header(...)) -> dict[str, Any]:
    try:
        p = gateway(request).principal_for(Actor(channel=CHANNEL, channel_subject=x_oidc_subject))
    except CapabilityError as exc:
        raise http_error(exc) from exc
    return {"principal_id": p.principal_id, "display_name": p.display_name, "roles": list(p.roles)}


@router.get("/web/api/workflows/{workflow_id}")
async def get(workflow_id: str, request: Request, x_oidc_subject: str = Header(...)) -> dict[str, Any]:
    try:
        resp = await gateway(request).handle({"capability": CAPABILITY, "operation": "get", "workflow_id": workflow_id,
                                              "actor": {"channel": CHANNEL, "channel_subject": x_oidc_subject},
                                              "channel_context": {"thread_ref": f"tab:{workflow_id}"}})
    except CapabilityError as exc:
        raise http_error(exc) from exc
    return _page(resp)


@router.post("/web/api/workflows/{workflow_id}/actions", status_code=202)
async def act(workflow_id: str, body: ActionBody, request: Request, x_oidc_subject: str = Header(...)) -> dict[str, Any]:
    try:
        resp = await gateway(request).handle({"capability": CAPABILITY, "operation": "act", "workflow_id": workflow_id,
                                              "action_id": body.action_id, "binding": body.binding,
                                              "input": {"comment": body.comment} if body.comment else {},
                                              "actor": {"channel": CHANNEL, "channel_subject": x_oidc_subject},
                                              "channel_context": {"thread_ref": f"tab:{workflow_id}"}})
    except CapabilityError as exc:
        raise http_error(exc) from exc
    return _page(resp)
