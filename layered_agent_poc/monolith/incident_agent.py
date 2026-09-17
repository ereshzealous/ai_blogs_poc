"""incident_agent.py: our first incident agent. It works, and for one bounded use case it is fine.

Everything lives in this class: the prompt, the Ollama call and its model-specific options, the conversation
("memory"), the MCP clients, the tool list, the approval rule, retries and logging. The platform version of the same
capability is in `agent_platform/`; this file is the baseline the article compares against.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from typing import Any

import httpx
import mcp_types as types
import traffic
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.shared.exceptions import MCPError

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = "gpt-oss:20b"
SERVERS = ("itsm", "source_control", "observability", "database", "kubernetes")
WRITE_TOOLS = {"rollback_release", "rollback_deployment", "update_incident"}

SYSTEM_PROMPT = """You are an incident response agent for our production systems.
Investigate incidents with the tools, find the root cause, fix it, verify, and update the incident.
Rules:
- Production changes need a human OK. The platform will ask the user when you call a write tool.
- Prefer rolling back a bad release.
- Update the incident with the cause, the action and the verification at the end.
Be concise."""

log = logging.getLogger("incident_agent")

Approver = Callable[[str, dict[str, Any]], Awaitable[bool]]


async def ask_on_terminal(tool: str, args: dict[str, Any]) -> bool:
    answer = await asyncio.to_thread(input, f"\nThe agent wants to run {tool} {json.dumps(args)}. Approve? [y/N] ")
    return answer.strip().lower().startswith("y")


class IncidentAgent:
    def __init__(self, model: str = MODEL, approver: Approver = ask_on_terminal, user: str = "alice"):
        self.model = model
        self.approver = approver
        self.tape = traffic.from_env()  # recorded or replayed model traffic (LAP_MODEL_TRAFFIC)
        self.user = user
        self.history: list[dict[str, Any]] = []  # our "memory"
        self.clients: dict[str, Client] = {}
        self.tools: list[dict[str, Any]] = []
        self.token_count = 0
        self._stack: AsyncExitStack | None = None

    # -- setup ------------------------------------------------------------------------------------
    async def connect(self) -> None:
        env = dict(os.environ)
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        for server in SERVERS:
            params = StdioServerParameters(command=sys.executable, args=["-m", "mock_enterprise", server], env=env)
            client = await self._stack.enter_async_context(Client(params))
            self.clients[server] = client
            for tool in (await client.list_tools()).tools:
                schema = dict(tool.input_schema)
                schema["properties"] = {k: v for k, v in schema.get("properties", {}).items() if k != "idempotency_key"}
                self.tools.append({"type": "function", "function": {
                    "name": f"{server}__{tool.name}", "description": tool.description or "", "parameters": schema}})
        log.info("connected to %d servers, %d tools", len(self.clients), len(self.tools))

    async def close(self) -> None:
        if self._stack:
            await self._stack.__aexit__(None, None, None)

    # -- the model ---------------------------------------------------------------------------------
    async def chat(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        body = {"model": self.model, "messages": messages, "tools": self.tools, "stream": False,
                "think": "low",  # gpt-oss reasoning effort
                "options": {"temperature": 0, "seed": 7, "num_ctx": 32768}}
        tape = self.tape
        request = {"model": self.model, "messages": messages, "tools": sorted(t["function"]["name"] for t in self.tools),
                   "structured": False}
        if tape and tape.mode == "replay":
            data, _ = tape.replay_chat("monolith", self.model, request)
        else:
            t0 = time.perf_counter()
            async with httpx.AsyncClient(timeout=240) as http:
                resp = await http.post(f"{OLLAMA_URL}/api/chat", json=body)
                resp.raise_for_status()
                data = resp.json()
            if tape:
                tape.record_chat("monolith", self.model, request, data, (time.perf_counter() - t0) * 1000)
        self.token_count += int(data.get("prompt_eval_count") or 0) + int(data.get("eval_count") or 0)
        return data["message"]

    # -- tools -------------------------------------------------------------------------------------
    async def call_tool(self, name: str, args: dict[str, Any], retries: int = 3) -> str:
        server, tool = name.split("__", 1)
        for attempt in range(1, retries + 1):
            try:
                result = await self.clients[server].call_tool(tool, args, read_timeout_seconds=2)
                return "".join(c.text for c in result.content if isinstance(c, types.TextContent))
            except MCPError as exc:
                if "timed out" in str(exc) and attempt < retries:
                    log.warning("%s timed out, retrying (%d/%d)", name, attempt, retries)
                    await asyncio.sleep(0.5)
                    continue
                log.error("agent failed: %s", exc)
                return f"error: {exc}"
        return "error: retries exhausted"

    # -- the loop ------------------------------------------------------------------------------------
    async def run(self, request: str, max_turns: int = 20) -> str:
        self.history.append({"role": "user", "content": f"[{self.user}] {request}"})
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self.history
        for _ in range(max_turns):
            msg = await self.chat(messages)
            calls = msg.get("tool_calls") or []
            messages.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": calls})
            if not calls:
                self.history.append({"role": "assistant", "content": msg.get("content", "")})
                return msg.get("content", "")
            for call in calls:
                name, args = call["function"]["name"], call["function"].get("arguments") or {}
                tool = name.split("__", 1)[-1]
                if tool in WRITE_TOOLS and args.get("environment", "production") == "production" and tool != "update_incident":
                    if not await self.approver(name, args):
                        result = "The user did not approve this action."
                    else:
                        result = await self.call_tool(name, args)
                else:
                    result = await self.call_tool(name, args)
                log.info("tool %s(%s) -> %s", name, json.dumps(args)[:120], result[:160])
                messages.append({"role": "tool", "tool_name": name, "content": result[:2400]})
        log.error("agent failed: too many turns")
        return "I could not finish the investigation."
