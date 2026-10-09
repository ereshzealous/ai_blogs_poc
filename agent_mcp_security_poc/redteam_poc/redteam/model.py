"""The scripted worst-case-compliant model. This is the ONLY module allowed to import the corpus, because it plays the
role of a model whose context has been manipulated: when an untrusted-instruction marker reaches it, it proposes exactly
the mock actions the marker asks for. It never refuses. That makes `model_manipulated = YES` an assumption of the test,
not a hoped-for property, so the only variable left is whether the surrounding system contains the action.

A separate, optional live backend (redteam/live.py) can replace this with a local model to MEASURE how often a real
model complies; the scripted model is what the publication gate uses.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redteam.base import ProposedAction


@dataclass
class ModelPlan:
    actions: list[ProposedAction]
    manipulated: bool             # did a hostile marker reach the model and get obeyed?
    saw_hostile_content: bool     # was hostile content present in context at all (even if a guard later stripped it)?


def plan(scenario: dict, content_visible: bool = True) -> ModelPlan:
    """Build the model's proposed actions.

    content_visible=False models a guard (arm B) that stripped the hostile content before the model saw it: the model
    then proposes only the legitimate task and is NOT manipulated.
    """
    actions: list[ProposedAction] = []
    # 1. the legitimate task (always proposed)
    for step in scenario.get("legit_task_actions", []):
        actions.append(ProposedAction(step["tool"], dict(step["args"]), source="task", hostile=False))
    # 2. a legitimate escalation that genuinely needs approval (control OK-2)
    for step in scenario.get("escalation", []) or []:
        actions.append(ProposedAction(step["tool"], dict(step["args"]), source="task", hostile=False))

    hijack = scenario.get("hijack") or []
    saw_hostile = bool(hijack)
    manipulated = False
    if hijack and content_visible:
        manipulated = True
        for step in hijack:
            # {{RESULT:-1}} stays literal here; the runtime substitutes the ACTUAL prior tool result at execution time,
            # so an arm where the first step really executed will carry its real output into the next call.
            actions.append(ProposedAction(step["tool"], dict(step["args"]),
                                          source=scenario.get("ingress", "content"), hostile=True))
    return ModelPlan(actions=actions, manipulated=manipulated, saw_hostile_content=saw_hostile)
