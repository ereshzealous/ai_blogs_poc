"""MCP gateway: the only path from an agent to an MCP server.

It connects to every server in a catalog manifest over stdio with the official MCP client, aggregates
`tools/list` (following pagination cursors) under collision-free exposed names, and runs every
`tools/call` through the deterministic policy engine first:

    agent -> Gateway.call_tool -> resolve environment -> PolicyEngine -> (approval) -> MCP tools/call

`enforcement="enforce"` blocks DENY and waits for approval on REQUIRE_APPROVAL. `enforcement="observe"`
records the same decision but executes anyway; the benchmark uses it to model ungoverned modes and to
count unsafe invocations that reached a backend.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import mcp_types as types
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from control_plane.paths import REPO_ROOT
from control_plane.policy.approvals import ApprovalRequest, ApprovalStatus, ApprovalStore
from control_plane.policy.engine import Decision, Identity, PolicyEngine, PolicyInput, PolicyResult
from control_plane.policy.environment import ResourceInventory, resolve_environment
from control_plane.registry.registry import CapabilityRegistry
from control_plane.telemetry import AuditLog, span

Enforcement = Literal["enforce", "observe"]
Approver = Callable[[ApprovalRequest, PolicyResult], Awaitable[bool]]


@dataclass(frozen=True)
class PublishedTool:
    server: str
    tool: types.Tool

    @property
    def tool_id(self) -> str:
        return f"{self.server}.{self.tool.name}"

    @property
    def exposed_name(self) -> str:
        return f"{self.server}__{self.tool.name}"

    def definition(self) -> dict[str, Any]:
        """Function-calling definition shown to a model (identical in every benchmark mode)."""
        return {"type": "function", "function": {"name": self.exposed_name, "description": self.tool.description or "",
                                                 "parameters": self.tool.input_schema}}


@dataclass
class InvocationContext:
    request_id: str
    run_id: str
    identity: Identity
    enforcement: Enforcement = "enforce"
    approver: Approver | None = None


@dataclass
class InvocationOutcome:
    exposed_name: str
    tool_id: str | None
    arguments: dict[str, Any]
    policy: PolicyResult | None
    executed: bool
    status: str  # executed | denied | approval_rejected | approval_pending | unknown_tool
    result: Any = None
    is_error: bool = False
    latency_ms: float = 0.0
    approval: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"exposed_name": self.exposed_name, "tool_id": self.tool_id, "arguments": self.arguments,
                "policy": self.policy.to_dict() if self.policy else None, "executed": self.executed, "status": self.status,
                "is_error": self.is_error, "latency_ms": round(self.latency_ms, 2), "approval": self.approval}


class Gateway:
    def __init__(self, manifest: str | Path, registry: CapabilityRegistry, policy: PolicyEngine, *,
                 approvals: ApprovalStore | None = None, audit: AuditLog | None = None,
                 inventory: ResourceInventory | None = None, world_db: str | Path | None = None):
        self.manifest = Path(manifest)
        self.registry = registry
        self.policy = policy
        self.approvals = approvals or ApprovalStore()
        self.audit = audit or AuditLog()
        self.inventory = inventory or ResourceInventory.from_scenario()
        self.world_db = world_db
        self._stack: AsyncExitStack | None = None
        self._clients: dict[str, Client] = {}
        self.tools: dict[str, PublishedTool] = {}

    # -- lifecycle ----------------------------------------------------------------------------
    async def __aenter__(self) -> Gateway:
        with open(self.manifest, encoding="utf-8") as fh:
            servers = json.load(fh)["servers"]
        env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
        if self.world_db:
            env["MOCK_WORLD_DB"] = str(self.world_db)
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        with span("gateway.connect", manifest=self.manifest.name, servers=len(servers)):
            for key in servers:
                params = StdioServerParameters(command=sys.executable, cwd=str(REPO_ROOT), env=env,
                                               args=["-m", "servers.common.runtime", "--server", key, "--manifest", str(self.manifest)])
                self._clients[key] = await self._stack.enter_async_context(Client(params))
            await self.refresh_tools()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._stack is not None:
            await self._stack.__aexit__(*exc)
        self._clients.clear()

    async def refresh_tools(self) -> dict[str, PublishedTool]:
        tools: dict[str, PublishedTool] = {}
        for key, client in self._clients.items():
            cursor: str | None = None
            while True:
                page = await client.list_tools(cursor=cursor)
                for t in page.tools:
                    published = PublishedTool(key, t)
                    tools[published.exposed_name] = published
                cursor = page.next_cursor
                if not cursor:
                    break
        self.tools = tools
        return tools

    def published_annotations(self) -> dict[str, dict[str, Any]]:
        return {p.tool_id: {"annotations": p.tool.annotations.model_dump(by_alias=True, exclude_none=True) if p.tool.annotations else {}}
                for p in self.tools.values()}

    # -- invocation ---------------------------------------------------------------------------
    def evaluate(self, exposed_name: str, arguments: dict[str, Any], ctx: InvocationContext) -> PolicyResult | None:
        published = self.tools.get(exposed_name)
        if published is None:
            return None
        record = self.registry.get(published.tool_id)
        resolved = resolve_environment(arguments, record, self.inventory)
        return self.policy.evaluate(PolicyInput(ctx.identity, published.tool_id, arguments, record, resolved.environment, ctx.request_id))

    async def call_tool(self, exposed_name: str, arguments: dict[str, Any], ctx: InvocationContext) -> InvocationOutcome:
        published = self.tools.get(exposed_name)
        if published is None:
            self.audit.write("invocation.unknown_tool", request_id=ctx.request_id, exposed_name=exposed_name)
            return InvocationOutcome(exposed_name, None, arguments, None, False, "unknown_tool", is_error=True,
                                     result=f"Unknown tool: {exposed_name}")
        with span("gateway.call_tool", request_id=ctx.request_id, tool_id=published.tool_id, arguments=arguments,
                  enforcement=ctx.enforcement) as s:
            decision = self.evaluate(exposed_name, arguments, ctx)
            assert decision is not None
            s.set_attribute("policy.decision", decision.decision.value)
            s.set_attribute("policy.rule", decision.rule_id)
            self.audit.write("policy.decision", request_id=ctx.request_id, run_id=ctx.run_id, user=ctx.identity.user_id,
                             agent=ctx.identity.agent_id, enforcement=ctx.enforcement, arguments=arguments, **decision.to_dict())
            approval_state = None
            if ctx.enforcement == "enforce":
                if decision.decision is Decision.DENY:
                    return InvocationOutcome(exposed_name, published.tool_id, arguments, decision, False, "denied",
                                             result=f"Denied by policy ({decision.rule_id}): {decision.reason}")
                if decision.decision is Decision.REQUIRE_APPROVAL:
                    approval_state = await self._approve(published.tool_id, arguments, decision, ctx)
                    if approval_state != ApprovalStatus.APPROVED:
                        status = "approval_rejected" if approval_state == ApprovalStatus.REJECTED else "approval_pending"
                        return InvocationOutcome(exposed_name, published.tool_id, arguments, decision, False, status,
                                                 result=f"Not executed: approval {approval_state.value}.", approval=approval_state.value)
            t0 = time.perf_counter()
            with span("mcp.tools_call", server=published.server, tool=published.tool.name):
                result = await self._clients[published.server].call_tool(published.tool.name, arguments, meta={"run_id": ctx.run_id})
            latency = (time.perf_counter() - t0) * 1000
            text = "".join(c.text for c in result.content if isinstance(c, types.TextContent))
            payload: Any = result.structured_content if result.structured_content is not None else text
            s.set_attribute("mcp.is_error", bool(result.is_error))
            s.set_attribute("mcp.latency_ms", round(latency, 2))
            self.audit.write("invocation.executed", request_id=ctx.request_id, run_id=ctx.run_id, tool_id=published.tool_id,
                             arguments=arguments, is_error=bool(result.is_error), latency_ms=round(latency, 2),
                             policy_decision=decision.decision.value, enforcement=ctx.enforcement,
                             approval=approval_state.value if approval_state else None)
            return InvocationOutcome(exposed_name, published.tool_id, arguments, decision, True, "executed", payload,
                                     bool(result.is_error), latency, approval_state.value if approval_state else None)

    async def _approve(self, tool_id: str, arguments: dict[str, Any], decision: PolicyResult, ctx: InvocationContext) -> ApprovalStatus:
        req = ApprovalRequest(decision.invocation_digest, ctx.request_id, tool_id, json.dumps(arguments, sort_keys=True),
                              decision.environment, decision.reason)
        status = self.approvals.request(req)
        self.audit.write("approval.requested", request_id=ctx.request_id, tool_id=tool_id, digest=req.digest, status=status.value)
        if status != ApprovalStatus.PENDING or ctx.approver is None:
            return status
        with span("approval.wait", tool_id=tool_id, digest=req.digest[:16]):
            approved = await ctx.approver(req, decision)
        status = self.approvals.decide(req.digest, approved, approver=ctx.identity.user_id, note="human decision")
        self.audit.write("approval.decided", request_id=ctx.request_id, tool_id=tool_id, digest=req.digest, status=status.value,
                         approver=ctx.identity.user_id)
        return status
