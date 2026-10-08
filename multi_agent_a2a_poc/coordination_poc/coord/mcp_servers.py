"""Real MCP servers (official Python SDK, stdio) in front of the simulated enterprise.

    python -m coord.mcp_servers itsm | observability | deploy | change

Every architecture reaches every system through these same processes and these same 13 tools.  In architecture C each
A2A agent process starts its own stdio sessions to them; all of them open the one world file named by C1_WORLD_DB.
The servers know nothing about agents, policy or approval: that is the capability gateway's job, in the caller.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from typing import Annotated, Any, Literal

import anyio
import mcp_types as t
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from coord.world import BusinessError, World

SERVERS = ("itsm", "observability", "deploy", "change")

Env = Annotated[Literal["production", "staging"], Field(description="Deployment environment")]
Service = Annotated[str, Field(description="Service name, e.g. checkout-api")]
Minutes = Annotated[int, Field(ge=1, le=120, description="Look-back window in minutes")]
Key = Annotated[str | None, Field(description="Idempotency key; a repeated key returns the first result instead of executing again")]

READ = t.ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = t.ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)


def _run(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return fn()
    except BusinessError as exc:
        raise ToolError(str(exc)) from None


def build(system: str, world: World | None = None) -> MCPServer:
    w = world or World(os.environ["C1_WORLD_DB"])
    srv = MCPServer(name=f"{system}-mcp", version="1.0.0", log_level="WARNING",
                    instructions=f"Simulated {system} system for the C1 incident fixtures. Deterministic; not a real backend.")

    if system == "itsm":
        async def get_incident(incident_id: Annotated[str, Field(description="Incident id, e.g. INC-4917")]) -> dict:
            return _run(lambda: w.get_incident(incident_id))

        async def get_runbook(service: Service) -> dict:
            return _run(lambda: w.get_runbook(service))

        srv.add_tool(get_incident, name="get_incident", description="Read an incident: service, environment, severity, impact, timeline and notes.", annotations=READ)
        srv.add_tool(get_runbook, name="get_runbook", description="The on-call runbook for a service, plus the general production change rules.", annotations=READ)

    elif system == "observability":
        async def query_metrics(service: Service, environment: Env, metric: Annotated[str, Field(description="Metric name, e.g. latency_p95_ms, error_rate_pct, cpu_pct, memory_pct, db_pool_wait_ms, cache_hit_pct, upstream_latency_ms, connections_active, request_rate_rps, evictions_per_s")],
                                minutes: Minutes = 30) -> dict:
            return _run(lambda: w.query_metrics(service, environment, metric, minutes))

        async def search_logs(service: Service, environment: Env, query: Annotated[str, Field(description="Words to match (any)")] = "", minutes: Minutes = 30) -> dict:
            return _run(lambda: w.search_logs(service, environment, query, minutes))

        async def get_dependencies(service: Service) -> dict:
            return _run(lambda: w.get_dependencies(service))

        srv.add_tool(query_metrics, name="query_metrics", description="Time series of one metric for one service, with latest, min, max and SLO. An unknown metric returns the list of available metrics.", annotations=READ)
        srv.add_tool(search_logs, name="search_logs", description="Recent log lines for a service, filtered by words.", annotations=READ)
        srv.add_tool(get_dependencies, name="get_dependencies", description="Service map: owner, tier, current replica count, what a service depends on (internal or external, with provider status for external) and what depends on it.", annotations=READ)

    elif system == "deploy":
        async def list_deployments(service: Service, environment: Env, limit: Annotated[int, Field(ge=1, le=20)] = 5) -> dict:
            return _run(lambda: w.list_deployments(service, environment, limit))

        async def rollback_release(service: Service, environment: Env, to_release: Annotated[str, Field(description="Release id to roll back to, e.g. rel-1234")], idempotency_key: Key = None) -> dict:
            return _run(lambda: w.rollback_release(service, environment, to_release, idempotency_key))

        async def restart_service(service: Service, environment: Env, idempotency_key: Key = None) -> dict:
            return _run(lambda: w.restart_service(service, environment, idempotency_key))

        async def scale_service(service: Service, environment: Env, replicas: Annotated[int, Field(ge=0, le=50)], idempotency_key: Key = None) -> dict:
            return _run(lambda: w.scale_service(service, environment, replicas, idempotency_key))

        async def flush_sessions(service: Service, environment: Env, idempotency_key: Key = None) -> dict:
            return _run(lambda: w.flush_sessions(service, environment, idempotency_key))

        srv.add_tool(list_deployments, name="list_deployments", description="Recent releases of a service in one environment, newest first, and which release is running.", annotations=READ)
        srv.add_tool(rollback_release, name="rollback_release", description="Roll a service back to an earlier release. Production change.", annotations=WRITE)
        srv.add_tool(restart_service, name="restart_service", description="Restart every instance of a service. Production change.", annotations=WRITE)
        srv.add_tool(scale_service, name="scale_service", description="Set the replica count of a service to an absolute number (not a delta; get_dependencies shows the current count). Production change.", annotations=WRITE)
        srv.add_tool(flush_sessions, name="flush_sessions", description="Drop every active session held by a service. Production change.", annotations=WRITE)

    elif system == "change":
        async def get_change_history(service: Service, environment: Env, limit: Annotated[int, Field(ge=1, le=20)] = 10) -> dict:
            return _run(lambda: w.get_change_history(service, environment, limit))

        async def revert_config(service: Service, environment: Env, change_id: Annotated[str, Field(description="Change id from get_change_history, e.g. chg-123")], idempotency_key: Key = None) -> dict:
            return _run(lambda: w.revert_config(service, environment, change_id, idempotency_key))

        async def set_feature_flag(service: Service, environment: Env, flag: Annotated[str, Field(description="Flag key")], value: Annotated[str, Field(description="New value, e.g. on/off or true/false")], idempotency_key: Key = None) -> dict:
            return _run(lambda: w.set_feature_flag(service, environment, flag, value, idempotency_key))

        srv.add_tool(get_change_history, name="get_change_history", description="Configuration changes, feature-flag changes, scheduled jobs and infrastructure events for a service, newest first.", annotations=READ)
        srv.add_tool(revert_config, name="revert_config", description="Revert one configuration or feature-flag change to its previous value. Production change.", annotations=WRITE)
        srv.add_tool(set_feature_flag, name="set_feature_flag", description="Set a feature flag of a service. Production change.", annotations=WRITE)
    else:
        raise ValueError(f"unknown MCP server {system}")
    return srv


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1 or args[0] not in SERVERS:
        raise SystemExit(f"usage: python -m coord.mcp_servers {{{'|'.join(SERVERS)}}}")
    anyio.run(build(args[0]).run_stdio_async)


if __name__ == "__main__":
    main()
