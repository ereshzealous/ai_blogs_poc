"""REST channel for the monolith. It had to copy the session handling, the approval rule and the formatting,
because they live inside (or next to) the agent.

    uvicorn monolith.api:app --port 8090
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, Header
from pydantic import BaseModel

from monolith.incident_agent import IncidentAgent

app = FastAPI(title="incident agent (monolith)")
AGENTS: dict[str, IncidentAgent] = {}  # one agent (and its memory) per user, in this process only
PENDING: dict[str, dict[str, Any]] = {}  # approvals we are waiting for, in this process only


class Ask(BaseModel):
    request: str


async def _api_approver_for(user: str):
    async def approver(tool: str, args: dict[str, Any]) -> bool:
        # The HTTP caller cannot answer a prompt, so we park the question and wait (up to 10 minutes).
        event = asyncio.Event()
        PENDING[user] = {"tool": tool, "args": args, "event": event, "approved": False}
        try:
            await asyncio.wait_for(event.wait(), timeout=600)
        except TimeoutError:
            return False
        return PENDING.pop(user)["approved"]
    return approver


@app.post("/investigate")
async def investigate(body: Ask, x_user_id: str = Header(...)) -> dict[str, Any]:
    agent = AGENTS.get(x_user_id)
    if agent is None:
        agent = IncidentAgent(approver=await _api_approver_for(x_user_id), user=x_user_id)
        await agent.connect()
        AGENTS[x_user_id] = agent
    answer = await agent.run(body.request)
    return {"answer": answer, "tokens": agent.token_count, "format": "markdown"}


@app.post("/approve")
async def approve(x_user_id: str = Header(...), yes: bool = True) -> dict[str, Any]:
    pending = PENDING.get(x_user_id)
    if not pending:
        return {"error": "nothing to approve"}
    pending["approved"] = yes
    pending["event"].set()
    return {"ok": True}
