"""One independent agent as an A2A server, in its own OS process (official a2a-sdk 1.2.2, A2A v1.0, JSON-RPC binding).

    python -m coord.a2a_server evidence|diagnosis|remediation|review

Serves its Agent Card at /.well-known/agent-card.json (one skill, Bearer auth declared in securitySchemes, streaming
supported) and handles SendMessage / SendStreamingMessage / GetTask / CancelTask through the SDK's DefaultRequestHandler
with an InMemoryTaskStore (tasks do not survive a restart: experiment E6 shows what that means).

Every request is authenticated before work starts (A2A v1.0.1 §7.4): the `Authorization: Bearer` header must carry a
token minted for this agent.  The W3C `traceparent` header is extracted so the agent's spans join the host's trace.
The agent's own MCP sessions, gateway and model gateway live in this process; the ledgers they append to are shared.
"""

from __future__ import annotations

import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from a2a.helpers.proto_helpers import get_data_parts, new_task_from_user_message, new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (AgentCapabilities, AgentCard, AgentInterface, AgentSkill, HTTPAuthSecurityScheme, Part, Role, SecurityRequirement,
                       SecurityScheme, StringList)
from google.protobuf import struct_pb2
from starlette.applications import Starlette

from coord.gateway import Gateway, McpPool
from coord.identity import AuthError, TokenService
from coord.models import ModelGateway, OllamaProvider
from coord.specialists import AGENTS, SpecialistEnv, run_specialist
from coord.store import Store
from coord.telemetry import annotate, extracted, setup, span
from coord.util import home, load_config

SKILLS = {
    "evidence": ("incident-evidence", "Gather incident evidence", "Collects releases, changes, metrics, logs and dependencies for an incident and reports findings with evidence references."),
    "diagnosis": ("incident-diagnosis", "Diagnose an incident", "Decides the root cause of a production incident from evidence, verifying with its own read-only lookups."),
    "remediation": ("incident-remediation", "Plan or execute a remediation", "Proposes one runbook-allowed production change; executes it only when the delegation authorizes execution."),
    "review": ("remediation-review", "Review a diagnosis and remediation", "Independently checks a diagnosis and a proposed change and approves or rejects it."),
}


def agent_card(agent: str, url: str) -> AgentCard:
    sid, name, desc = SKILLS[agent]
    return AgentCard(
        name=f"c1-{agent}-agent", description=f"C1 {agent} agent ({desc})", version="1.0.0",
        supported_interfaces=[AgentInterface(url=f"{url}/a2a", protocol_binding="JSONRPC", protocol_version="1.0")],
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["application/json"], default_output_modes=["application/json"],
        skills=[AgentSkill(id=sid, name=name, description=desc, tags=["incident", agent])],
        security_schemes={"bearer": SecurityScheme(http_auth_security_scheme=HTTPAuthSecurityScheme(
            scheme="Bearer", bearer_format="C1-HMAC", description="Delegation token minted for this agent by the C1 token service"))},
        security_requirements=[SecurityRequirement(schemes={"bearer": StringList()})],
    )


def to_value(obj: Any) -> struct_pb2.Value:
    v = struct_pb2.Value()
    v.struct_value.update(obj)
    return v


class SpecialistExecutor(AgentExecutor):
    def __init__(self, agent: str, state: dict[str, Any]):
        self.agent, self.state = agent, state
        self.principal = AGENTS[agent]["principal"]

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        headers = context.call_context.state.get("headers", {})
        task = context.current_task or new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        up = TaskUpdater(event_queue, task.id, task.context_id)
        with extracted(headers), span("a2a.server.task", **{"c1.agent": self.principal, "a2a.task_id": task.id, "a2a.context_id": task.context_id}):
            t0 = time.perf_counter()
            env: SpecialistEnv = self.state["env"]
            try:
                raw = headers.get("authorization", "")
                token = env.tokens.decode(raw.removeprefix("Bearer ").strip(), audience=self.principal)
            except AuthError as exc:
                annotate(**{"c1.auth": "rejected"})
                await up.reject(message=new_text_message(f"authentication failed: {exc}", role=Role.ROLE_AGENT))
                return
            data = get_data_parts(context.message.parts)
            if not data:
                await up.reject(message=new_text_message("expected one data part", role=Role.ROLE_AGENT))
                return
            request = data[0]
            annotate(**{"c1.workflow_id": request.get("workflow_id"), "c1.delegation_id": request.get("delegation_id"),
                        "c1.token.chain": token.chain(), "c1.token.scopes": ",".join(token.scope)})
            await up.start_work()
            try:
                out = await run_specialist(env, request, token)
            except AuthError as exc:
                await up.reject(message=new_text_message(f"authorization failed: {exc}", role=Role.ROLE_AGENT))
                return
            except Exception as exc:  # noqa: BLE001 - reported to the client as a failed task, never swallowed
                await up.failed(message=new_text_message(f"{type(exc).__name__}: {exc}"[:500], role=Role.ROLE_AGENT))
                return
            out["server_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            out["pid"] = os.getpid()
            await up.add_artifact([Part(data=to_value(out))], name=out["kind"])
            await up.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.task_id and context.context_id:
            await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()


def build_app(agent: str, port: int, provider: Any = None) -> Starlette:
    host = load_config("agents.yaml")["host"]
    card = agent_card(agent, f"http://{host}:{port}")
    state: dict[str, Any] = {}
    executor = SpecialistExecutor(agent, state)
    handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore(), agent_card=card)

    @asynccontextmanager
    async def lifespan(app: Starlette):  # noqa: ANN202
        h = home()
        setup(h / "traces", AGENTS[agent]["principal"])
        store = Store(h / "platform.db")
        world_db = os.environ.get("C1_WORLD_DB", str(h / "world.db"))
        mcp = McpPool(world_db)
        await mcp.start()
        tokens = TokenService()
        prov = provider
        if prov is None and os.environ.get("C1_SCRIPTED"):
            from coord.scripted import ScriptedProvider
            prov = ScriptedProvider()
        model = ModelGateway(store, prov or OllamaProvider())
        state["env"] = SpecialistEnv(Gateway(store, mcp, tokens, world_db), model, tokens, load_config("limits.yaml"))
        yield
        await model.close()
        await mcp.close()

    return Starlette(routes=create_agent_card_routes(card) + create_jsonrpc_routes(handler, "/a2a"), lifespan=lifespan)


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1 or args[0] not in AGENTS:
        raise SystemExit(f"usage: python -m coord.a2a_server {{{'|'.join(AGENTS)}}}")
    agent = args[0]
    port = int(os.environ.get("C1_PORT", AGENTS[agent]["port"]))
    uvicorn.run(build_app(agent, port), host=load_config("agents.yaml")["host"], port=port, log_level="warning")


if __name__ == "__main__":
    main()
