"""Mock team-chat backend."""

from __future__ import annotations

from typing import Any

from servers.common.handlers import Ctx, handler


def _messages(ctx: Ctx) -> list[dict[str, Any]]:
    msgs = [dict(m) for m in ctx.scenario.collaboration["messages"]]
    for e in ctx.world.events(ctx.run_id, "chat_post"):
        msgs.append({"channel": e["payload"]["channel"], "at": e["at"], "author": "incident-agent", "text": e["payload"]["text"]})
    return msgs


def _channels(ctx: Ctx) -> list[dict[str, Any]]:
    chans = [dict(c) for c in ctx.scenario.collaboration["channels"]]
    for e in ctx.world.events(ctx.run_id, "chat_channel_create"):
        chans.append({"id": e["payload"]["id"], "name": e["payload"]["name"], "topic": e["payload"]["topic"], "created_at": e["at"]})
    return chans


@handler("collaboration:search_messages")
def search_messages(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    tokens = args["query"].lower().split()
    hits = [m for m in _messages(ctx)
            if any(t in m["text"].lower() for t in tokens) and (not args.get("channel") or m["channel"] == args["channel"])]
    hits.sort(key=lambda m: m["at"], reverse=True)
    return {"messages": hits[: int(args.get("limit", 10))]}


@handler("collaboration:get_channel")
def get_channel(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    chan = next((c for c in _channels(ctx) if c["name"] == args["channel"]), None)
    if chan is None:
        raise LookupError(f"Channel {args['channel']} not found.")
    recent = sorted((m for m in _messages(ctx) if m["channel"] == chan["name"]), key=lambda m: m["at"])[-5:]
    return chan | {"recent_messages": recent}


@handler("collaboration:post_message")
def post_message(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    get_channel(ctx, {"channel": args["channel"]})
    ev = ctx.record("chat_post", {"channel": args["channel"], "text": args["text"]})
    return {"channel": args["channel"], "posted": True, "at": ev["at"]}


@handler("collaboration:create_incident_channel")
def create_incident_channel(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    number = args["incident_id"].split("-")[1]
    existing = next((c for c in _channels(ctx) if c["name"].startswith(f"#inc-{number}")), None)
    if existing:
        return existing | {"created": False}
    name = f"#inc-{number}"
    ev = ctx.record("chat_channel_create", {"id": f"C-INC{number}", "name": name, "topic": args.get("topic", args["incident_id"])})
    return {"id": f"C-INC{number}", "name": name, "created": True, "at": ev["at"]}
