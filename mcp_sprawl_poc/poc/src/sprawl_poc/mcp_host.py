"""Host side of the REAL MCP boundary: launch every server in an estate as its own stdio
process, run the protocol handshake/discovery, page through ``tools/list``, and route
``tools/call``.

Records, per server, the negotiated protocol revision *as measured on the live
connection* (``Client.protocol_version``), the SDK version, and the connect mode.
"""

from __future__ import annotations

import importlib.metadata
import json
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
from mcp import Client
from mcp.client.stdio import StdioServerParameters

SEP = "__"
CALL_TIMEOUT_S = 30.0  # host-side namespacing: <server>__<tool>; tool names collide across servers


@dataclass(frozen=True)
class ToolInfo:
    server: str
    tool: str
    description: str
    input_schema: dict[str, Any]
    annotations: dict[str, Any] | None

    @property
    def qualified(self) -> str:
        return f"{self.server}.{self.tool}"

    @property
    def model_name(self) -> str:
        return f"{self.server}{SEP}{self.tool}"

    def ollama_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.model_name, "description": self.description, "parameters": self.input_schema},
        }


@dataclass
class CallOutcome:
    is_error: bool
    text: str
    structured: dict[str, Any] | None
    wall_s: float
    transport_error: str | None = None

    def as_record(self) -> dict[str, Any]:
        return {"is_error": self.is_error, "text": self.text[:4000], "structured": self.structured, "wall_s": round(self.wall_s, 4), "transport_error": self.transport_error}


@dataclass
class ServerConnection:
    name: str
    client: Client
    protocol_version: str
    server_info: dict[str, Any] | None
    tools: list[ToolInfo] = field(default_factory=list)


class Estate:
    """All MCP servers of one estate, connected over stdio."""

    def __init__(self, estate_dir: Path, db_path: Path, *, enforce_gateway_token: bool, gateway_key: str, mode: str = "auto"):
        self.estate_dir = Path(estate_dir)
        self.db_path = Path(db_path)
        self.enforce = enforce_gateway_token
        self.gateway_key = gateway_key
        self.mode = mode
        self.connections: dict[str, ServerConnection] = {}
        self.tools: dict[str, ToolInfo] = {}  # qualified -> info
        self.by_model_name: dict[str, ToolInfo] = {}
        self._stack: AsyncExitStack | None = None
        self.connect_s: float = 0.0

    async def __aenter__(self) -> "Estate":
        t0 = time.time()
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        specs = sorted((self.estate_dir / "servers").glob("*.json"))
        for spec_path in specs:
            spec = json.loads(spec_path.read_text())
            args = ["-m", "sprawl_poc.servers.serve", "--spec", str(spec_path), "--db", str(self.db_path)]
            if self.enforce:
                args.append("--enforce-gateway-token")
            params = StdioServerParameters(
                command=sys.executable,
                args=args,
                env={"SPRAWL_GATEWAY_KEY": self.gateway_key, "PATH": "/usr/bin:/bin", "PYTHONUNBUFFERED": "1"},
            )
            client = Client(params, mode=self.mode, cache=None)
            await self._stack.enter_async_context(client)
            info = client.server_info.model_dump(exclude_none=True) if client.server_info else None
            conn = ServerConnection(spec["server"], client, client.protocol_version, info)
            cursor = None
            while True:
                page = await client.list_tools(cursor=cursor)
                for t in page.tools:
                    ann = t.annotations.model_dump(by_alias=True, exclude_none=True) if t.annotations else None
                    ti = ToolInfo(spec["server"], t.name, t.description or "", dict(t.input_schema), ann)
                    conn.tools.append(ti)
                    self.tools[ti.qualified] = ti
                    self.by_model_name[ti.model_name] = ti
                cursor = page.next_cursor
                if not cursor:
                    break
            self.connections[spec["server"]] = conn
        self.connect_s = time.time() - t0
        return self

    async def __aexit__(self, *exc) -> None:
        if self._stack is not None:
            await self._stack.__aexit__(*exc)
            self._stack = None

    async def call(self, qualified: str, arguments: dict[str, Any], meta: dict[str, Any] | None = None) -> CallOutcome:
        server, tool = qualified.split(".", 1)
        conn = self.connections[server]
        t0 = time.time()
        try:
            with anyio.fail_after(CALL_TIMEOUT_S):
                r = await conn.client.call_tool(tool, arguments, meta=meta)
        except TimeoutError:
            return CallOutcome(True, f"MCP call timed out after {CALL_TIMEOUT_S}s", None, time.time() - t0, transport_error="timeout")
        except Exception as e:  # protocol/transport failure — recorded, never retried silently
            return CallOutcome(True, f"MCP call failed: {type(e).__name__}: {e}", None, time.time() - t0, transport_error=repr(e))
        text = "\n".join(getattr(c, "text", "") for c in r.content)
        return CallOutcome(bool(r.is_error), text, r.structured_content, time.time() - t0)

    def protocol_record(self) -> dict[str, Any]:
        versions = sorted({c.protocol_version for c in self.connections.values()})
        return {
            "sdk_package": "mcp",
            "sdk_version": importlib.metadata.version("mcp"),
            "mcp_types_version": importlib.metadata.version("mcp-types"),
            "server_api": "mcp.server.lowlevel.Server (on_list_tools / on_call_tool) over mcp.server.stdio.stdio_server",
            "client_api": "mcp.Client(StdioServerParameters, mode=%r, cache=None)" % self.mode,
            "transport": "stdio (one OS process per server)",
            "connect_mode": self.mode,
            "negotiated_protocol_versions": versions,
            "servers": {n: c.protocol_version for n, c in sorted(self.connections.items())},
            "server_count": len(self.connections),
            "tool_count": len(self.tools),
            "connect_s": round(self.connect_s, 2),
        }
