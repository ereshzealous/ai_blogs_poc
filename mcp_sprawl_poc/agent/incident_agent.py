"""Multi-step incident agent running through the MCP gateway.

Tool exposure depends on the mode:

* baseline       - every published tool is in the prompt on every step;
* search         - the top-K tools for the request, plus a `find_tools` meta-tool backed by hybrid search;
* control_plane  - the top-K tools from capability discovery, plus `find_tools` backed by the same pipeline.

`find_tools` mirrors deferred tool loading as used in practice: the model asks for more tools and the
results are added to the tools it can call. Every real tool call goes through `Gateway.call_tool`.

Guards (the benchmark uses `evidence` in control_plane mode and `legacy` elsewhere):

* legacy   - the model decides when it is done and writes the final answer and incident fields itself.
* evidence - the agent keeps a ledger of successful structured results (agent/evidence.py). Before each model call
             it asks discovery for the next missing piece of evidence and keeps at most `max_tools` real tools
             exposed. It blocks writes the request does not allow, incident closure without verified recovery and
             rollbacks to a version the evidence does not support; renders incident fields from receipts; sends the
             model back when it stops before the required evidence exists (and ends the run after
             `MAX_IDLE_PUSHBACKS` pushbacks in a row without a tool call); and renders the final report from receipts,
             incomplete when the run ends early. Gateway policy and approvals are unchanged.

Every step records the full tool result in both guards.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from agent.evidence import (
    EvidenceLedger,
    NotExecuted,
    describe,
    diagnose,
    gate_call,
    missing_requirements,
    next_requirement,
    parse_intent,
    render_report,
    verify_recovery,
)
from agent.llm import ChatModel
from agent.prompts import system_prompt
from control_plane.gateway.gateway import Gateway, InvocationContext
from control_plane.policy.approvals import ApprovalRequest
from control_plane.policy.engine import PolicyResult

FIND_TOOLS = {
    "type": "function",
    "function": {
        "name": "find_tools",
        "description": "Search the tool catalogue for tools matching a need (e.g. 'database connection pool stats') and "
                       "load them so you can call them. Returns tool names and descriptions.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
}
MAX_RESULT_CHARS = 2500
MAX_TOOLS = 12
MAX_IDLE_PUSHBACKS = 3
NOT_EXECUTED = {"denied": "denied by policy", "approval_rejected": "approval rejected", "approval_pending": "approval pending",
                "unknown_tool": "unknown tool", "guard_blocked": "blocked by the evidence guard"}
GUARDS = ("legacy", "evidence")
# The active incident the system prompt names; the evidence guard uses it when a request names no scope.
ACTIVE_INCIDENT = {"default_service": "checkout-api", "default_environment": "production", "incident_id": "INC-4917"}


@dataclass
class AgentStep:
    index: int
    tool: str | None
    arguments: dict[str, Any]
    status: str
    policy: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    llm_latency_ms: float
    tools_in_prompt: int
    result_preview: str = ""
    is_error: bool = False
    result: Any = None
    guard: str | None = None


@dataclass
class AgentRun:
    mode: str
    guard: str = "legacy"
    steps: list[AgentStep] = field(default_factory=list)
    final_answer: str | None = None
    stopped: str = ""
    wall_ms: float = 0.0
    model_final: str | None = None
    complete: bool | None = None
    missing: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    diagnosis: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "guard": self.guard, "final_answer": self.final_answer, "model_final": self.model_final,
                "stopped": self.stopped, "wall_ms": round(self.wall_ms, 1), "complete": self.complete, "missing": self.missing,
                "evidence": self.evidence, "diagnosis": self.diagnosis, "verification": self.verification,
                "steps": [s.__dict__ for s in self.steps]}


def scripted_approver(approve_if: Callable[[ApprovalRequest], bool]):
    """A human stand-in with a fixed decision table, so runs are reproducible."""

    async def approver(req: ApprovalRequest, decision: PolicyResult) -> bool:
        return approve_if(req)

    return approver


def _bounded(first: list[str], rest: list[str], limit: int) -> list[str]:
    """Newest tools first, duplicates removed, at most `limit`."""
    return list(dict.fromkeys([*first, *rest]))[:limit]


async def run_incident_agent(llm: ChatModel, gateway: Gateway, request: str, ctx: InvocationContext, *, mode: str,
                             discover: Callable[[str], list[str]] | None = None, max_steps: int = 16,
                             guard: str = "legacy", context: dict[str, str] | None = None,
                             max_tools: int = MAX_TOOLS) -> AgentRun:
    """`discover(query)` returns exposed tool names (search / control_plane modes only)."""
    if guard not in GUARDS:
        raise ValueError(f"unknown agent guard {guard!r}; choose one of {', '.join(GUARDS)}")
    evidence = guard == "evidence"
    adaptive = evidence and mode != "baseline" and discover is not None
    t0 = time.perf_counter()
    run = AgentRun(mode, guard)
    intent = parse_intent(request, **(context or ACTIVE_INCIDENT)) if evidence else None
    ledger = EvidenceLedger()
    loaded: list[str] = list(gateway.tools) if mode == "baseline" else list(dict.fromkeys(discover(request) if discover else []))
    if adaptive:
        loaded = loaded[:max_tools]
    asked: set[str] = set()
    idle = 0
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt(ctx.identity.user_id, ctx.identity.roles, agent=True)},
        {"role": "user", "content": request},
    ]
    for i in range(max_steps):
        if adaptive:
            requirement = next_requirement(intent, ledger)
            if requirement is not None and requirement.query not in asked:
                asked.add(requirement.query)
                found = [n for n in discover(requirement.query) if n in gateway.tools]
                loaded = _bounded(found, loaded, max_tools)
        defs = [gateway.tools[n].definition() for n in loaded if n in gateway.tools]
        if mode != "baseline":
            defs.append(FIND_TOOLS)
        resp = llm.chat(messages, defs)
        if resp.error:
            run.stopped = f"llm_error: {resp.error}"
            break
        if not resp.tool_calls:
            if evidence:
                requirement = next_requirement(intent, ledger)
                if requirement is not None and idle >= MAX_IDLE_PUSHBACKS:
                    run.final_answer = render_report(intent, ledger)
                    run.model_final = resp.content
                    run.steps.append(AgentStep(i, None, {}, "guard_stalled", None, resp.prompt_tokens, resp.completion_tokens,
                                               resp.latency_ms, len(defs), guard="stalled"))
                    run.stopped = "guard_stalled"
                    break
                if requirement is not None and i < max_steps - 1:
                    idle += 1
                    note = (f"Not finished, still missing: {requirement.name.replace('_', ' ')} ({requirement.why}). "
                            f"Next: {requirement.query}. Reply with FINAL only once that is done.")
                    messages.append({"role": "assistant", "content": resp.content or ""})
                    messages.append({"role": "user", "content": note})
                    run.steps.append(AgentStep(i, None, {}, "guard_continue", None, resp.prompt_tokens, resp.completion_tokens,
                                               resp.latency_ms, len(defs), note[:300], guard="continue"))
                    continue
                run.model_final = resp.content
                run.final_answer = render_report(intent, ledger)
            else:
                run.final_answer = resp.content
            run.steps.append(AgentStep(i, None, {}, "final", None, resp.prompt_tokens, resp.completion_tokens, resp.latency_ms, len(defs)))
            run.stopped = "final_answer"
            break
        idle = 0
        call = resp.tool_calls[0]
        messages.append({"role": "assistant", "content": resp.content or "",
                         "tool_calls": [{"function": {"name": call.name, "arguments": call.arguments}}]})
        arguments, step_guard = call.arguments, None
        if call.name == "find_tools" and discover is not None:
            found = [n for n in discover(str(call.arguments.get("query", ""))) if n in gateway.tools]
            loaded = _bounded(found, loaded, max_tools) if adaptive else list(dict.fromkeys(loaded + found))
            result: Any = {"loaded_tools": [{"name": n, "description": gateway.tools[n].tool.description} for n in found]}
            content, status, policy, is_error = json.dumps(result), "find_tools", None, False
        else:
            published = gateway.tools.get(call.name)
            blocked = None
            if evidence and published is not None:
                gate = gate_call(intent, published.tool_id, arguments, gateway.registry.get(published.tool_id), ledger)
                if not gate.allowed:
                    blocked = gate.message
                elif gate.arguments != arguments:
                    arguments, step_guard = gate.arguments, "arguments_rendered"
            if blocked:
                result = {"status": "blocked_by_evidence_guard", "message": blocked}
                content, status, policy, is_error, step_guard = json.dumps(result), "guard_blocked", None, False, "blocked"
            else:
                outcome = await gateway.call_tool(call.name, arguments, ctx)
                policy = outcome.policy.decision.value if outcome.policy else None
                status, is_error = outcome.status, outcome.is_error
                result = outcome.result if outcome.executed else {"status": outcome.status, "message": outcome.result}
                content = json.dumps(result, default=str)[:MAX_RESULT_CHARS]
                if outcome.executed and outcome.tool_id:
                    ledger.record(i, outcome.tool_id, arguments, outcome.result, outcome.is_error)
        if evidence and status in NOT_EXECUTED:
            tool_id = published.tool_id if published is not None else call.name.replace("__", ".", 1)
            ledger.not_executed.append(NotExecuted(i, tool_id, dict(arguments), NOT_EXECUTED[status]))
        messages.append({"role": "tool", "content": content, "tool_name": call.name})
        run.steps.append(AgentStep(i, call.name, arguments, status, policy, resp.prompt_tokens, resp.completion_tokens,
                                   resp.latency_ms, len(defs), content[:300], is_error, result, step_guard))
    else:
        run.stopped = "max_steps"
        if evidence:
            run.final_answer = render_report(intent, ledger)
    if evidence:
        run.missing = missing_requirements(intent, ledger)
        run.complete = run.stopped == "final_answer" and not run.missing
        run.evidence = [{"eid": r.eid, "step": r.step, "tool_id": r.tool_id, "summary": describe(r, intent.service, intent.environment)}
                        for r in ledger.receipts]
        diagnosis = diagnose(ledger, intent.service, intent.environment)
        verification = verify_recovery(ledger, intent.service, intent.environment)
        run.diagnosis = asdict(diagnosis) if diagnosis else None
        run.verification = asdict(verification) if verification else None
    run.wall_ms = (time.perf_counter() - t0) * 1000
    return run
