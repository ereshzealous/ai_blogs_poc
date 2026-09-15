"""Generic, data-driven MCP server runtime.

Every server in this repository, hand-written or generated, runs through this module:

    python -m servers.common.runtime --server observability --manifest benchmark/catalogs/catalog_500.json

It speaks real MCP over stdio using the official Python SDK's low-level server: `tools/list` with
cursor pagination, and `tools/call` with JSON Schema validation. Tool behaviour comes from the
deterministic mock backends registered in `servers/*_mcp/backend.py`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import anyio
import mcp.server.stdio
import mcp_types as types
from jsonschema import Draft202012Validator
from mcp.server.lowlevel import Server

from servers.common.handlers import Ctx, resolve
from servers.common.toolspec import ToolSpec
from servers.common.world import World

PAGE_SIZE = 20  # servers with more tools answer tools/list in several pages, as real ones do
LIST_TTL_MS = 300_000


def load_manifest(path: str | Path, server_key: str) -> list[ToolSpec]:
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    return [ToolSpec.from_manifest(t) for t in manifest["tools"] if t["server"] == server_key]


def _error(message: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=message)], is_error=True)


def build_server(server_key: str, specs: list[ToolSpec], world: World | None = None) -> Server[Any]:
    world = world or World()
    by_name = {s.name: s for s in specs}
    validators = {s.name: Draft202012Validator(s.input_schema) for s in specs}
    tools = [s.to_mcp() for s in specs]

    async def list_tools(ctx: Any, params: types.PaginatedRequestParams | None) -> types.ListToolsResult:
        start = int(params.cursor) if params is not None and params.cursor else 0
        end = start + PAGE_SIZE
        return types.ListToolsResult(
            tools=tools[start:end],
            next_cursor=str(end) if end < len(tools) else None,
            ttl_ms=LIST_TTL_MS,
            cache_scope="public",
        )

    async def call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        spec = by_name.get(params.name)
        if spec is None:
            return _error(f"Unknown tool: {params.name}")
        args = dict(params.arguments or {})
        problems = sorted(validators[spec.name].iter_errors(args), key=lambda e: list(e.path))
        if problems:
            return _error("Invalid arguments: " + "; ".join(p.message for p in problems[:3]))
        run_id = str((params.meta or {}).get("run_id", "default"))
        try:
            result = resolve(spec.handler)(Ctx(world, run_id, server_key, spec), args)
        except LookupError as exc:
            return _error(str(exc))
        except KeyError as exc:
            return _error(f"Missing required argument for this backend: {exc.args[0]}")
        text = json.dumps(result, separators=(",", ":"), sort_keys=False)
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)], structured_content=result)

    return Server(
        f"{server_key.replace('_', '-')}-mcp",
        version="1.0.0",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--server", required=True, help="server key, e.g. observability")
    parser.add_argument("--manifest", required=True, help="catalog manifest JSON produced by the catalog generator")
    args = parser.parse_args()
    specs = load_manifest(args.manifest, args.server)
    server = build_server(args.server, specs)

    async def serve() -> None:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    anyio.run(serve)


if __name__ == "__main__":
    main()
