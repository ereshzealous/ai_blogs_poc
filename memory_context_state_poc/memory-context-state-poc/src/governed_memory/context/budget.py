"""Gate 6: the evidence token budget. Greedy in rank order; an item that does not fit is skipped, the next one is tried."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")


def tokens(text: str) -> int:
    return max(1, len(text) // 4)  # the same estimate as F2's context assembler


def fill(items: Iterable[T], budget: int, cost) -> tuple[list[T], list[T], int]:
    taken, skipped, used = [], [], 0
    for it in items:
        c = cost(it)
        if used + c <= budget:
            taken.append(it)
            used += c
        else:
            skipped.append(it)
    return taken, skipped, used
