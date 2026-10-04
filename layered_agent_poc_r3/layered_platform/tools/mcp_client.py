"""The platform's one MCP client: a stdio session per enterprise MCP server.  The only module that imports `mcp`."""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from typing import Any

import mcp_types as types
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.shared.exceptions import MCPError

from layered_platform.config import ROOT


class ToolTimeout(TimeoutError):
    pass


class ToolFailed(RuntimeError):
    pass


class McpClientPool:
    def __init__(self, servers: list[str], world_db: str):
        self.servers, self.world_db = servers, world_db
        self._stack: AsyncExitStack | None = None
        self.clients: dict[str, Client] = {}
        self.tools: dict[tuple[str, str], types.Tool] = {}

    async def start(self) -> None:
        env = dict(os.environ, PYTHONPATH=str(ROOT), F2_WORLD_DB=self.world_db)
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        for server in self.servers:
            params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_servers", server], env=env, cwd=str(ROOT))
            client = await self._stack.enter_async_context(Client(params))
            self.clients[server] = client
            for tool in (await client.list_tools()).tools:
                self.tools[(server, tool.name)] = tool

    async def close(self) -> None:
        if self._stack:
            await self._stack.__aexit__(None, None, None)
            self._stack = None

    def describe(self, server: str, tool: str) -> tuple[str, dict[str, Any]]:
        t = self.tools[(server, tool)]
        return t.description or "", t.input_schema

    async def call(self, server: str, tool: str, arguments: dict[str, Any], timeout_s: float) -> Any:
        try:
            result = await self.clients[server].call_tool(tool, arguments, read_timeout_seconds=timeout_s)
        except MCPError as exc:
            if "timed out" in str(exc).lower():
                raise ToolTimeout(f"{server}.{tool} timed out after {timeout_s}s") from exc
            raise ToolFailed(f"{server}.{tool}: {exc}") from exc
        text = "".join(c.text for c in result.content if isinstance(c, types.TextContent))
        if result.is_error:
            raise ToolFailed(text)
        try:
            return json.loads(text)
        except ValueError:
            return text
