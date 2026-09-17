"""One FastAPI app that hosts any set of channel adapters over the same gateway.

    uvicorn --factory headless_ai_platform.server:create_app          all channels
    HAI_CHANNELS=slack,rest  HAI_SLACK_URL=http://...   (per-process channel sets, as in experiment H2/H7)

Every process opens the same layered platform (shared SQLite state), so a workflow started through one process can be
read and approved through another.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from headless_ai_platform.channels import event, rest, slack, web
from headless_ai_platform.runtime import open_gateway

ROUTERS = {"slack": slack.router, "web": web.router, "rest": rest.router, "event": event.router}
SENDERS = {"slack": slack.send, "rest": rest.send}


def create_app(channels: list[str] | None = None, gateway_factory: Any = None) -> FastAPI:
    hosted = channels or [c for c in os.environ.get("HAI_CHANNELS", ",".join(ROUTERS)).split(",") if c]
    urls = {c: os.environ[f"HAI_{c.upper()}_URL"] for c in hosted if os.environ.get(f"HAI_{c.upper()}_URL")}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with (gateway_factory or open_gateway)() as gw:
            app.state.gateway = gw
            app.state.channel_urls = urls
            senders = {c: SENDERS[c] for c in hosted if c in SENDERS}
            loop = asyncio.create_task(gw.delivery_loop(senders))
            try:
                yield
            finally:
                loop.cancel()

    app = FastAPI(title="Headless AI capability boundary", version="0.1.0", lifespan=lifespan)
    for c in hosted:
        app.include_router(ROUTERS[c])

    @app.get("/healthz")
    async def health() -> dict[str, Any]:
        return {"ok": True, "pid": os.getpid(), "channels": hosted}

    return app
