"""One meaning-based question for discovery v5, a simulated user who knows only the hidden intent, and the constraint
an answer puts on a second discovery pass.

The question compares two capabilities on the first dimension where they differ (system, then resource, then
action) and uses plain labels from the vocabulary, never tool names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from control_plane.registry.capabilities import CapabilityCatalog
from control_plane.registry.vocabulary import action_label, resource_label, system_label

DIMENSIONS = ("system", "resource", "action")
TEMPLATES = {
    "system": "Should this happen in {a} or in {b}?",
    "resource": "Do you mean {a} or {b}?",
    "action": "Do you want to {a} or {b}?",
}
LABELS = {"system": system_label, "resource": resource_label, "action": action_label}


@dataclass(frozen=True)
class Option:
    capability: str
    value: str
    label: str


@dataclass(frozen=True)
class Question:
    dimension: str
    text: str
    options: tuple[Option, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"dimension": self.dimension, "text": self.text,
                "options": [{"capability": o.capability, "value": o.value, "label": o.label} for o in self.options]}


@dataclass(frozen=True)
class Answer:
    kind: str  # option | neither | not_sure
    value: str | None = None
    text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "value": self.value, "text": self.text}


@dataclass(frozen=True)
class Constraint:
    """What an answer changes in the second discovery pass."""

    dimension: str | None = None
    value: str | None = None
    exclude: frozenset[str] = field(default_factory=frozenset)
    reads_only: bool = False

    def allows(self, capability: Any) -> bool:
        if capability.id in self.exclude:
            return False
        if self.dimension and capability.value(self.dimension) != self.value:
            return False
        return not (self.reads_only and capability.side_effect)

    def to_dict(self) -> dict[str, Any]:
        return {"dimension": self.dimension, "value": self.value, "exclude": sorted(self.exclude), "reads_only": self.reads_only}


def build_question(resolution: Any, selected_tool: str | None, *, catalog: CapabilityCatalog,
                   prefer: str | None = None) -> Question | None:
    """Compare discovery's leading capability (or `prefer`'s) with the model's pick, or with the runner-up."""
    ranked = [c["capability"] for c in resolution.capabilities]
    first = catalog.capability_of(prefer) if prefer else (ranked[0] if ranked else None)
    picked = catalog.capability_of(selected_tool)
    second = picked if picked and picked != first else next((c for c in ranked if c != first), None)
    if first is None or second is None:
        return None
    a, b = catalog.capabilities[first], catalog.capabilities[second]
    for dim in DIMENSIONS:
        if a.value(dim) != b.value(dim):
            label = LABELS[dim]
            options = (Option(a.id, a.value(dim), label(a.value(dim))), Option(b.id, b.value(dim), label(b.value(dim))))
            text = TEMPLATES[dim].format(a=options[0].label, b=options[1].label)
            return Question(dim, text[0].upper() + text[1:], options)
    return None


def simulated_answer(intent: dict[str, Any] | None, question: Question) -> Answer:
    """A user who knows only what they meant: the matching option, "neither" or "not sure"."""
    wanted = (intent or {}).get(question.dimension)
    if not wanted:
        return Answer("not_sure", text="I'm not sure.")
    for option in question.options:
        if option.value == wanted:
            return Answer("option", option.value, text=option.label[0].upper() + option.label[1:] + ".")
    return Answer("neither", text="Neither of those.")


def answer_constraint(question: Question, answer: Answer, *, catalog: CapabilityCatalog) -> Constraint | None:
    """The constraint for the second pass; None means make no call (the user is unsure and every option writes)."""
    if answer.kind == "option":
        return Constraint(dimension=question.dimension, value=answer.value)
    if answer.kind == "neither":
        return Constraint(exclude=frozenset(o.capability for o in question.options))
    if any(not catalog.capabilities[o.capability].side_effect for o in question.options):
        return Constraint(reads_only=True)
    return None


def clarification_note(question: Question, answer: Answer) -> str:
    """Added to the request for the second selection call."""
    return f"\n\n(You asked: {question.text} The user answered: {answer.text})"
