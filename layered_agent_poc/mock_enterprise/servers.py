"""Five real MCP servers in front of the simulated INC-4917 systems of record.

    python -m mock_enterprise itsm            # stdio
    python -m mock_enterprise source_control

Each tool is a typed Python function; the MCP SDK derives its JSON Schema. Writes accept an optional
`idempotency_key`: the platform's action gateway fills it in, a model never sees it.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

import anyio
import mcp_types as t
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from mock_enterprise.world import World

SYSTEMS = ("itsm", "source_control", "observability", "database", "kubernetes")

Env = Annotated[Literal["production", "staging", "development"], Field(description="Deployment environment")]
Service = Annotated[str, Field(description="Service name, e.g. checkout-api")]
Key = Annotated[str | None, Field(description="Idempotency key (set by the platform)")]

READ = t.ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = t.ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
SOFT_WRITE = t.ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


def _guard(world: World, tool_id: str, fn: Callable[[], dict[str, Any]], *, write: bool) -> Callable[[], Awaitable[dict[str, Any]]]:
    """Apply injected faults around one tool execution."""

    async def run() -> dict[str, Any]:
        world.record_call(tool_id)
        fault = world.take_fault(tool_id)
        if fault and fault[0] == "timeout":
            await anyio.sleep(fault[1])
            raise ToolError(f"{tool_id}: upstream timed out")
        try:
            result = fn()
        except (LookupError, ValueError) as exc:  # expected business errors become clean MCP tool errors
            raise ToolError(str(exc)) from None
        if fault and fault[0] == "lose_response" and write:
            await anyio.sleep(fault[1])  # committed, but the caller has given up waiting
        return result

    return run


def build_server(system: str, world: World | None = None) -> MCPServer:
    w = world or World()
    srv = MCPServer(name=f"{system.replace('_', '-')}-mcp", version="1.0.0", log_level="WARNING",
                    instructions=f"Simulated {system} system for incident INC-4917. Deterministic; nothing here is real.")

    def add(fn: Callable[..., Any], name: str, description: str, annotations: t.ToolAnnotations) -> None:
        srv.add_tool(fn, name=name, description=description, annotations=annotations)

    if system == "itsm":
        async def get_incident(incident_id: Annotated[str, Field(description="Incident id, e.g. INC-4917")]) -> dict:
            return await _guard(w, "itsm.get_incident", lambda: w.get_incident(incident_id), write=False)()

        async def update_incident(incident_id: str, status: Literal["investigating", "mitigated", "resolved"],
                                  note: Annotated[str, Field(description="Work note to append")], idempotency_key: Key = None) -> dict:
            args = {"incident_id": incident_id, "status": status, "note": note, "idempotency_key": idempotency_key}
            return await _guard(w, "itsm.update_incident", lambda: w.update_incident(args), write=True)()

        add(get_incident, "get_incident", "Get an incident record: severity, status, service, environment, timeline and work notes.", READ)
        add(update_incident, "update_incident", "Append a work note to an incident and set its status.", SOFT_WRITE)

    elif system == "source_control":
        async def search_deployments(service: Service | None = None, environment: Env | None = None,
                                     since_hours: Annotated[int, Field(ge=1, le=168)] = 24) -> dict:
            return await _guard(w, "source_control.search_deployments",
                                lambda: w.search_deployments(service, environment, since_hours), write=False)()

        async def get_diff(commit: Annotated[str, Field(description="Commit sha, e.g. a91f3c2")]) -> dict:
            return await _guard(w, "source_control.get_diff", lambda: w.get_diff(commit), write=False)()

        async def rollback_release(service: Service, environment: Env,
                                   target_version: Annotated[str, Field(description="Release version to roll back to, e.g. v4.16")],
                                   reason: str = "", idempotency_key: Key = None) -> dict:
            args = {"service": service, "environment": environment, "target_version": target_version,
                    "reason": reason, "idempotency_key": idempotency_key}
            return await _guard(w, "source_control.rollback_release", lambda: w.rollback_release(args), write=True)()

        add(search_deployments, "search_deployments",
            "List recent deployments (version, previous version, commit, time, status), newest first.", READ)
        add(get_diff, "get_diff", "Show the files and unified diff of a commit.", READ)
        add(rollback_release, "rollback_release",
            "Roll a service back to an earlier release through the release pipeline (GitOps). "
            "This is the authoritative rollback path for pipeline-managed services.", WRITE)

    elif system == "observability":
        async def query_latency(service: Service, environment: Env,
                                window_minutes: Annotated[int, Field(ge=5, le=240)] = 30) -> dict:
            return await _guard(w, "observability.query_latency",
                                lambda: w.query_latency(service, environment, window_minutes), write=False)()

        async def search_logs(service: Service, environment: Env,
                              level: Literal["ERROR", "WARN", "INFO"] | None = None,
                              limit: Annotated[int, Field(ge=1, le=20)] = 5) -> dict:
            return await _guard(w, "observability.search_logs",
                                lambda: w.search_logs(service, environment, level, limit), write=False)()

        async def get_slow_trace(service: Service, environment: Env) -> dict:
            return await _guard(w, "observability.get_slow_trace", lambda: w.get_slow_trace(service, environment), write=False)()

        add(query_latency, "query_latency", "Current p50/p95 request latency for a service, with baseline, SLO and a short series.", READ)
        add(search_logs, "search_logs", "Search recent application log patterns for a service, with counts.", READ)
        add(get_slow_trace, "get_slow_trace", "Return a representative slow request trace with its spans.", READ)

    elif system == "database":
        async def get_connection_pool_stats(service: Service, environment: Env) -> dict:
            return await _guard(w, "database.get_connection_pool_stats",
                                lambda: w.get_connection_pool_stats(service, environment), write=False)()

        add(get_connection_pool_stats, "get_connection_pool_stats",
            "Connection-pool usage of a service's database client: max, in use, waiting, acquire wait.", READ)

    elif system == "kubernetes":
        async def get_pods(service: Service, environment: Env) -> dict:
            return await _guard(w, "kubernetes.get_pods", lambda: w.get_pods(service, environment), write=False)()

        async def rollback_deployment(service: Service, environment: Env,
                                      revision: Annotated[int, Field(description="ReplicaSet revision to roll back to")],
                                      idempotency_key: Key = None) -> dict:
            args = {"service": service, "environment": environment, "revision": revision, "idempotency_key": idempotency_key}
            return await _guard(w, "kubernetes.rollback_deployment", lambda: w.rollback_deployment(args), write=True)()

        add(get_pods, "get_pods", "List a workload's pods with status, restarts, image version and resource use.", READ)
        add(rollback_deployment, "rollback_deployment", "Roll a Kubernetes deployment back to an earlier ReplicaSet revision.", WRITE)

    else:
        raise ValueError(f"unknown system {system}")
    return srv


def main(argv: list[str] | None = None) -> None:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if args[:1] == ["reset"]:
        World().reset()
        print("enterprise world reset: checkout-api production back on v4.17, incident active")
        return
    if args[:1] == ["status"]:
        w = World()
        print(dump({"now": w.now().isoformat(), "checkout-api/production": w.version("checkout-api", "production"),
                    "incident_active": w.incident_active("checkout-api", "production"),
                    "rollbacks_executed": len(w.executions("source_control.rollback_release")),
                    "rollback_replays": w.replay_count("source_control.rollback_release")}))
        return
    if len(args) != 1 or args[0] not in SYSTEMS:
        raise SystemExit(f"usage: python -m mock_enterprise {{{'|'.join(SYSTEMS)}|reset|status}}")
    anyio.run(build_server(args[0]).run_stdio_async)


def dump(obj: Any) -> str:
    return json.dumps(obj, indent=2)
