"""Mock CMDB backend."""

from __future__ import annotations

from typing import Any

from servers.common.handlers import Ctx, handler


def _ci(ctx: Ctx, name: str) -> dict[str, Any]:
    for ci in ctx.scenario.cmdb["configuration_items"]:
        if ci["name"] == name:
            return ci
    raise LookupError(f"No configuration item named {name}.")


@handler("cmdb:get_service")
def get_service(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    ci = _ci(ctx, args["service"])
    return {k: v for k, v in ci.items() if k != "depends_on"}


@handler("cmdb:get_dependencies")
def get_dependencies(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    ci = _ci(ctx, args["service"])
    deps = []
    for name in ci["depends_on"]:
        try:
            d = _ci(ctx, name)
            deps.append({"name": name, "type": d["type"], "owner_team": d["owner_team"]})
        except LookupError:
            deps.append({"name": name, "type": "unknown", "owner_team": None})
    return {"service": args["service"], "dependencies": deps}
