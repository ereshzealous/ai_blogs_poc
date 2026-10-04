"""The ToolPort handed to an agent: read capabilities only, described for a model, executed through the gateway.

An agent can look, never touch.  Side effects are proposed as data and executed by the orchestrator after policy.
"""

from __future__ import annotations

import json
from typing import Any

from layered_platform.contracts import ActionContext
from layered_platform.tools.gateway import ActionDenied, ActionFailed, ActionGateway, ApprovalRequired
from layered_platform.tools.registry import Registry


class ReadOnlyToolbox:
    def __init__(self, gateway: ActionGateway, capabilities: list[str], ctx: ActionContext):
        self.gateway, self.ctx = gateway, ctx
        self.by_name = {Registry.exposed_name(c): c for c in capabilities if (gateway.registry.get(c) or {}).get("kind") == "read"}

    def definitions(self) -> list[dict[str, Any]]:
        out = []
        for name, cap in self.by_name.items():
            desc, schema = self.gateway.describe(cap)
            out.append({"type": "function", "function": {"name": name, "description": desc, "parameters": schema}})
        return out

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        cap = self.by_name.get(name)
        if cap is None:
            return f"Error: {name} is not available to this agent (read-only capabilities only)."
        try:
            return json.dumps(await self.gateway.execute(cap, arguments, self.ctx), default=str)
        except (ActionDenied, ApprovalRequired, ActionFailed) as exc:
            return f"Error: {exc}"
