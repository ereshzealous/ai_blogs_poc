"""Adapters between a capability's contract and one tool implementation's arguments and results.

The platform always speaks the capability contract (e.g. deploy.rollback takes service, environment, to_release).
When a backend changes its interface, a new adapter absorbs it here and nothing above this layer changes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Adapter = tuple[Callable[[dict[str, Any]], dict[str, Any]], Callable[[Any], Any]]


def _same(x: Any) -> Any:
    return x


ADAPTERS: dict[str, Adapter] = {
    "passthrough": (_same, _same),
}


def get(name: str) -> Adapter:
    return ADAPTERS[name]
