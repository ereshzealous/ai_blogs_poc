"""MCP client pool: one stdio client per enterprise MCP server. The only module that speaks MCP."""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import mcp_types as types
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.shared.exceptions import MCPError

from agent_platform.config import ROOT

SERVERS = ("itsm", "source_control", "observability", "database", "kubernetes")


class ToolTimeout(TimeoutError):
    pass


class ToolFailed(RuntimeError):
    pass


class McpPool:
    def __init__(self, enterprise_db: Path):
        self.enterprise_db = enterprise_db
        self._stack: AsyncExitStack | None = None
        self.clients: dict[str, Client] = {}
        self.tools: dict[str, types.Tool] = {}  # tool_id -> MCP tool

    async def start(self) -> None:
        env = dict(os.environ, PYTHONPATH=str(ROOT), LAP_ENTERPRISE_DB=str(self.enterprise_db))
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        for server in SERVERS:
            params = StdioServerParameters(command=sys.executable, args=["-m", "mock_enterprise", server], env=env, cwd=str(ROOT))
            client = await self._stack.enter_async_context(Client(params))
            self.clients[server] = client
            listed = await client.list_tools()
            for tool in listed.tools:
                self.tools[f"{server}.{tool.name}"] = tool

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.__aexit__(None, None, None)
            self._stack = None

    def schema(self, tool_id: str) -> dict[str, Any]:
        return self.tools[tool_id].input_schema

    def description(self, tool_id: str) -> str:
        return self.tools[tool_id].description or ""

    async def call(self, tool_id: str, arguments: dict[str, Any], timeout_s: float) -> Any:
        server, name = tool_id.split(".", 1)
        try:
            result = await self.clients[server].call_tool(name, arguments, read_timeout_seconds=timeout_s)
        except MCPError as exc:
            if "timed out" in str(exc):
                raise ToolTimeout(f"{tool_id} timed out after {timeout_s}s") from exc
            raise ToolFailed(f"{tool_id}: {exc}") from exc
        text = "".join(c.text for c in result.content if isinstance(c, types.TextContent))
        if result.is_error:
            raise ToolFailed(text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
