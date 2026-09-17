"""Terminal text, plus the exit code a script can branch on."""

from __future__ import annotations

from headless_ai_platform.contracts import CapabilityResponse, Status

ICON = {Status.RUNNING: "▶", Status.WAITING_APPROVAL: "⏸", Status.COMPLETED: "✔", Status.FAILED: "✖", Status.REJECTED: "⊘"}
EXIT = {Status.COMPLETED: 0, Status.WAITING_APPROVAL: 10, Status.RUNNING: 11, Status.REJECTED: 20, Status.FAILED: 1}


def render(r: CapabilityResponse) -> str:
    s = r.state
    out = [f"{ICON[r.status]} {r.workflow_id}  {s.incident_id}  {r.status.value}   "
           f"(started via {r.started_by.channel} by {r.started_by.principal_id}; you are {r.actor.principal_id})"]
    for label, value in (("root cause", s.summary), ("suspect", s.suspect),
                         ("recommended", s.recommended_action.description if s.recommended_action else None),
                         ("policy", f"{s.policy_decision} ({s.policy_rule})" if s.policy_decision else None),
                         ("approval", f"{s.approval_status}" + (f" by {s.approved_by}" if s.approved_by else "")
                          if s.approval_status else None),
                         ("verified", f"p95 {s.p95_ms:.0f} ms / SLO {s.slo_p95_ms:.0f} ms" if s.p95_ms is not None else None),
                         ("trace", r.trace_id)):
        if value:
            out.append(f"  {label:<12}{value}")
    for a in r.available_actions:
        verb = {"APPROVE": "approve", "REJECT": "reject", "RETRY": "retry"}[a.type.value]
        lock = "" if a.allowed_for_actor else f"   # needs role {a.required_role}"
        out.append(f"  next        hai {verb} {r.workflow_id}{lock}")
    return "\n".join(out)


def exit_code(r: CapabilityResponse) -> int:
    return EXIT[r.status]
