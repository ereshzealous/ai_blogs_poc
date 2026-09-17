"""An in-memory platform with the same port and the same role rule, for tests that are about the boundary itself."""

from __future__ import annotations

import itertools
from typing import Any

from headless_ai_platform.platform.port import NotAllowed, NotPending

DIRECTORY = {"alice": ("Alice (SRE on call)", ("sre", "incident-commander")), "bob": ("Bob (developer)", ("developer",))}


class FakePlatform:
    def __init__(self) -> None:
        self.workflows: dict[str, dict[str, Any]] = {}
        self.ids = itertools.count(1)
        self.calls: list[str] = []

    def submit(self, *, incident_id, request, principal_id, channel, session_id):
        if principal_id not in DIRECTORY:
            raise NotAllowed(f"unknown user {principal_id}")
        wf = f"wf-fake{next(self.ids):05d}"
        self.workflows[wf] = {"workflow_id": wf, "incident_id": incident_id, "status": "RUNNING", "current_step": "intake",
                              "channel": channel, "requested_by": principal_id, "trace_id": f"trace-{wf}",
                              "session_id": session_id, "approval": None, "incident": {"service": "checkout-api",
                                                                                        "environment": "production"}}
        self.calls.append(f"submit {wf}")

        async def go():
            self.workflows[wf].update(status="WAITING_APPROVAL", current_step="await_approval",
                                      diagnosis={"root_cause": "pool exhausted", "suspect_service": "checkout-api",
                                                 "suspect_version": "v4.17", "suspect_deployment_id": "DEP-1", "confidence": "high"},
                                      proposal={"tool_id": "source_control.rollback_release", "service": "checkout-api",
                                                "environment": "production", "target_version": "v4.16"},
                                      policy={"decision": "REQUIRE_APPROVAL", "rule_id": "P4-prod-high-risk-approval"},
                                      approval={"status": "PENDING", "required_role": "incident-commander", "digest": "d" * 64,
                                                "tool_id": "source_control.rollback_release",
                                                "arguments": {"target_version": "v4.16"}, "decided_by": None})
            return self.workflows[wf]

        return wf, go()

    def check_decision(self, workflow_id, principal_id):
        a = self.workflows[workflow_id]["approval"]
        if not a or a["status"] != "PENDING":
            raise NotPending(f"{workflow_id} has no pending approval")
        if a["required_role"] not in DIRECTORY[principal_id][1]:
            raise NotAllowed(f"{principal_id} lacks role {a['required_role']!r}")

    def decide(self, workflow_id, principal_id, approve, comment):
        async def go():
            self.check_decision(workflow_id, principal_id)
            wf = self.workflows[workflow_id]
            wf["approval"] = {**wf["approval"], "status": "APPROVED" if approve else "REJECTED", "decided_by": principal_id}
            wf.update(status="COMPLETED" if approve else "REJECTED", current_step="complete" if approve else "await_approval",
                      verification={"ok": True, "p95_ms": 200.0, "slo_p95_ms": 400.0} if approve else None)
            self.calls.append(f"decide {workflow_id}")
            return wf

        return go()

    def resume(self, workflow_id):
        async def go():
            return self.workflows[workflow_id]

        return go()

    def view(self, workflow_id):
        return dict(self.workflows[workflow_id])

    def principal(self, principal_id):
        return DIRECTORY.get(principal_id)

    def activity(self, workflow_id):
        return {"calls": len(self.calls)}

    def trace(self, workflow_id):
        return []
