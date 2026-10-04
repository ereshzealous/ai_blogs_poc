"""One REAL MCP server process (official Python SDK, low-level Server, stdio transport).

    python -m sprawl_poc.servers.serve --spec estate/servers/refunds.json --db work.db [--enforce-gateway-token]

The spec holds only what the server publishes over MCP (tool name, description,
inputSchema, annotations) plus which simulated handler backs each tool.  Governance
metadata is NOT here — servers never see the platform registry.

With ``--enforce-gateway-token`` (control-plane arm), every ``tools/call`` must carry
``_meta["io.sprawl-poc/gateway"] = {"invocation_id", "mac"}`` where ``mac`` is an
HMAC-SHA256 over the canonical (server.tool, arguments, invocation_id) under a key
only the gateway process holds (passed via SPRAWL_GATEWAY_KEY).  Tokens are single-use.
This lets the POC *test* bypass resistance instead of asserting it; key management
itself is out of scope (Identity & Security learnings).
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import sys
import time
from hashlib import sha256
from pathlib import Path
from typing import Any

import anyio
import mcp_types as types
from jsonschema import Draft202012Validator
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from ..util import canonical_json
from ..world.db import connect
from ..world.handlers import HANDLERS, ServerCtx, ToolError

GATEWAY_META_KEY = "io.sprawl-poc/gateway"
IDEMPOTENCY_META_KEY = "io.sprawl-poc/idempotency-key"


def gateway_mac(key: bytes, implementation: str, arguments: dict[str, Any], invocation_id: str) -> str:
    msg = canonical_json({"implementation": implementation, "arguments": arguments, "invocation_id": invocation_id})
    return hmac.new(key, msg.encode(), sha256).hexdigest()


def build_server(spec: dict[str, Any], db_path: Path, enforce: bool, key: bytes | None) -> Server:
    name = spec["server"]
    tools = [
        types.Tool(
            name=t["name"],
            description=t["description"],
            input_schema=t["inputSchema"],
            annotations=types.ToolAnnotations(**t["annotations"]) if t.get("annotations") else None,
        )
        for t in spec["tools"]
    ]
    handler_ids = {t["name"]: t["handler"] for t in spec["tools"]}
    validators = {t["name"]: Draft202012Validator(t["inputSchema"]) for t in spec["tools"]}

    async def on_list_tools(ctx, params):
        # 2026-07-28 (SEP-2549): tools/list results carry ttlMs + cacheScope; this catalog has no per-user data.
        return types.ListToolsResult(tools=tools, ttl_ms=300000, cache_scope="public")

    def _error(text: str) -> types.CallToolResult:
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=True)

    async def on_call_tool(ctx, params: types.CallToolRequestParams):
        tool = params.name
        args = dict(params.arguments or {})
        if tool not in handler_ids:
            return _error(f"unknown tool {tool}")
        meta = dict(params.meta) if params.meta else {}
        gw = meta.get(GATEWAY_META_KEY) if isinstance(meta.get(GATEWAY_META_KEY), dict) else None
        invocation_id = gw.get("invocation_id") if gw else None
        verified = False
        if gw and key and invocation_id:
            expected = gateway_mac(key, f"{name}.{tool}", args, invocation_id)
            verified = hmac.compare_digest(expected, str(gw.get("mac", "")))
        if enforce and not verified:
            return _error("REJECTED_BY_SERVER: missing or invalid gateway token; this server only accepts gateway-mediated calls")
        # MCP spec (tools, security considerations): servers MUST validate all tool inputs.
        errors = sorted(e.message for e in validators[tool].iter_errors(args))
        if errors:
            return _error("invalid arguments: " + "; ".join(errors))
        sctx = ServerCtx(name, spec["environment"], spec.get("region", "global"), tool, invocation_id, verified)
        idem = meta.get(IDEMPOTENCY_META_KEY) if isinstance(meta.get(IDEMPOTENCY_META_KEY), str) else None
        if idem:  # same key, same tool: return the first result instead of executing again
            with connect(db_path) as con:
                prev = con.execute("SELECT result FROM idempotency WHERE key=? AND tool=?", (idem, f"{name}.{tool}")).fetchone()
            if prev is not None:
                stored = json.loads(prev["result"])
                return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(stored, sort_keys=True))],
                                            structured_content={**stored, "idempotent_replay": True})
        try:
            if enforce:  # burn the token first, in its own transaction, so even a failed call cannot be replayed
                with connect(db_path) as con:
                    if con.execute("SELECT 1 FROM used_invocations WHERE invocation_id=?", (invocation_id,)).fetchone():
                        raise ToolError("REJECTED_BY_SERVER: gateway token already used (replay)")
                    con.execute("INSERT INTO used_invocations VALUES (?, ?)", (invocation_id, time.time()))
            with connect(db_path) as con:  # SIMULATED outage of this system (fault injection for the benchmark)
                fault = con.execute("SELECT remaining, message FROM faults WHERE target=?", (f"{name}.{tool}",)).fetchone()
                if fault is not None and fault["remaining"] > 0:
                    con.execute("UPDATE faults SET remaining = remaining - 1 WHERE target=?", (f"{name}.{tool}",))
            if fault is not None and fault["remaining"] > 0:
                return _error(fault["message"])
            with connect(db_path) as con:
                result = HANDLERS[handler_ids[tool]](con, sctx, args)
                if idem:
                    con.execute("INSERT INTO idempotency(key, tool, result) VALUES (?,?,?)", (idem, f"{name}.{tool}", json.dumps(result, sort_keys=True)))
        except ToolError as e:
            return _error(str(e))
        except Exception as e:  # one bad call must fail that call, never the server or the run
            return _error(f"internal error in {name}.{tool}: {type(e).__name__}: {e}")
        try:
            text = json.dumps(result, sort_keys=True)
        except (TypeError, ValueError) as e:
            return _error(f"internal error: result not JSON-encodable: {e}")
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)], structured_content=result)

    return Server(name, version=spec.get("version", "1.0.0"), on_list_tools=on_list_tools, on_call_tool=on_call_tool)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--enforce-gateway-token", action="store_true")
    ns = ap.parse_args(argv)
    spec = json.loads(Path(ns.spec).read_text())
    key = os.environ.get("SPRAWL_GATEWAY_KEY")
    server = build_server(spec, Path(ns.db), ns.enforce_gateway_token, key.encode() if key else None)

    async def run() -> None:
        async with stdio_server() as (r, w):
            await server.run(r, w, server.create_initialization_options())

    try:
        anyio.run(run)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
