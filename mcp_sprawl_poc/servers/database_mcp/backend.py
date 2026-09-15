"""Mock database-operations backend."""

from __future__ import annotations

from typing import Any

from servers.common.handlers import Ctx, handler, require_service

DATABASE_ENVS = {"orders-db-prod": "production", "orders-db-staging": "staging"}


@handler("database:get_connection_pool_stats")
def get_connection_pool_stats(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    service, env = args["service"], args["environment"]
    require_service(ctx, service)
    stats = ctx.scenario.database["pool_stats"].get(service, {}).get(env)
    if not stats:
        raise LookupError(f"No connection-pool telemetry for {service} in {env}.")
    shape = ctx.scenario.metrics.get(service, {}).get(env, {})
    start = shape.get("incident_start")
    recovered = ctx.world.recovered_at(ctx.run_id, service, env)
    incident = bool(start) and ctx.now >= ctx.scenario.at(start) and (recovered is None or ctx.now < recovered)
    current = stats["incident"] if incident and "incident" in stats else stats["baseline"]
    return {"service": service, "environment": env, "as_of": ctx.now_iso, "database": "orders-db", **current}


@handler("database:list_slow_queries")
def list_slow_queries(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    queries = ctx.scenario.database["slow_queries"].get(args["database_id"])
    if queries is None:
        raise LookupError(f"Database {args['database_id']} not found.")
    return {"database_id": args["database_id"], "queries": queries[: int(args.get("limit", 5))]}


@handler("database:kill_session")
def kill_session(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    if args["database_id"] not in DATABASE_ENVS:
        raise LookupError(f"Database {args['database_id']} not found.")
    ev = ctx.record("db_kill_session", {"database_id": args["database_id"], "session_id": args["session_id"],
                                        "environment": DATABASE_ENVS[args["database_id"]]})
    return {"database_id": args["database_id"], "session_id": args["session_id"], "terminated": True, "at": ev["at"]}


@handler("database:failover_cluster")
def failover_cluster(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    if args["database_id"] not in DATABASE_ENVS:
        raise LookupError(f"Database {args['database_id']} not found.")
    ev = ctx.record("db_failover", {"database_id": args["database_id"], "environment": DATABASE_ENVS[args["database_id"]],
                                    "reason": args.get("reason")}, advance_minutes=2)
    return {"database_id": args["database_id"], "status": "failover in progress", "at": ev["at"]}
