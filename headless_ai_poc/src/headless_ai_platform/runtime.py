"""Composition root: the layered platform, the interaction store and the gateway, opened together.

    async with open_gateway() as gw:
        resp = await gw.handle({...})
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from headless_ai_platform.gateway import CapabilityGateway
from headless_ai_platform.interactions import InteractionStore
from headless_ai_platform.platform.layered import LayeredPlatform
from headless_ai_platform.settings import Settings, load_settings


@asynccontextmanager
async def open_gateway(settings: Settings | None = None) -> AsyncIterator[CapabilityGateway]:
    s = settings or load_settings()
    async with LayeredPlatform.open(s) as platform:
        gw = CapabilityGateway(platform, InteractionStore(s.headless_db), settings=s)
        try:
            yield gw
        finally:
            await gw.drain()
