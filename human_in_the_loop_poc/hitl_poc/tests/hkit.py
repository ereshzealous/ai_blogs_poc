"""Shared by tests/test_h*.py: run one preregistered experiment under arms A, B and C and assert its arm-C invariants.

Hypotheses about A and B are predictions, evaluated and reported by `hitl proof` (a FAIL there is a finding, not a broken
build).  Here only what must hold is gated: every scenario completes in every arm, and every invariant of arm C holds.
"""
from pathlib import Path

from hitl.scenarios import EXPERIMENTS, run_all

OPS = {"==": lambda a, b: a == b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b}


def value(outs, x: str, arm: str, metric: str):
    name, _, scope = metric.partition("@")
    sids = [s["id"] for s in EXPERIMENTS[x]["scenarios"]] if not scope or scope == "all" else scope.split("+")
    return sum(outs[(s, arm)].metrics.get(name) or 0 for s in sids)


def check_experiment(x: str, tmp: Path) -> dict:
    sids = [s["id"] for s in EXPERIMENTS[x]["scenarios"]]
    outs = run_all(tmp, only=sids)
    crashed = {k: o.error for k, o in outs.items() if o.error}
    assert not crashed, crashed
    for h in EXPERIMENTS[x]["hypotheses"]:
        if h["kind"] == "invariant":
            got = value(outs, x, h["arm"], h["metric"])
            assert OPS[h["op"]](got, h["value"]), f"{x} arm {h['arm']}: {h['metric']} = {got}, must be {h['op']} {h['value']} ({h['text']})"
    return outs
