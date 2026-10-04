"""The agent loop and the three experiment arms.

A — all_tools:      every tool definition in the estate is given to the model; calls go
                    straight to the MCP servers.
B — search_only:    a hybrid-retrieval shortlist of K implementations (+ search_tools for
                    progressive loading); calls go straight to the MCP servers.
C — control_plane:  the same retrieval, collapsed to K capabilities; calls go through the
                    gateway (binding, schema, policy, approval, signed execution, audit).

All arms share the same model, prompt text, finish tool, turn limit and simulated world.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

import anyio

from ..control_plane.gateway import Gateway
from ..control_plane.invocation import CallContext
from ..control_plane.context import render_context, resolve_entities
from ..control_plane.resolve import CapabilityResolver, SurfacedCapability, entity_priors, rank_capabilities
from ..discovery.index import ToolIndex
from ..mcp_host import Estate, ToolInfo
from .ollama import ChatResult, ContextOverflow, MalformedToolCall, ModelCallError
from .prompts import FINISH_TOOL, SEARCH_TOOL, system_prompt, user_prompt

FINISH_OUTCOMES = tuple(FINISH_TOOL["function"]["parameters"]["properties"]["outcome"]["enum"])

MAX_MODEL_CALLS = 10  # per phase
MAX_PHASES = 3  # initial request + at most two scripted follow-ups (user answer / correction / approver decision)
MAX_FINISH_REMINDERS = 2
FINISH_REMINDER = "Please call the finish tool now with the outcome and your message for the representative."
SHORTLIST_K = 8
COLLAPSE_DEPTH = 40
RESULT_CHARS = 3000


class ChatClient(Protocol):
    calls: list[dict[str, Any]]

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> ChatResult: ...


@dataclass
class ToolCallRecord:
    step: int
    model_tool: str
    arguments: Any
    kind: str  # finish | search | tool
    implementation: str | None = None  # the MCP tool actually called (A/B) or resolved (C)
    result: dict[str, Any] | None = None
    gateway: dict[str, Any] | None = None

    def as_record(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class Episode:
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    surfaced_per_step: list[list[str]] = field(default_factory=list)
    retrieval: list[dict[str, Any]] = field(default_factory=list)
    declared_outcome: str | None = None
    declared_message: str | None = None
    final_text: str | None = None
    stop_reason: str = "unknown"  # finish | no_tool_call | turn_limit | context_overflow | model_error
    error: dict[str, Any] | None = None
    first_prompt_tokens: int | None = None
    total_prompt_tokens: int = 0
    total_eval_tokens: int = 0
    model_wall_s: float = 0.0
    model_calls: int = 0
    finish_reminders: int = 0
    invalid_finish_calls: int = 0
    rejected_finish_calls: int = 0
    phases: list[dict[str, Any]] = field(default_factory=list)  # closed phases (a finish that triggered a follow-up)
    finish_reminders_by_phase: list[int] = field(default_factory=list)
    thinking_chars: int = 0


class Arm:
    name = "base"
    with_search = False

    def initial_tools(self, request: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def current_tools(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def search(self, query: str) -> dict[str, Any]:
        return {"error": "search not available"}

    async def prepare(self, llm: Any, request: str) -> str | None:
        """Hook before the first model call; may return extra context for the user message."""
        return None

    def validate_finish(self, outcome: str) -> str | None:
        """Hook to reject a finish that contradicts the execution record (control plane only)."""
        return None

    async def on_user_followup(self, text: str) -> str | None:
        """Hook when the requester answers or corrects; may return extra platform context (control plane only)."""
        return None

    async def call(self, name: str, args: dict[str, Any], rec: ToolCallRecord) -> dict[str, Any]:
        raise NotImplementedError

    def surfaced_names(self) -> list[str]:
        return [t["function"]["name"] for t in self.current_tools()]


class _DirectMCP:
    """A/B: the host calls MCP servers directly with whatever the model proposed."""

    estate: Estate

    async def _direct(self, name: str, args: Any, rec: ToolCallRecord, allowed: set[str]) -> dict[str, Any]:
        info = self.estate.by_model_name.get(name)
        if info is None or name not in allowed:
            return {"error": f"unknown tool {name}"}
        rec.implementation = info.qualified
        if not isinstance(args, dict):
            return {"error": "arguments must be a JSON object"}
        out = await self.estate.call(info.qualified, args)
        rec.result = out.as_record()
        if out.is_error:
            return {"error": out.text[:RESULT_CHARS]}
        return out.structured if out.structured is not None else {"result": out.text[:RESULT_CHARS]}


class AllToolsArm(Arm, _DirectMCP):
    name = "A_all_tools"

    def __init__(self, estate: Estate):
        self.estate = estate
        self._tools = [t.ollama_tool() for t in sorted(estate.tools.values(), key=lambda t: t.model_name)] + [FINISH_TOOL]
        self._allowed = set(estate.by_model_name)

    def initial_tools(self, request: str) -> list[dict[str, Any]]:
        return self._tools

    def current_tools(self) -> list[dict[str, Any]]:
        return self._tools

    async def call(self, name, args, rec):
        return await self._direct(name, args, rec, self._allowed)


class SearchOnlyArm(Arm, _DirectMCP):
    name = "B_search_only"
    with_search = True

    def __init__(self, estate: Estate, index: ToolIndex):
        self.estate = estate
        self.index = index
        self._loaded: list[ToolInfo] = []
        self.retrieval_log: list[dict[str, Any]] = []

    def _load(self, query: str, source: str) -> list[str]:
        hits = self.index.search(query, SHORTLIST_K)
        added = []
        for h in hits:
            info = self.estate.tools[h.qualified]
            if info not in self._loaded:
                self._loaded.append(info)
                added.append(info.model_name)
        self.retrieval_log.append({"source": source, "query": query, "hits": [h.__dict__ for h in hits], "added": added})
        return added

    def initial_tools(self, request: str) -> list[dict[str, Any]]:
        self._load(request, "initial")
        return self.current_tools()

    def current_tools(self) -> list[dict[str, Any]]:
        return [t.ollama_tool() for t in self._loaded] + [SEARCH_TOOL, FINISH_TOOL]

    def search(self, query: str) -> dict[str, Any]:
        added = self._load(query, "search_tools")
        return {"added_tools": added, "loaded_tools": [t.model_name for t in self._loaded]}

    async def call(self, name, args, rec):
        return await self._direct(name, args, rec, {t.model_name for t in self._loaded})


PLATFORM_NOTE = ("Platform note: actions that need supervisor approval are held by the platform automatically. "
                 "Propose the exact action with the capability tool; nothing executes until a supervisor approves it.")


class ControlPlaneArm(Arm):
    """C: resolve entities, discover capabilities deterministically, govern every invocation."""

    name = "C_control_plane"
    with_search = True

    def __init__(self, estate: Estate, index: ToolIndex, resolver: CapabilityResolver, gateway: Gateway, ctx: CallContext):
        self.estate = estate
        self.index = index
        self.resolver = resolver
        self.gateway = gateway
        self.ctx = ctx
        self._surfaced: dict[str, SurfacedCapability] = {}
        self.retrieval_log: list[dict[str, Any]] = []
        self.entity_context: dict[str, Any] = {}
        self.entity_types: dict[str, float] = {}
        self.request = ""
        self.results: list[dict[str, Any]] = []  # gateway outcomes this episode (for finish validation)

    def _add(self, caps: list[SurfacedCapability]) -> list[str]:
        added = []
        for c in caps:
            if c.tool_name not in self._surfaced:
                self._surfaced[c.tool_name] = c
                added.append(c.tool_name)
        return added

    def _rank(self, queries: list[str], source: str) -> list[str]:
        query_hits = [(q, self.index.search(q, COLLAPSE_DEPTH)) for q in queries]
        caps, dropped, scores = rank_capabilities(self.resolver, query_hits, self.entity_types, SHORTLIST_K)
        added = self._add(caps)
        self.retrieval_log.append({
            "source": source, "queries": queries, "entity_priors": self.entity_types,
            "hits": {q: [h.__dict__ for h in hits[:15]] for q, hits in query_hits},
            "capabilities": [{"capability": c.capability, "best_rank": c.best_rank, "matched": list(c.matched_implementations)} for c in caps],
            "scores": scores, "dropped": dropped[:20], "added": added,
        })
        return added

    async def prepare(self, llm: Any, request: str) -> str | None:
        self.request = request
        # 1. resolve entities deterministically from systems of record (through the gateway)
        self.entity_context = await resolve_entities(request, self.gateway.context_read)
        self.entity_types = entity_priors([e["type"] for e in self.entity_context.get("entities", [])])
        # 2. deterministic discovery: hybrid retrieval over published metadata, registry collapse, entity prior
        self._rank([request], "initial")
        ctx_block = render_context(self.entity_context)
        return (ctx_block + "\n\n" if ctx_block else "") + PLATFORM_NOTE

    def initial_tools(self, request: str) -> list[dict[str, Any]]:
        if not self._surfaced:  # prepare() not run (should not happen in the harness)
            self._rank([request], "initial")
        return self.current_tools()

    def current_tools(self) -> list[dict[str, Any]]:
        return [c.ollama_tool() for c in self._surfaced.values()] + [SEARCH_TOOL, FINISH_TOOL]

    def search(self, query: str) -> dict[str, Any]:
        added = self._rank([query], "search_tools")
        return {"added_tools": added, "loaded_tools": list(self._surfaced)}

    async def on_user_followup(self, text: str) -> str | None:
        # the requester's own words ground requester-owned values; newly referenced entities are resolved too
        self.request = f"{self.request}\n{text}"
        extra = await resolve_entities(text, self.gateway.context_read)
        if extra.get("entities"):
            self.entity_context.setdefault("entities", []).extend(extra["entities"])
        return render_context(extra)

    def validate_finish(self, outcome: str) -> str | None:
        writes = [r for r in self.results if r["write"]]
        if outcome == "needs_approval":
            if any(r["status"] == "APPROVAL_REQUIRED" for r in writes):
                return None
            return ("The approval system has no request for this. Propose the exact action with the capability tool; "
                    "the platform routes it to a supervisor and nothing executes until it is approved.")
        if outcome != "completed":
            return None
        executed = [r for r in writes if r["status"] == "EXECUTED"]
        if executed:
            return None
        if any(r["status"] == "APPROVAL_REQUIRED" for r in writes):
            return "The audit record shows an approval request and no executed write. The outcome must be needs_approval."
        if writes:
            return ("The audit record shows no executed write for this request, so completed is not supported. "
                    "Finish with refused, needs_clarification or needs_approval as the tool results indicate.")
        return None

    async def call(self, name, args, rec):
        if not isinstance(args, dict):
            return {"error": "arguments must be a JSON object"}
        result, trace = await self.gateway.handle(name, args, self.ctx, self._surfaced, self.request)
        rec.gateway = trace.as_record()
        rec.implementation = trace.implementation
        rec.result = {"status": result.get("status"), "stage": trace.stage_reached}
        cap = self.gateway.registry.capabilities.get(trace.capability or "")
        impl = trace.implementation or (next(iter(cap.authoritative.values())) if cap else None)
        irec = self.gateway.registry.get(impl) if impl else None
        write = (irec.side_effect != "none") if irec else trace.proposal_kind != "unknown"
        self.results.append({"tool": name, "status": result.get("status"), "write": write})
        return result


def _parse_args(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return raw


FollowUp = Callable[[str, str], Awaitable[str | None]]


async def run_episode(llm: ChatClient, arm: Arm, *, nonce: str, requester_name: str, role: str, request: str,
                      on_finish: FollowUp | None = None) -> Episode:
    """Run one conversation. ``on_finish(outcome, message)`` may return a follow-up user/approver message
    (clarification answer, correction, approval decision); the conversation then continues in a new phase."""
    ep = Episode()
    extra = await arm.prepare(llm, request)
    user = user_prompt(requester_name, role, request) + (f"\n\n{extra}" if extra else "")
    ep.messages = [
        {"role": "system", "content": system_prompt(nonce, arm.with_search)},
        {"role": "user", "content": user},
    ]
    tools = arm.initial_tools(request)
    phase_calls = 0
    for step in range(MAX_MODEL_CALLS * MAX_PHASES):
        if phase_calls >= MAX_MODEL_CALLS:
            ep.stop_reason = "turn_limit"
            break
        phase_calls += 1
        ep.surfaced_per_step.append([t["function"]["name"] for t in tools])
        try:
            res = await anyio.to_thread.run_sync(llm.chat, ep.messages, tools)
        except ContextOverflow as e:
            ep.stop_reason = "context_overflow"
            ep.error = {"class": "context_overflow", "n_prompt_tokens": e.n_prompt_tokens, "n_ctx": e.n_ctx}
            if ep.first_prompt_tokens is None:
                ep.first_prompt_tokens = e.n_prompt_tokens
            break
        except MalformedToolCall as e:
            # Same request + fixed seed would reproduce the same malformed output; the episode ends as a model failure.
            ep.stop_reason = "malformed_tool_call"
            ep.error = {"class": "model_output", "detail": str(e)[:500]}
            break
        except ModelCallError as e:
            ep.stop_reason = "model_error"
            ep.error = {"class": "infrastructure", "detail": str(e)[:500]}
            break
        ep.model_calls += 1
        ep.model_wall_s += res.wall_s
        if ep.first_prompt_tokens is None:
            ep.first_prompt_tokens = res.prompt_eval_count
        ep.total_prompt_tokens += res.prompt_eval_count or 0
        ep.total_eval_tokens += res.eval_count or 0
        ep.thinking_chars += len(res.message.get("thinking") or "")
        msg = {"role": "assistant", "content": res.message.get("content", "")}
        if res.message.get("thinking"):
            msg["thinking"] = res.message["thinking"]
        if res.tool_calls:
            msg["tool_calls"] = res.tool_calls
        ep.messages.append(msg)
        if not res.tool_calls:
            ep.final_text = res.message.get("content", "")
            if ep.finish_reminders < MAX_FINISH_REMINDERS:
                # Pre-registered harness protocol, identical for every arm: one fixed reminder.
                ep.finish_reminders += 1
                ep.messages.append({"role": "user", "content": FINISH_REMINDER})
                tools = arm.current_tools()
                continue
            ep.stop_reason = "no_tool_call"
            break
        finished = False
        pending_followup = None
        for tc in res.tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = _parse_args(fn.get("arguments", {}))
            if name == "finish":
                a = args if isinstance(args, dict) else {}
                veto = arm.validate_finish(a.get("outcome")) if a.get("outcome") in FINISH_OUTCOMES else None
                if veto:
                    rec = ToolCallRecord(step, name, args, "finish_rejected")
                    ep.rejected_finish_calls += 1
                    content = {"error": veto}
                elif a.get("outcome") in FINISH_OUTCOMES and isinstance(a.get("message"), str):
                    rec = ToolCallRecord(step, name, args, "finish")
                    if ep.declared_outcome is None:
                        ep.declared_outcome = a["outcome"]
                        ep.declared_message = a["message"]
                    content = {"ok": True}
                    finished = True
                    follow = await on_finish(a["outcome"], a["message"]) if (on_finish and len(ep.phases) < MAX_PHASES - 1) else None
                    if follow:
                        ep.phases.append({"step": step, "declared_outcome": ep.declared_outcome, "declared_message": ep.declared_message,
                                          "followup": follow})
                        ep.declared_outcome = ep.declared_message = None
                        finished = False
                        pending_followup = follow
                else:
                    # The finish tool validates its own schema, like any tool; the model may call it again.
                    rec = ToolCallRecord(step, name, args, "finish_invalid")
                    ep.invalid_finish_calls += 1
                    content = {"error": f"invalid finish call: outcome must be one of {list(FINISH_OUTCOMES)} and message must be a string"}
            elif name == "search_tools" and arm.with_search:
                rec = ToolCallRecord(step, name, args, "search")
                q = args.get("query", "") if isinstance(args, dict) else str(args)
                content = arm.search(q)
            else:
                rec = ToolCallRecord(step, name, args, "tool")
                content = await arm.call(name, args if isinstance(args, dict) else {}, rec)
            ep.tool_calls.append(rec)
            ep.messages.append({"role": "tool", "tool_name": name, "content": json.dumps(content, default=str)[:RESULT_CHARS]})
        if finished:
            ep.stop_reason = "finish"
            break
        if pending_followup:
            ep.messages.append({"role": "user", "content": pending_followup})
            ep.finish_reminders_by_phase.append(ep.finish_reminders)
            ep.finish_reminders = 0
            phase_calls = 0
        tools = arm.current_tools()
    else:
        ep.stop_reason = "turn_limit"
    return ep
