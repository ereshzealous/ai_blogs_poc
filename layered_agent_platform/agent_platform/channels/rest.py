"""REST channel (FastAPI). Long-running work runs in the background; clients poll the workflow.

    POST /v1/incidents/{incident_id}/investigations   X-User-Id: alice   {"request": "..."}   -> 202
    GET  /v1/workflows/{id}          GET /v1/workflows          GET /v1/workflows/{id}/trace
    POST /v1/workflows/{id}/approvals X-User-Id: alice   {"approve": true}                  -> 202
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from agent_platform.channels.chat_webhook import router as chat_router
from agent_platform.contracts import ApprovalDecision, StartInvestigation
from agent_platform.service import Forbidden, PlatformService


class InvestigationBody(BaseModel):
    request: str
    session_id: str | None = None


class ApprovalBody(BaseModel):
    approve: bool
    comment: str = ""


def background(app: FastAPI, coro: Any) -> None:
    task = asyncio.create_task(coro)
    app.state.tasks.add(task)
    task.add_done_callback(app.state.tasks.discard)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with PlatformService.open() as svc:
            app.state.svc = svc
            app.state.tasks = set()
            if os.environ.get("LAP_RECOVER_ON_START", "1") == "1":
                background(app, svc.recover())  # a restarted worker picks up what a dead one left RUNNING
            yield

    app = FastAPI(title="Layered agent platform", version="0.1.0", lifespan=lifespan)

    def svc() -> PlatformService:
        return app.state.svc

    @app.post("/v1/incidents/{incident_id}/investigations", status_code=202)
    async def start(incident_id: str, body: InvestigationBody, x_user_id: str = Header(...)) -> dict[str, Any]:
        try:
            wf_id, run = svc().submit(StartInvestigation(incident_id=incident_id, request=body.request, user_id=x_user_id,
                                                         channel="rest", session_id=body.session_id))
        except Forbidden as exc:
            raise HTTPException(403, str(exc)) from exc
        background(app, run)
        return {"workflow_id": wf_id, "status": "RUNNING", "links": {"self": f"/v1/workflows/{wf_id}"}}

    @app.get("/v1/workflows")
    async def list_workflows(status: str | None = None) -> list[dict[str, Any]]:
        return svc().workflows(status)

    @app.get("/v1/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str) -> dict[str, Any]:
        try:
            return svc().workflow(workflow_id)
        except KeyError as exc:
            raise HTTPException(404, f"unknown workflow {workflow_id}") from exc

    @app.post("/v1/workflows/{workflow_id}/approvals", status_code=202)
    async def approve(workflow_id: str, body: ApprovalBody, x_user_id: str = Header(...)) -> dict[str, Any]:
        cmd = ApprovalDecision(workflow_id=workflow_id, approver_id=x_user_id, approve=body.approve, comment=body.comment)
        try:
            svc().check_approver(cmd)
        except Forbidden as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        background(app, svc().decide_approval(cmd))
        return {"workflow_id": workflow_id, "decision": "APPROVED" if body.approve else "REJECTED"}

    @app.post("/v1/workflows/{workflow_id}/resume", status_code=202)
    async def resume(workflow_id: str) -> dict[str, Any]:
        background(app, svc().resume(workflow_id))
        return {"workflow_id": workflow_id}

    @app.get("/v1/workflows/{workflow_id}/events")
    async def events(workflow_id: str) -> list[dict[str, Any]]:
        return svc().events(workflow_id)

    @app.get("/v1/workflows/{workflow_id}/trace")
    async def trace(workflow_id: str) -> list[dict[str, Any]]:
        return svc().trace(workflow_id)

    @app.get("/v1/workflows/{workflow_id}/evaluation")
    async def evaluation(workflow_id: str) -> dict[str, Any]:
        return svc().evaluate(workflow_id)

    @app.get("/healthz")
    async def health() -> dict[str, Any]:
        return {"ok": True, "pid": os.getpid(), "tools": len(svc().pool.tools)}

    app.include_router(chat_router, prefix="/v1/chat")
    return app


app = None  # uvicorn factory: `uvicorn agent_platform.channels.rest:create_app --factory`
