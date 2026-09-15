"""Handler registry: maps a ToolSpec.handler reference to a mock-backend function.

A reference looks like "observability:query_latency". The part before the colon names the backend
package (`servers/observability_mcp/backend.py`); backends register functions with @handler.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from servers.common.scenario import Scenario
from servers.common.toolspec import ToolSpec
from servers.common.world import World, iso

HandlerFn = Callable[["Ctx", dict[str, Any]], dict[str, Any]]
_HANDLERS: dict[str, HandlerFn] = {}


@dataclass
class Ctx:
    world: World
    run_id: str
    server: str
    spec: ToolSpec

    @property
    def scenario(self) -> Scenario:
        return self.world.scenario

    @property
    def now(self) -> datetime:
        return self.world.now(self.run_id)

    @property
    def now_iso(self) -> str:
        return iso(self.now)

    def record(self, kind: str, payload: dict[str, Any], advance_minutes: int = 0) -> dict[str, Any]:
        return self.world.record(self.run_id, self.server, self.spec.name, kind, payload, advance_minutes)


def handler(ref: str) -> Callable[[HandlerFn], HandlerFn]:
    def register(fn: HandlerFn) -> HandlerFn:
        if ref in _HANDLERS:
            raise ValueError(f"duplicate handler {ref}")
        _HANDLERS[ref] = fn
        return fn

    return register


def resolve(ref: str) -> HandlerFn:
    """Resolve "backend:function" or "backend:function|parameters" (parameters are read via ctx.spec.handler)."""
    key = ref.split("|", 1)[0]
    if key not in _HANDLERS:
        backend = key.split(":", 1)[0]
        importlib.import_module(f"servers.{backend}_mcp.backend")
    try:
        return _HANDLERS[key]
    except KeyError as exc:
        raise LookupError(f"no handler registered for {key}") from exc


def handler_params(ctx: Ctx) -> list[str]:
    return ctx.spec.handler.split("|")[1:]


def require_service(ctx: Ctx, service: str) -> dict[str, Any]:
    services = ctx.scenario.services
    if service not in services:
        raise LookupError(f"Unknown service '{service}'. Known services: {', '.join(sorted(services))}.")
    return services[service]
