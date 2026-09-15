"""Mock feature-flag backend."""

from __future__ import annotations

from typing import Any

from servers.common.handlers import Ctx, handler


def _flags(ctx: Ctx) -> list[dict[str, Any]]:
    flags = [dict(f) for f in ctx.scenario.feature_flags["flags"]]
    for e in ctx.world.events(ctx.run_id, "flag_set"):
        p = e["payload"]
        for f in flags:
            if f["key"] == p["key"] and f["environment"] == p["environment"]:
                f["enabled"] = p["enabled"]
                f["rollout_pct"] = p["rollout_pct"]
    return flags


@handler("feature_flags:get_flag")
def get_flag(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    for f in _flags(ctx):
        if f["key"] == args["key"] and f["environment"] == args["environment"]:
            return f
    raise LookupError(f"Flag {args['key']} not found in {args['environment']}.")


@handler("feature_flags:list_flag_changes")
def list_flag_changes(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    changes = [dict(c) for c in ctx.scenario.feature_flags["changes"]]
    for e in ctx.world.events(ctx.run_id, "flag_set"):
        p = e["payload"]
        changes.append({"key": p["key"], "environment": p["environment"], "at": e["at"],
                        "change": f"enabled={p['enabled']} rollout={p['rollout_pct']}%", "actor": "incident-agent"})
    hits = [c for c in changes if (not args.get("environment") or c["environment"] == args["environment"])
            and (not args.get("since") or c["at"] >= args["since"])]
    return {"changes": sorted(hits, key=lambda c: c["at"], reverse=True)}


@handler("feature_flags:set_flag")
def set_flag(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    flag = get_flag(ctx, {"key": args["key"], "environment": args["environment"]})
    pct = args.get("rollout_pct", 100 if args["enabled"] else 0)
    ev = ctx.record("flag_set", {"key": flag["key"], "environment": flag["environment"], "enabled": args["enabled"], "rollout_pct": pct})
    return {"key": flag["key"], "environment": flag["environment"], "enabled": args["enabled"], "rollout_pct": pct, "at": ev["at"]}
