"""The capability gateway: the only path from any component, in any process, to any enterprise system.

    verify token (signature, audience=gateway, expiry) -> registry -> policy -> approval (digest-bound) ->
    idempotency key (owned by the workflow) -> MCP call -> audit row

The same code runs in the host (architectures A and B) and inside every A2A agent process (architecture C).  Every
attempt, allowed or not, is one row in `gateway_calls`; reads get an evidence reference (`ev-<seq>`) that reasoning
components cite, so a claim can be traced to the call that produced it.  Approval is a simulated incident commander
who approves every request that policy routes to approval; the approval is bound to a digest of the exact call (T3).
Identical for every architecture: the component that *triggers* a write differs, the rules it meets do not.
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

import mcp_types as types
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.shared.exceptions import MCPError

from coord.identity import AuthError, Token, TokenService
from coord.policy import PolicyEngine
from coord.store import Store
from coord.telemetry import annotate, current_ids, span
from coord.util import ROOT, canon, digest, load_config
from coord.world import World

APPROVER = "ic.oncall"


class GatewayError(RuntimeError):
    kind = "error"


class Denied(GatewayError):
    kind = "denied"


class ToolFailed(GatewayError):
    kind = "error"


@dataclass
class CallContext:
    workflow_id: str
    component: str
    incident_environment: str
    delegation_id: str | None = None


class McpPool:
    """One stdio session per MCP server, per process.  The only place that speaks MCP."""

    def __init__(self, world_db: str):
        self.world_db = world_db
        self._stack: AsyncExitStack | None = None
        self.clients: dict[str, Client] = {}
        self.tools: dict[str, types.Tool] = {}

    async def start(self, servers: tuple[str, ...] = ("itsm", "observability", "deploy", "change")) -> None:
        env = dict(os.environ, PYTHONPATH=str(ROOT), C1_WORLD_DB=self.world_db)
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        for server in servers:
            params = StdioServerParameters(command=sys.executable, args=["-m", "coord.mcp_servers", server], env=env, cwd=str(ROOT))
            client = await self._stack.enter_async_context(Client(params))
            self.clients[server] = client
            for tool in (await client.list_tools()).tools:
                self.tools[tool.name] = tool

    async def close(self) -> None:
        if self._stack:
            await self._stack.__aexit__(None, None, None)
            self._stack = None

    async def call(self, server: str, tool: str, arguments: dict[str, Any], timeout_s: float) -> Any:
        try:
            result = await self.clients[server].call_tool(tool, arguments, read_timeout_seconds=timeout_s)
        except MCPError as exc:
            raise ToolFailed(f"{tool}: {exc}") from exc
        text = "".join(c.text for c in result.content if isinstance(c, types.TextContent))
        if result.is_error:
            raise ToolFailed(text)
        try:
            return json.loads(text)
        except ValueError:
            return text


class Gateway:
    def __init__(self, store: Store, mcp: McpPool, tokens: TokenService, world_db: str):
        self.store, self.mcp, self.tokens = store, mcp, tokens
        self.world = World(world_db)
        self.policy = PolicyEngine()
        cfg = load_config("capabilities.yaml")
        self.registry: dict[str, dict[str, Any]] = cfg["capabilities"]
        self.timeouts = cfg["timeouts"]

    # ---- what a model is shown ---------------------------------------------------------------------------------------
    def tool_definitions(self, names: list[str]) -> list[dict[str, Any]]:
        out = []
        for name in names:
            t = self.mcp.tools[name]
            schema = json.loads(json.dumps(t.input_schema))
            schema.get("properties", {}).pop("idempotency_key", None)  # the model never sees, so never invents, a key
            if "required" in schema:
                schema["required"] = [r for r in schema["required"] if r != "idempotency_key"]
            out.append({"type": "function", "function": {"name": name, "description": t.description or "", "parameters": schema}})
        return out

    def catalog(self, names: list[str]) -> list[dict[str, Any]]:
        """Information only, no authority: tool names, descriptions and parameters, for planners that hold no tools."""
        return [{"tool": d["function"]["name"], "description": d["function"]["description"],
                 "parameters": {k: v.get("description", v.get("type", "")) for k, v in d["function"]["parameters"].get("properties", {}).items()},
                 "required": d["function"]["parameters"].get("required", [])} for d in self.tool_definitions(names)]

    def missing_args(self, capability: str, args: dict[str, Any]) -> list[str]:
        t = self.mcp.tools.get(capability)
        if t is None:
            return [f"unknown tool {capability}"]
        req = [r for r in t.input_schema.get("required", []) if r != "idempotency_key"]
        props = set(t.input_schema.get("properties", {}))
        return [f"missing argument {r}" for r in req if r not in args] + [f"unknown argument {k}" for k in args if k not in props]

    # ---- the governed path -------------------------------------------------------------------------------------------
    async def call(self, token: str | Token, capability: str, args: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
        meta = self.registry.get(capability)
        args = {k: v for k, v in (args or {}).items() if k != "idempotency_key"}
        version = self.world.version()
        with span("gateway.call", **{"c1.workflow_id": ctx.workflow_id, "c1.component": ctx.component, "gen_ai.tool.name": capability,
                                     "c1.delegation_id": ctx.delegation_id}):
            trace_id, _ = current_ids()
            row = dict(workflow_id=ctx.workflow_id, component=ctx.component, capability=capability, kind=meta["kind"] if meta else "unknown",
                       args=canon(args), world_version=version, trace_id=trace_id, delegation_id=ctx.delegation_id)
            try:
                tok = token if isinstance(token, Token) else self.tokens.decode(token, audience="gateway")
                if tok.wf != ctx.workflow_id:
                    raise AuthError(f"token is for workflow {tok.wf}, not {ctx.workflow_id}")
            except AuthError as exc:
                self.store.record_call(**row, actor_chain="?", effect="DENY", rule="AUTH", outcome="denied", error=str(exc))
                annotate(**{"c1.policy.effect": "DENY", "c1.policy.rule": "AUTH"})
                raise Denied(f"authentication failed: {exc}") from None
            row["actor_chain"] = tok.chain()
            decision = self.policy.evaluate(capability, args, tok.scope, ctx.incident_environment)
            annotate(**{"c1.policy.effect": decision.effect, "c1.policy.rule": decision.rule})
            if decision.effect == "DENY":
                self.store.record_call(**row, effect="DENY", rule=decision.rule, outcome="denied", error=decision.reason)
                raise Denied(f"DENIED by policy {decision.rule}: {decision.reason}")
            approval_id = None
            if decision.effect == "REQUIRE_APPROVAL":
                approval_id = self._approve(ctx.workflow_id, capability, args, decision.required_role or "")
            assert meta is not None
            key = None
            if meta["kind"] == "write":
                wf = self.store.workflow(ctx.workflow_id) or {}
                if (wf.get("idempotency") or "workflow") == "workflow":
                    key = "wf-" + digest([ctx.workflow_id, capability, args], 24)
                tool_args = dict(args, idempotency_key=key) if key else dict(args)
            else:
                tool_args = dict(args)
            seq, ordinal = self.store.record_call(**row, effect=decision.effect, rule=decision.rule, approval_id=approval_id, outcome="pending",
                                                  idem_key=key)
            ref = f"ev-{ordinal}"
            t0 = time.perf_counter()
            try:
                result = await self.mcp.call(meta["server"], capability, tool_args, float(self.timeouts[f"{meta['kind']}_s"]))
            except ToolFailed as exc:
                self.store.set_call(seq, outcome="error", error=str(exc)[:500], wall_ms=round((time.perf_counter() - t0) * 1000, 1),
                                    evidence_ref=ref)
                raise
            self.store.set_call(seq, outcome="ok", wall_ms=round((time.perf_counter() - t0) * 1000, 1), evidence_ref=ref)
            annotate(**{"c1.evidence_ref": ref, "c1.idem_key": key})
            return {"evidence_ref": ref, "result": result}

    def _approve(self, workflow_id: str, capability: str, args: dict[str, Any], role: str) -> str:
        d = digest({"wf": workflow_id, "capability": capability, "args": args})
        approval_id = f"apr-{d[:16]}"
        with span("approval", **{"c1.workflow_id": workflow_id, "c1.approval.digest": d, "c1.approver": APPROVER}):
            self.store.execute("INSERT OR IGNORE INTO approvals VALUES (?,?,?,?,?,?,?,?,?)",
                               (approval_id, workflow_id, capability, canon(args), d, APPROVER, role, "APPROVED", time.time()))
        return approval_id


class GatewayTools:
    """The ToolPort an agent loop gets: a fixed list of capabilities, called with one token, results as JSON text."""

    def __init__(self, gateway: Gateway, token: Token, names: list[str], ctx: CallContext):
        self.gateway, self.token, self.names, self.ctx = gateway, token, names, ctx

    def definitions(self) -> list[dict[str, Any]]:
        return self.gateway.tool_definitions(self.names)

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        if name not in self.names:
            return json.dumps({"error": f"unknown tool {name}; available: {', '.join(self.names)}"})
        try:
            return json.dumps(await self.gateway.call(self.token, name, arguments, self.ctx), separators=(",", ":"))
        except GatewayError as exc:
            return json.dumps({"error": str(exc)})
