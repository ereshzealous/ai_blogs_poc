"""The incident agent a competent engineer would build first: one class, one run() loop, everything inside it.

It is deliberately not a strawman.  It uses the same MCP servers, the same model, the same runbook and the same past
incident notes as the layered platform.  It gates production writes behind an approval callback in code (not in the
prompt), retries reads that time out, keeps a session history on disk, and writes a structured trace log.  It works.

What it does not have is a place for each of those concerns: the model client, the prompt, the tool plumbing, the
approval rule, the session store and the tracing all live in this file and share one control flow.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import httpx
import mcp_types as types
import yaml
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.shared.exceptions import MCPError

import crashpoints
from recordreplay.tape import transport_from_env

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "simulated_enterprise" / "data"

# ---- model -----------------------------------------------------------------------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = "gpt-oss:20b"
THINK: Any = "low"                  # gpt-oss takes low/medium/high
SEED = int(os.environ.get("F2_SEED", "7"))
TEMPERATURE = 0.0
NUM_CTX = 16384
MAX_TURNS = 16

# ---- tools -----------------------------------------------------------------------------------------------------------
SERVERS = ["itsm", "observability", "deploy"]
TOOL_TIMEOUT_S = float(os.environ.get("F2_TOOL_TIMEOUT_S", "5"))
READ_RETRIES = 2
NEEDS_APPROVAL = {"rollback_release", "restart_service", "scale_service"}   # production changes

SYSTEM_PROMPT = """You are the on-call SRE agent for an online store.  You investigate incidents with the tools you have
and remediate them safely.

Procedure:
1. Load the incident.
2. Investigate: releases of the affected service, its metrics (latency_p95_ms, error_rate_pct, db_pool_wait_ms, cpu_pct)
   and its logs.  Check that dependencies are healthy before blaming them.
3. Decide the root cause and the release that introduced it.
4. Remediate with the smallest safe action the runbook allows.  Production changes are gated by an approval step that
   the platform runs for you when you call the tool; if it is refused, stop and report.
5. Verify: query latency_p95_ms for the last 3 minutes; it must be below the SLO.
6. Update the incident: status "mitigated", with a note giving the root cause, the action and the verification.
7. Finish with a short report that has the lines "Root cause:", "Action:" and "Verification:".

Runbook for the affected service:
{runbook}

What we remember from earlier incidents:
{memory}
"""


def _load_runbook(service: str) -> str:
    code = {"checkout-api": "RB-CHK-007", "payment-gateway": "RB-PAY-002"}.get(service, "RB-CHK-007")
    return (DATA / "runbooks" / f"{code}.md").read_text()


def _load_memory(service: str) -> str:
    items = yaml.safe_load((DATA / "memory_seed.yaml").read_text())
    return "\n".join(f"- {m['text']} (source: {m['source']})" for m in items if m["subject"] == service)


Approver = Callable[[str, dict[str, Any]], Awaitable[bool]]


async def deny_all(tool: str, args: dict[str, Any]) -> bool:
    return False


class IncidentAgent:
    def __init__(self, session_id: str | None = None, approver: Approver = deny_all, workdir: str | Path = ".",
                 world_db: str | Path | None = None, service: str = "checkout-api"):
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.approver = approver
        self.workdir = Path(workdir)
        self.world_db = str(world_db or os.environ.get("F2_WORLD_DB", "world.db"))
        self.service = service
        self.sessions = self.workdir / "sessions"
        self.sessions.mkdir(parents=True, exist_ok=True)
        self.log_path = self.workdir / "agent.log.jsonl"
        transport = transport_from_env()
        self.http = httpx.AsyncClient(timeout=300, transport=transport) if transport else httpx.AsyncClient(timeout=300)
        self.clients: dict[str, Client] = {}
        self.tool_server: dict[str, str] = {}
        self.tools: list[dict[str, Any]] = []
        self.usage = {"model_calls": 0, "prompt_tokens": 0, "completion_tokens": 0}

    # ---- the one entry point -----------------------------------------------------------------------------------------
    async def run(self, user_message: str) -> str:
        self._log("run_start", message=user_message)
        async with AsyncExitStack() as stack:
            await self._connect(stack)
            history = self._load_session()
            system = SYSTEM_PROMPT.format(runbook=_load_runbook(self.service), memory=_load_memory(self.service))
            messages: list[dict[str, Any]] = [{"role": "system", "content": system}, *history, {"role": "user", "content": user_message}]
            final = ""
            for _turn in range(MAX_TURNS):
                reply = await self._chat(messages)
                msg = reply["message"]
                messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
                calls = msg.get("tool_calls") or []
                if not calls:
                    final = msg.get("content", "").strip()
                    break
                for call in calls:
                    name = call["function"]["name"]
                    args = call["function"].get("arguments") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except ValueError:
                            args = {}
                    result = await self._execute_tool(name, args)
                    messages.append({"role": "tool", "tool_name": name, "content": result})
            else:
                final = "Stopped: turn limit reached before the incident was resolved."
            self._save_session(history + [{"role": "user", "content": user_message}, {"role": "assistant", "content": final}])
        self._log("run_end", usage=self.usage)
        return self._format(final)

    # ---- model -------------------------------------------------------------------------------------------------------
    async def _chat(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        body = {"model": MODEL, "messages": messages, "tools": self.tools, "stream": False, "think": THINK,
                "options": {"temperature": TEMPERATURE, "seed": SEED, "num_ctx": NUM_CTX}}
        for attempt in range(3):
            try:
                resp = await self.http.post(f"{OLLAMA_URL}/api/chat", json=body, headers={"x-f2-caller": "monolith"})
                resp.raise_for_status()
                data = resp.json()
                break
            except httpx.HTTPError as exc:
                self._log("model_error", attempt=attempt, error=str(exc))
                if attempt == 2:
                    raise
                await asyncio.sleep(2 * (attempt + 1))
        self.usage["model_calls"] += 1
        self.usage["prompt_tokens"] += data.get("prompt_eval_count", 0)
        self.usage["completion_tokens"] += data.get("eval_count", 0)
        self._log("model_call", model=MODEL, prompt_tokens=data.get("prompt_eval_count", 0), completion_tokens=data.get("eval_count", 0),
                  tool_calls=[c["function"]["name"] for c in data["message"].get("tool_calls") or []])
        return data

    # ---- tools -------------------------------------------------------------------------------------------------------
    async def _connect(self, stack: AsyncExitStack) -> None:
        env = dict(os.environ, PYTHONPATH=str(ROOT), F2_WORLD_DB=self.world_db)
        for server in SERVERS:
            params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_servers", server], env=env, cwd=str(ROOT))
            client = await stack.enter_async_context(Client(params))
            self.clients[server] = client
            for tool in (await client.list_tools()).tools:
                self.tool_server[tool.name] = server
                self.tools.append({"type": "function", "function": {"name": tool.name, "description": tool.description or "",
                                                                     "parameters": tool.input_schema}})

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
        if name not in self.tool_server:
            return f"Error: unknown tool {name}"
        if name in NEEDS_APPROVAL and args.get("environment") == "production":
            crashpoints.hit("awaiting_approval")
            approved = await self.approver(name, args)
            self._log("approval", tool=name, args=args, approved=approved)
            if not approved:
                return f"Error: {name} was not approved by the incident commander. Do not retry; report instead."
        attempts = 1 if name in NEEDS_APPROVAL or name == "update_incident" else 1 + READ_RETRIES
        for attempt in range(attempts):
            t0 = time.perf_counter()
            try:
                result = await self.clients[self.tool_server[name]].call_tool(name, args, read_timeout_seconds=TOOL_TIMEOUT_S)
            except MCPError as exc:
                self._log("tool_call", tool=name, args=args, ok=False, error=str(exc), attempt=attempt, wall_s=round(time.perf_counter() - t0, 3))
                if "timed out" in str(exc).lower() and attempt + 1 < attempts:
                    continue
                return f"Error: {name} failed: {exc}"
            text = "".join(c.text for c in result.content if isinstance(c, types.TextContent))
            self._log("tool_call", tool=name, args=args, ok=not result.is_error, attempt=attempt, wall_s=round(time.perf_counter() - t0, 3))
            crashpoints.hit(f"after_tool_result:{name}")
            return f"Error: {text}" if result.is_error else text
        return f"Error: {name} failed"

    # ---- session -----------------------------------------------------------------------------------------------------
    def _load_session(self) -> list[dict[str, Any]]:
        path = self.sessions / f"{self.session_id}.json"
        return json.loads(path.read_text()) if path.exists() else []

    def _save_session(self, history: list[dict[str, Any]]) -> None:
        (self.sessions / f"{self.session_id}.json").write_text(json.dumps(history, indent=1))

    # ---- presentation and tracing ------------------------------------------------------------------------------------
    def _format(self, text: str) -> str:
        return f"INC report (session {self.session_id})\n{'=' * 40}\n{text}\n"

    def _log(self, event: str, **fields: Any) -> None:
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.time(), "pid": os.getpid(), "session_id": self.session_id, "event": event, **fields}, default=str) + "\n")

    async def aclose(self) -> None:
        await self.http.aclose()
