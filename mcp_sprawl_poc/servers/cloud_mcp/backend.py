"""Mock cloud-provider backend."""

from __future__ import annotations

from typing import Any

from servers.common.handlers import Ctx, handler


def _resource(ctx: Ctx, resource_id: str, rtype: str | None = None) -> dict[str, Any]:
    for r in ctx.scenario.cloud["resources"]:
        if r["id"] == resource_id and (rtype is None or r["type"] == rtype):
            return dict(r)
    kind = f"{rtype} " if rtype else ""
    raise LookupError(f"Cloud {kind}resource {resource_id} not found.")


def _terminated(ctx: Ctx, resource_id: str) -> bool:
    return any(e["payload"].get("resource_id") == resource_id for e in ctx.world.events(ctx.run_id, "terminate"))


def _db_metrics(ctx: Ctx, r: dict[str, Any]) -> dict[str, Any]:
    m = dict(r["metrics"])
    if r["id"] == "orders-db-prod" and ctx.world.recovered_at(ctx.run_id, "checkout-api", "production"):
        m["active_connections"] = m["baseline_active_connections"]
    return m


@handler("cloud:get_instance")
def get_instance(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    r = _resource(ctx, args["instance_id"], "vm-instance")
    if _terminated(ctx, r["id"]):
        r["status"] = "terminated"
    return r


@handler("cloud:get_service_health")
def get_service_health(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    statuses = [s for s in ctx.scenario.cloud["provider_status"]
                if s["region"] == args["region"] and (not args.get("provider_service") or s["service"] == args["provider_service"])]
    return {"region": args["region"], "as_of": ctx.now_iso, "statuses": statuses}


@handler("cloud:query_cloud_logs")
def query_cloud_logs(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    r = _resource(ctx, args["resource_id"])
    if r["type"] == "managed-postgres":
        m = _db_metrics(ctx, r)
        lines = [f"LOG: checkpoint complete; active connections={m['active_connections']}",
                 "LOG: automatic vacuum of table orders.public.order_items completed"]
    else:
        lines = [f"{r['id']}: system healthy, cpu={r['metrics']['cpu_utilization_pct']}%"]
    query = (args.get("query") or "").lower()
    if query:
        lines = [ln for ln in lines if any(tok in ln.lower() for tok in query.split())]
    return {"resource_id": r["id"], "window": args.get("time_range", "15m"), "lines": lines}


@handler("cloud:describe_resource")
def describe_resource(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    r = _resource(ctx, args["resource_id"])
    if r["type"] == "managed-postgres":
        r["metrics"] = _db_metrics(ctx, r)
    if _terminated(ctx, r["id"]):
        r["status"] = "terminated"
    return r


def _mutate(ctx: Ctx, args: dict[str, Any], key: str, rtype: str, kind: str, status: str, advance: int) -> dict[str, Any]:
    r = _resource(ctx, args[key], rtype)
    ev = ctx.record(kind, {"resource_id": r["id"], "environment": r["environment"]}, advance_minutes=advance)
    return {key: r["id"], "environment": r["environment"], "status": status, "at": ev["at"]}


@handler("cloud:restart_instance")
def restart_instance(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    return _mutate(ctx, args, "instance_id", "vm-instance", "instance_restart", "rebooting", 2)


@handler("cloud:restart_task")
def restart_task(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    return _mutate(ctx, args, "task_id", "container-task", "task_restart", "stopped; replacement starting", 1)


@handler("cloud:terminate_instance")
def terminate_instance(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    return _mutate(ctx, args, "instance_id", "vm-instance", "terminate", "shutting-down", 1)
