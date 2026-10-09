"""Agent runtime: the incident remediation agent.  It reasons; it does not act.

It receives a model port (the model gateway) and the capabilities discovery offered it.  It returns tool intents and one
action proposal.  This reasoning component holds no MCP client, no execution credential or execution capability, and no
policy: tests/test_units.py (test_agent_imports_no_execution_machinery) checks that this module imports none of mcp,
capability, approval, policy, the tool gateway or the simulated enterprise systems.  The agent workload still has an
identity (the runtime attests it); the capability for a call is attached by the gateway at execution time, never handed
to this code.  The platform runs the agent's intents through enforcement; the agent never learns why a call was allowed,
only its result or its refusal.

This file's sha256 is recorded in every experiment: the kill switch, the model outage and the policy changes happen with
the same agent code.
"""

from __future__ import annotations

import json
from typing import Any, Callable

ModelPort = Callable[..., dict[str, Any]]


def render(task: dict[str, Any], context: list[dict[str, Any]], observations: list[dict[str, Any]], offered: list[dict[str, Any]],
           ask: str, round_: int | None = None) -> str:
    """The prompt: task, capability menu, governed context and observations, each item carrying its evidence id."""
    parts = [f"ROLE: incident remediation agent for tenant {task['tenant']}. You may PROPOSE actions; the platform decides.",
             f"TASK: {task['request']}", f"INCIDENT: {task['incident']} service={task['service']} environment={task['environment']}"]
    if round_ is not None:
        parts.append(f"ROUND: {round_}")
    parts.append("CAPABILITIES OFFERED: " + ", ".join(f"{c['name']} ({c['description']})" for c in offered))
    parts.append("CONTEXT:")
    parts += [f"  [{c['id']}] ({c['kind']}, {c['source']}) {c['text']}" for c in context]
    parts.append("OBSERVATIONS:")
    for o in observations:
        parts.append(f"  <{o['capability']}> " + json.dumps(o["result"], sort_keys=True))
    parts.append(f"ASK: {ask}")
    return "\n".join(parts)


class IncidentAgent:
    def __init__(self, model: ModelPort, capability_class: str, quality: str):
        self.model, self.cls, self.quality = model, capability_class, quality

    def plan(self, task, context, observations, offered, round_: int) -> dict[str, Any]:
        """Which reads next?  Returns {"intents": [{capability, arguments}], "done": bool}."""
        prompt = render(task, context, observations, offered, "Which capabilities should be called next to diagnose? Reply {intents, done}.", round_)
        out = self.model(purpose="plan", cls=self.cls, quality=self.quality, prompt=prompt, round_=round_)
        return out["content"]

    def propose(self, task, context, observations, offered) -> dict[str, Any]:
        """One remediation proposal: {diagnosis, proposal: {capability, arguments, rationale, evidence}}."""
        prompt = render(task, context, observations, offered, "Diagnose and propose exactly one remediation, citing evidence ids.")
        return self.model(purpose="propose", cls=self.cls, quality=self.quality, prompt=prompt)["content"]

    def summarize(self, task, outcome: dict[str, Any]) -> dict[str, Any]:
        prompt = render(task, [], [{"capability": "platform.outcome", "result": outcome}], [], "Write the incident note.")
        return self.model(purpose="summarize", cls="summarization", quality=self.quality, prompt=prompt)["content"]
