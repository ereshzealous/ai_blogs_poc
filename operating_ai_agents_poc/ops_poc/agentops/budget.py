"""The workflow resource envelope (P1 layer D, "budgets are a runtime primitive"): the bounds a workflow runs inside.

An Envelope is a set of limits. A Ledger records what a workflow has consumed and answers, before each step, whether
the next step still fits. Child workflows (a coordinator's sub-agents) either draw from the parent's ledger (the
propagated envelope) or get a ledger of their own (per-agent budgets), which is the difference E4 measures.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DIMENSIONS = ("steps", "model_calls", "tool_calls", "input_tokens", "output_tokens", "cost_cu", "wall_ms", "fanout")


@dataclass
class Envelope:
    steps: int | None = None
    model_calls: int | None = None
    tool_calls: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_cu: float | None = None
    wall_ms: int | None = None
    fanout: int | None = None

    @classmethod
    def none(cls) -> "Envelope":
        return cls()

    def as_dict(self) -> dict:
        return {d: getattr(self, d) for d in DIMENSIONS}


@dataclass
class Ledger:
    envelope: Envelope
    started_ms: int = 0
    used: dict = field(default_factory=lambda: {d: 0 for d in DIMENSIONS})
    exceeded: str | None = None

    def charge(self, **amounts: float) -> None:
        for k, v in amounts.items():
            self.used[k] = self.used[k] + v

    def check(self, now: int, next_kind: str | None = None) -> str | None:
        """The dimension that is exhausted (the next step would not fit), or None. ``next_kind``: model | tool | fanout."""
        e = self.envelope
        self.used["wall_ms"] = now - self.started_ms
        tests = [("steps", 1), ("cost_cu", 0), ("input_tokens", 0), ("output_tokens", 0), ("wall_ms", 0)]
        if next_kind == "model":
            tests.append(("model_calls", 1))
        if next_kind == "tool":
            tests.append(("tool_calls", 1))
        if next_kind == "fanout":
            tests.append(("fanout", 1))
        for dim, inc in tests:
            lim = getattr(e, dim)
            # counts: the next unit must fit; continuous dimensions (cost, tokens, time) are checked before the step, so
            # a step that starts inside the envelope can finish over it by at most its own size
            if lim is not None and (self.used[dim] + inc > lim if inc else self.used[dim] >= lim):
                self.exceeded = self.exceeded or dim
                return dim
        return None
