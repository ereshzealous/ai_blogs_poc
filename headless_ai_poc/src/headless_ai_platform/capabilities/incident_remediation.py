"""The `incident.remediation` capability: the contract's meaning for one kind of work.

It turns contract operations into platform commands and the platform's workflow view into capability state and
available actions. It holds no workflow rules (the platform's orchestration does) and no authorization rules (the
platform's policy and principal directory do); `allowed_for_actor` is a hint computed from the same directory.
"""

from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

from headless_ai_platform.contracts import (ActionType, AvailableAction, CapabilityError, CapabilityRequest,
                                            CapabilityResponse, CapabilityState, ErrorCode, RecommendedAction,
                                            ResolvedActor, Status)
from headless_ai_platform.identity.resolver import Principal
from headless_ai_platform.platform.port import NotAllowed, NotPending, PlatformPort, View

NAME = "incident.remediation"
ACTIONS = {"approve-remediation": ActionType.APPROVE, "reject-remediation": ActionType.REJECT, "retry": ActionType.RETRY}


class IncidentRemediation:
    name = NAME

    def __init__(self, platform: PlatformPort, version: str, default_request: str):
        self.platform = platform
        self.version = version
        self.default_request = default_request

    # ---------------------------------------------------------------- operations
    def start(self, principal: Principal, req: CapabilityRequest, session_id: str | None) -> tuple[str, Coroutine[Any, Any, View]]:
        incident_id = req.input.get("incident_id")
        if not isinstance(incident_id, str):
            raise CapabilityError(ErrorCode.INVALID_REQUEST, "input.incident_id is required")
        unknown = set(req.input) - {"incident_id", "request", "service"}
        if unknown:
            raise CapabilityError(ErrorCode.INVALID_REQUEST, f"unknown input fields: {sorted(unknown)}")
        request = str(req.input.get("request") or self.default_request)
        try:
            return self.platform.submit(incident_id=incident_id, request=request, principal_id=principal.principal_id,
                                        channel=req.actor.channel, session_id=session_id)
        except NotAllowed as exc:
            raise CapabilityError(ErrorCode.FORBIDDEN, str(exc)) from exc
        except ValueError as exc:  # the platform's own command validation
            raise CapabilityError(ErrorCode.INVALID_REQUEST, str(exc)) from exc

    def act(self, principal: Principal, req: CapabilityRequest, view: View) -> Coroutine[Any, Any, View]:
        wf_id = str(req.workflow_id)
        current = {a.action_id: a for a in self.actions(view, principal)}
        action = current.get(str(req.action_id))
        if action is None:
            known = "unknown action" if req.action_id not in ACTIONS else "not available now"
            raise CapabilityError(ErrorCode.CONFLICT, f"{req.action_id} is {known} for {wf_id} ({view['status']})")
        if req.binding is not None and req.binding != action.binding:
            raise CapabilityError(ErrorCode.CONFLICT, f"{req.action_id} was shown for a different invocation; refresh {wf_id}")
        if action.type is ActionType.RETRY:
            return self.platform.resume(wf_id)
        comment = str(req.input.get("comment", ""))[:500]
        try:
            self.platform.check_decision(wf_id, principal.principal_id)
        except NotAllowed as exc:
            raise CapabilityError(ErrorCode.FORBIDDEN, str(exc)) from exc
        except NotPending as exc:
            raise CapabilityError(ErrorCode.CONFLICT, str(exc)) from exc
        return self.platform.decide(wf_id, principal.principal_id, action.type is ActionType.APPROVE, comment)

    # ---------------------------------------------------------------- read model
    def actions(self, view: View, principal: Principal) -> list[AvailableAction]:
        a = view.get("approval")
        if view["status"] == Status.WAITING_APPROVAL and a and a["status"] == "PENDING":
            role, allowed = a["required_role"], principal.has_role(a["required_role"])
            target = a["arguments"].get("target_version") or a["arguments"].get("revision")
            return [AvailableAction(action_id="approve-remediation", type=ActionType.APPROVE, label=f"Approve {a['tool_id']} → {target}",
                                    required_role=role, allowed_for_actor=allowed, binding=a["digest"][:16]),
                    AvailableAction(action_id="reject-remediation", type=ActionType.REJECT, label="Reject",
                                    required_role=role, allowed_for_actor=allowed, binding=a["digest"][:16])]
        if view["status"] == Status.FAILED:
            return [AvailableAction(action_id="retry", type=ActionType.RETRY, label="Retry from the last checkpoint",
                                    allowed_for_actor=True)]
        return []

    def response(self, view: View, principal: Principal, channel: str) -> CapabilityResponse:
        return CapabilityResponse(
            capability=NAME, capability_version=f"{NAME}@{self.version}", workflow_id=view["workflow_id"],
            status=Status(view["status"]), state=state(view), available_actions=self.actions(view, principal),
            actor=ResolvedActor(principal_id=principal.principal_id, channel=channel),
            started_by=ResolvedActor(principal_id=view["requested_by"], channel=view["channel"]),
            trace_id=view.get("trace_id"), updated_at=view.get("updated_at"))


def state(view: View) -> CapabilityState:
    inc, d, p = view.get("incident") or {}, view.get("diagnosis") or {}, view.get("proposal") or {}
    pol, a = view.get("policy") or {}, view.get("approval") or {}
    rem, ver, note = view.get("remediation") or {}, view.get("verification") or {}, view.get("note") or {}
    recommended = None
    if p:
        target = p.get("target_version") or (f"revision {p['revision']}" if p.get("revision") is not None else None)
        verb = p["tool_id"].split(".")[-1].replace("_", " ")
        recommended = RecommendedAction(tool=p["tool_id"], target=target, environment=p.get("environment"),
                                        description=f"{verb} {p.get('service', inc.get('service', ''))} to {target} in {p.get('environment')}")
    suspect = f"{d['suspect_service']} {d['suspect_version']} ({d['suspect_deployment_id']})" if d.get("suspect_version") else None
    return CapabilityState(
        incident_id=view["incident_id"], service=inc.get("service"), environment=inc.get("environment"),
        summary=d.get("root_cause"), suspect=suspect, confidence=d.get("confidence"), recommended_action=recommended,
        policy_decision=pol.get("decision"), policy_rule=pol.get("rule_id"), approval_status=a.get("status"),
        approval_required_role=a.get("required_role"), approved_by=a.get("decided_by"),
        remediation_status=rem.get("status"), verified=ver.get("ok") if ver else None, p95_ms=ver.get("p95_ms"),
        slo_p95_ms=ver.get("slo_p95_ms"), incident_note=note.get("note"), current_step=view.get("current_step"))
