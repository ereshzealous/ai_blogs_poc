"""Real MCP servers (official Python SDK, stdio) in front of the simulated INC-4917 systems.

    python -m mcp_servers itsm | observability | deploy | deploy_v2

Both architectures start these same processes and call the same tools.  `deploy_v2` is the "new version of the
deployment backend" that experiment E3 migrates to: the same capability behind a different tool name, argument shape
and result shape.  Faults are armed in the world database (so another process can arm them) and applied here, inside
the server, so both architectures meet exactly the same failure.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Literal

import anyio
import mcp_types as t
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from simulated_enterprise.world import BusinessError, World

SERVERS = ("itsm", "observability", "deploy", "deploy_v2")

Env = Annotated[Literal["production", "staging"], Field(description="Deployment environment")]
Service = Annotated[str, Field(description="Service name, e.g. checkout-api")]
Key = Annotated[str | None, Field(description="Optional idempotency key; a repeated key returns the first result instead of executing again")]
Minutes = Annotated[int, Field(ge=1, le=120, description="Look-back window in minutes")]
Ref = Annotated[str, Field(description="Service reference 'service/environment', e.g. checkout-api/production")]
Metric = Annotated[Literal["latency_p95_ms", "error_rate_pct", "db_pool_wait_ms", "cpu_pct"], Field(description="Metric name")]

READ = t.ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = t.ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
SOFT_WRITE = t.ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


async def guarded(w: World, tool: str, args: dict[str, Any], fn: Callable[[], dict[str, Any]], *, write: bool) -> dict[str, Any]:
    """Run one tool with any armed fault applied.  lose_response = the write commits, then the reply is withheld."""
    w.record_call(tool, args)
    fault = w.take_fault(tool)
    if fault and fault[0] == "timeout":
        await anyio.sleep(fault[1])
        raise ToolError(f"{tool}: upstream timed out")
    if fault and fault[0] == "unavailable":
        raise ToolError(f"{tool}: backend unavailable (503)")
    try:
        result = fn()
    except BusinessError as exc:
        raise ToolError(str(exc)) from None
    if fault and fault[0] == "lose_response" and write:
        await anyio.sleep(fault[1])  # committed; the caller has already given up waiting
    return result


def build(system: str, world: World | None = None) -> MCPServer:
    w = world or World()
    srv = MCPServer(name=f"{system.replace('_', '-')}-mcp", version="2.0.0" if system == "deploy_v2" else "1.0.0", log_level="WARNING",
                    instructions=f"Simulated {system} system for the INC-4917 scenario. Deterministic; not a real backend.")

    if system == "itsm":
        async def get_incident(incident_id: Annotated[str, Field(description="Incident id, e.g. INC-4917")]) -> dict:
            return await guarded(w, "get_incident", {"incident_id": incident_id}, lambda: w.get_incident(incident_id), write=False)

        async def update_incident(incident_id: str, status: Literal["investigating", "mitigated", "resolved"],
                                  note: Annotated[str, Field(description="Work note to append")], idempotency_key: Key = None) -> dict:
            a = {"incident_id": incident_id, "status": status, "note": note}
            return await guarded(w, "update_incident", a, lambda: w.update_incident(incident_id, status, note, idempotency_key), write=True)

        srv.add_tool(get_incident, name="get_incident", description="Read an incident: service, environment, severity, status, timeline and notes.", annotations=READ)
        srv.add_tool(update_incident, name="update_incident", description="Append a work note to an incident and set its status.", annotations=SOFT_WRITE)

    elif system == "observability":
        async def query_metrics(service: Service, environment: Env, metric: Metric, minutes: Minutes = 30) -> dict:
            a = {"service": service, "environment": environment, "metric": metric, "minutes": minutes}
            return await guarded(w, "query_metrics", a, lambda: w.query_metrics(service, environment, metric, minutes), write=False)

        async def search_logs(service: Service, environment: Env, query: Annotated[str, Field(description="Words to match")] = "", minutes: Minutes = 30) -> dict:
            a = {"service": service, "environment": environment, "query": query, "minutes": minutes}
            return await guarded(w, "search_logs", a, lambda: w.search_logs(service, environment, query, minutes), write=False)

        srv.add_tool(query_metrics, name="query_metrics", description="Time series for one service metric (latency_p95_ms, error_rate_pct, db_pool_wait_ms, cpu_pct), with latest value and SLO.", annotations=READ)
        srv.add_tool(search_logs, name="search_logs", description="Recent log lines for a service, filtered by words.", annotations=READ)

    elif system == "deploy":
        async def list_deployments(service: Service, environment: Env, limit: Annotated[int, Field(ge=1, le=20)] = 5) -> dict:
            a = {"service": service, "environment": environment, "limit": limit}
            return await guarded(w, "list_deployments", a, lambda: w.list_deployments(service, environment, limit), write=False)

        async def rollback_release(service: Service, environment: Env, to_release: Annotated[str, Field(description="Release id to roll back to, e.g. rel-1234")],
                                   idempotency_key: Key = None) -> dict:
            a = {"service": service, "environment": environment, "to_release": to_release}
            return await guarded(w, "rollback_release", a, lambda: w.rollback_release(service, environment, to_release, idempotency_key), write=True)

        async def restart_service(service: Service, environment: Env, idempotency_key: Key = None) -> dict:
            a = {"service": service, "environment": environment}
            return await guarded(w, "restart_service", a, lambda: w.restart_service(service, environment, idempotency_key), write=True)

        async def scale_service(service: Service, environment: Env, replicas: Annotated[int, Field(ge=0, le=50)], idempotency_key: Key = None) -> dict:
            a = {"service": service, "environment": environment, "replicas": replicas}
            return await guarded(w, "scale_service", a, lambda: w.scale_service(service, environment, replicas, idempotency_key), write=True)

        # Added to the deployment server after the agents were written: a write neither agent's author listed.
        async def flush_sessions(service: Service, environment: Env, idempotency_key: Key = None) -> dict:
            a = {"service": service, "environment": environment}
            return await guarded(w, "flush_sessions", a, lambda: w.flush_sessions(service, environment, idempotency_key), write=True)

        srv.add_tool(flush_sessions, name="flush_sessions", description="Drop every active user session of a service (cache flush). Production change.", annotations=WRITE)
        srv.add_tool(list_deployments, name="list_deployments", description="Recent releases of a service in one environment, newest first, and which release is running.", annotations=READ)
        srv.add_tool(rollback_release, name="rollback_release", description="Roll a service back to an earlier release. Production change.", annotations=WRITE)
        srv.add_tool(restart_service, name="restart_service", description="Restart every instance of a service. Production change.", annotations=WRITE)
        srv.add_tool(scale_service, name="scale_service", description="Set the replica count of a service. Production change.", annotations=WRITE)

    elif system == "deploy_v2":
        # Deployment backend v2: one "service_ref" instead of service + environment, "target_revision" instead of
        # to_release, "request_id" instead of idempotency_key, and a nested result.  Same world, same behaviour.
        def split(ref: str) -> tuple[str, str]:
            if "/" not in ref:
                raise ToolError("service_ref must look like service/environment")
            s, e = ref.split("/", 1)
            return s, e

        def v2(result: dict[str, Any]) -> dict[str, Any]:
            return {"operation": {"state": "SUCCEEDED", "kind": "rollback", "detail": result}}

        async def get_release_history(service_ref: Ref, limit: Annotated[int, Field(ge=1, le=20)] = 5) -> dict:
            s, e = split(service_ref)
            return await guarded(w, "list_deployments", {"service": s, "environment": e, "limit": limit}, lambda: w.list_deployments(s, e, limit), write=False)

        async def rollback(service_ref: Ref, target_revision: Annotated[str, Field(description="Release id to return to")],
                           request_id: Annotated[str | None, Field(description="Client request id; a repeated id is not executed twice")] = None) -> dict:
            s, e = split(service_ref)
            a = {"service": s, "environment": e, "to_release": target_revision}
            return await guarded(w, "rollback_release", a, lambda: v2(w.rollback_release(s, e, target_revision, request_id)), write=True)

        srv.add_tool(get_release_history, name="get_release_history", description="Release history for a service_ref, newest first.", annotations=READ)
        srv.add_tool(rollback, name="rollback", description="Create a rollback operation to target_revision. Production change.", annotations=WRITE)

    else:
        raise ValueError(f"unknown MCP server {system}")
    return srv


def main(argv: list[str] | None = None) -> None:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1 or args[0] not in SERVERS:
        raise SystemExit(f"usage: python -m mcp_servers {{{'|'.join(SERVERS)}}}")
    anyio.run(build(args[0]).run_stdio_async)
