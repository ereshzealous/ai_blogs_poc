"""What the headless boundary needs from the platform underneath. The layered platform provides it; tests may fake it.

Exceptions are the port's own, so nothing above this module depends on the platform's exception types.
"""

from __future__ import annotations

from collections.abc import Coroutine
from typing import Any, Protocol


class NotAllowed(PermissionError):
    """The platform refused: the principal lacks the role an action requires."""


class NotPending(RuntimeError):
    """The platform has nothing waiting for this decision."""


View = dict[str, Any]  # the platform's read model of one workflow


class PlatformPort(Protocol):
    def submit(self, *, incident_id: str, request: str, principal_id: str, channel: str,
               session_id: str | None) -> tuple[str, Coroutine[Any, Any, View]]: ...

    def check_decision(self, workflow_id: str, principal_id: str) -> None: ...

    def decide(self, workflow_id: str, principal_id: str, approve: bool, comment: str) -> Coroutine[Any, Any, View]: ...

    def resume(self, workflow_id: str) -> Coroutine[Any, Any, View]: ...

    def view(self, workflow_id: str) -> View: ...

    def principal(self, principal_id: str) -> tuple[str, tuple[str, ...]] | None: ...

    def activity(self, workflow_id: str) -> dict[str, int]: ...

    def trace(self, workflow_id: str) -> list[dict[str, Any]]: ...
