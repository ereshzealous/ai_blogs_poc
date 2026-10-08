"""The host's side of the A2A boundary: discover agents by Agent Card, delegate with SendStreamingMessage, probe with
GetTask, cancel with CancelTask.  Official a2a-sdk client, JSON-RPC binding.

Credentials and trace context travel as service parameters, i.e. HTTP headers (A2A v1.0.1 §3.2.6, §7.3):
`Authorization: Bearer <token minted for that agent>` and W3C `traceparent`.  The payload carries the delegation
(objective, inputs, ids) as one data part; identity is never in the payload.

Every delegation is measured on the wire (request and response bytes through a counting transport) and in time
(client_ms here, server_ms reported by the agent), so A2A/process-boundary overhead can be separated from the
reasoning it carries.  Failures are classified: transport (connection refused/reset: the process is gone), timeout
(deadline passed: we try CancelTask), failed (the agent reported TASK_STATE_FAILED), rejected (TASK_STATE_REJECTED,
e.g. authentication).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from a2a.client import ClientConfig, create_client
from a2a.client.client import ClientCallContext
from a2a.helpers.proto_helpers import get_message_text
from a2a.types import CancelTaskRequest, GetTaskRequest, Message, Part, Role, SendMessageRequest, TaskState
from google.protobuf import json_format, struct_pb2

from coord.telemetry import annotate, inject_headers, span
from coord.util import load_config

TERMINAL = {TaskState.TASK_STATE_COMPLETED, TaskState.TASK_STATE_FAILED, TaskState.TASK_STATE_CANCELED, TaskState.TASK_STATE_REJECTED}


class DelegationError(RuntimeError):
    def __init__(self, kind: str, detail: str, task_id: str | None = None, states: list[str] | None = None):
        super().__init__(f"{kind}: {detail}")
        self.kind, self.detail, self.task_id, self.states = kind, detail, task_id, states or []


@dataclass
class DelegationOutcome:
    out: dict[str, Any]
    task_id: str
    context_id: str
    state: str
    client_ms: float
    req_bytes: int
    resp_bytes: int
    states: list[str] = field(default_factory=list)


def ints(x: Any) -> Any:
    """protobuf Struct turns every number into a float; restore integral values."""
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, dict):
        return {k: ints(v) for k, v in x.items()}
    if isinstance(x, list):
        return [ints(v) for v in x]
    return x


def to_value(obj: Any) -> struct_pb2.Value:
    v = struct_pb2.Value()
    v.struct_value.update(obj)
    return v


class _CountingStream(httpx.AsyncByteStream):
    def __init__(self, inner: Any, counter: "CountingTransport"):
        self.inner, self.counter = inner, counter

    async def __aiter__(self):  # noqa: ANN204
        async for chunk in self.inner:
            self.counter.received += len(chunk)
            yield chunk

    async def aclose(self) -> None:
        await self.inner.aclose()


class CountingTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.inner = httpx.AsyncHTTPTransport()
        self.sent = self.received = 0

    def reset(self) -> None:
        self.sent = self.received = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        self.sent += len(body) + sum(len(k) + len(v) + 4 for k, v in request.headers.raw)
        resp = await self.inner.handle_async_request(request)
        self.received += sum(len(k) + len(v) + 4 for k, v in resp.headers.raw)
        resp.stream = _CountingStream(resp.stream, self)
        return resp

    async def aclose(self) -> None:
        await self.inner.aclose()


class A2ALink:
    def __init__(self) -> None:
        cfg = load_config("agents.yaml")
        self.urls = {name: f"http://{cfg['host']}:{a['port']}" for name, a in cfg["agents"].items()}
        self.counter = CountingTransport()
        self.http = httpx.AsyncClient(transport=self.counter, timeout=httpx.Timeout(600.0, connect=5.0))
        self.clients: dict[str, Any] = {}

    async def client(self, agent: str) -> Any:
        if agent not in self.clients:
            self.clients[agent] = await create_client(self.urls[agent], client_config=ClientConfig(streaming=True, httpx_client=self.http))
        return self.clients[agent]

    async def card(self, agent: str) -> dict[str, Any]:
        c = await self.client(agent)
        return json_format.MessageToDict(c._card)  # noqa: SLF001 - the resolved Agent Card, for the record

    async def delegate(self, agent: str, payload: dict[str, Any], token: str, *, timeout_s: float, message_id: str) -> DelegationOutcome:
        c = await self.client(agent)
        msg = Message(message_id=message_id, role=Role.ROLE_USER, parts=[Part(data=to_value(payload))])
        task_id, context_id, states = "", "", []
        artifact: dict[str, Any] | None = None
        final: Any = None
        status_text = ""
        with span("a2a.client.send_streaming_message", **{"c1.agent": agent, "c1.delegation_id": payload.get("delegation_id")}):
            ctx = ClientCallContext(service_parameters={"Authorization": f"Bearer {token}", **inject_headers()}, timeout=timeout_s)
            self.counter.reset()
            t0 = time.perf_counter()

            async def consume() -> None:
                nonlocal task_id, context_id, artifact, final, status_text
                async for ev in c.send_message(SendMessageRequest(message=msg), context=ctx):
                    which = ev.WhichOneof("payload")
                    if which == "task":
                        task_id, context_id, final = ev.task.id, ev.task.context_id, ev.task.status.state
                        states.append(TaskState.Name(final))
                        for a in ev.task.artifacts:
                            artifact = _artifact_data(a)
                        if ev.task.status.HasField("message"):
                            status_text = get_message_text(ev.task.status.message)
                    elif which == "status_update":
                        task_id = task_id or ev.status_update.task_id
                        final = ev.status_update.status.state
                        states.append(TaskState.Name(final))
                        if ev.status_update.status.HasField("message"):
                            status_text = get_message_text(ev.status_update.status.message)
                    elif which == "artifact_update":
                        artifact = _artifact_data(ev.artifact_update.artifact)

            try:
                await asyncio.wait_for(consume(), timeout=timeout_s)
            except (asyncio.TimeoutError, TimeoutError):
                annotate(**{"c1.delegation.failure": "timeout", "a2a.task_id": task_id})
                if task_id:
                    await self.cancel(agent, task_id)
                raise DelegationError("timeout", f"no terminal state within {timeout_s:.0f}s", task_id, states) from None
            except Exception as exc:  # noqa: BLE001 - classified, not swallowed
                annotate(**{"c1.delegation.failure": "transport", "a2a.task_id": task_id})
                raise DelegationError("transport", f"{type(exc).__name__}: {exc}"[:300], task_id, states) from None
            client_ms = round((time.perf_counter() - t0) * 1000, 1)
            annotate(**{"a2a.task_id": task_id, "a2a.context_id": context_id, "a2a.final_state": TaskState.Name(final) if final is not None else "",
                        "c1.req_bytes": self.counter.sent, "c1.resp_bytes": self.counter.received, "c1.client_ms": client_ms})
        if final == TaskState.TASK_STATE_COMPLETED and artifact is not None:
            return DelegationOutcome(artifact, task_id, context_id, TaskState.Name(final), client_ms, self.counter.sent, self.counter.received, states)
        kind = "rejected" if final == TaskState.TASK_STATE_REJECTED else "failed"
        raise DelegationError(kind, status_text or f"ended in {TaskState.Name(final) if final is not None else 'no state'}", task_id, states)

    async def get_task(self, agent: str, task_id: str) -> str:
        """GetTask: the protocol-level state the agent reports for a task id (or the error it returns)."""
        c = await self.client(agent)
        try:
            t = await c.get_task(GetTaskRequest(id=task_id))
            return TaskState.Name(t.status.state)
        except Exception as exc:  # noqa: BLE001
            return f"error:{type(exc).__name__}"

    async def cancel(self, agent: str, task_id: str) -> str:
        c = await self.client(agent)
        try:
            t = await c.cancel_task(CancelTaskRequest(id=task_id))
            return TaskState.Name(t.status.state)
        except Exception as exc:  # noqa: BLE001
            return f"error:{type(exc).__name__}"

    async def close(self) -> None:
        await self.http.aclose()


def _artifact_data(a: Any) -> dict[str, Any] | None:
    for p in a.parts:
        if p.HasField("data"):
            return ints(json_format.MessageToDict(p.data))
    return None
