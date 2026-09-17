"""The layered agent platform (Part 2) behind the headless port.

This is the only module that imports Part 2, and it imports only the public facade (`agent_platform.service`), the
command types the facade accepts (`agent_platform.contracts`) and the principal directory (`agent_platform.identity`).
Orchestration, agents, tools and models stay behind the facade (see `.importlinter`).
"""

from __future__ import annotations

import os
from collections.abc import Coroutine
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from agent_platform.contracts import ApprovalDecision, StartInvestigation
from agent_platform.identity.principals import resolve_user
from agent_platform.service import Forbidden, PlatformService

from headless_ai_platform.platform.port import NotAllowed, NotPending, View
from headless_ai_platform.settings import Settings, load_settings


class LayeredPlatform:
    def __init__(self, svc: PlatformService):
        self.svc = svc

    # The layered platform resolves a relative LAP_* path against ITS OWN folder, so a relative value here would write
    # into Part 2's tree. Everything this POC passes is absolute, and this refuses anything that is not.
    PATH_VARS = ("LAP_PLATFORM_DB", "LAP_ENTERPRISE_DB", "LAP_RUNS_DIR", "LAP_KNOWLEDGE_INDEX")

    @classmethod
    @asynccontextmanager
    async def open(cls, settings: Settings | None = None) -> AsyncIterator[LayeredPlatform]:
        s = settings or load_settings()
        for key, value in s.platform_env().items():
            os.environ.setdefault(key, value)
        relative = {k: os.environ[k] for k in cls.PATH_VARS if os.environ.get(k) and not Path(os.environ[k]).is_absolute()}
        if relative:
            raise ValueError(f"these must be absolute paths, or the layered platform writes inside its own folder: {relative}")
        s.platform_db.parent.mkdir(parents=True, exist_ok=True)
        async with PlatformService.open() as svc:
            yield cls(svc)

    # ---------------------------------------------------------------- commands
    def submit(self, *, incident_id: str, request: str, principal_id: str, channel: str,
               session_id: str | None) -> tuple[str, Coroutine[Any, Any, View]]:
        try:
            return self.svc.submit(StartInvestigation(incident_id=incident_id, request=request, user_id=principal_id,
                                                      channel=channel, session_id=session_id))
        except Forbidden as exc:
            raise NotAllowed(str(exc)) from exc

    def check_decision(self, workflow_id: str, principal_id: str) -> None:
        try:
            self.svc.check_approver(ApprovalDecision(workflow_id=workflow_id, approver_id=principal_id, approve=False))
        except Forbidden as exc:
            raise NotAllowed(str(exc)) from exc
        except ValueError as exc:
            raise NotPending(str(exc)) from exc

    def decide(self, workflow_id: str, principal_id: str, approve: bool, comment: str) -> Coroutine[Any, Any, View]:
        return self.svc.decide_approval(ApprovalDecision(workflow_id=workflow_id, approver_id=principal_id,
                                                         approve=approve, comment=comment))

    def resume(self, workflow_id: str) -> Coroutine[Any, Any, View]:
        return self.svc.resume(workflow_id)

    # ---------------------------------------------------------------- queries
    def view(self, workflow_id: str) -> View:
        return self.svc.workflow(workflow_id)

    @staticmethod
    def principal(principal_id: str) -> tuple[str, tuple[str, ...]] | None:
        try:
            p = resolve_user(principal_id)
        except Forbidden:
            return None
        return p.display_name, p.roles

    def activity(self, workflow_id: str) -> dict[str, int]:
        """Counters that any work on the workflow would move: model calls, tool calls, policy checks, state changes."""
        audit = self.svc.audit_log(workflow_id)
        view = self.view(workflow_id)
        return {"model_calls": len(self.svc.model_usage(workflow_id)),
                "tool_calls": sum(1 for a in audit if a["event"].startswith("invocation.")),
                "policy_evaluations": sum(1 for a in audit if a["event"] == "policy.decision"),
                "workflow_events": len(self.svc.events(workflow_id)),
                "checkpoints": view.get("checkpoints", 0)}

    def trace(self, workflow_id: str) -> list[dict[str, Any]]:
        return self.svc.trace(workflow_id)

    def record(self, workflow_id: str) -> dict[str, Any]:
        """Everything the platform recorded about a workflow (view, events, audit, usage, trace, evals). For reports."""
        return self.svc.workflow_record(workflow_id)
