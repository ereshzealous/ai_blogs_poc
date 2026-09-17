"""Web console card: evidence, recommendation, approval controls. Returns an HTML fragment (escaped)."""

from __future__ import annotations

from html import escape

from headless_ai_platform.contracts import CapabilityResponse

STEPS = ["intake", "investigate", "propose_remediation", "await_approval", "remediate", "verify", "record", "complete"]


def _row(label: str, value: object) -> str:
    return "" if value in (None, "") else f"<div class='kv'><dt>{escape(label)}</dt><dd>{escape(str(value))}</dd></div>"


def render(r: CapabilityResponse) -> str:
    s = r.state
    done = STEPS.index(s.current_step) if s.current_step in STEPS else 0
    if r.status.value == "COMPLETED":
        done = len(STEPS)
    steps = "".join(f"<li class='{'done' if i < done else 'now' if i == done else ''}'>{escape(n.replace('_', ' '))}</li>"
                    for i, n in enumerate(STEPS))
    rec = s.recommended_action
    buttons = "".join(
        f"<button class='act {a.type.value.lower()}' data-action='{escape(a.action_id)}' data-binding='{escape(a.binding or '')}'"
        f"{'' if a.allowed_for_actor else ' disabled'} title='{escape('needs ' + a.required_role if a.required_role else '')}'>"
        f"{escape(a.label)}</button>" for a in r.available_actions)
    note = "" if not buttons or all(a.allowed_for_actor for a in r.available_actions) else \
        f"<p class='hint'>You can see this action but need the <code>{escape(r.available_actions[0].required_role or '')}</code> role to take it.</p>"
    return (
        f"<article class='card status-{r.status.value.lower()}' data-workflow='{escape(r.workflow_id)}'>"
        f"<header><h2>{escape(s.incident_id)}</h2><span class='badge'>{escape(r.status.value.replace('_', ' '))}</span></header>"
        f"<p class='meta'>workflow <code>{escape(r.workflow_id)}</code> · started from {escape(r.started_by.channel)} by "
        f"{escape(r.started_by.principal_id)} · {escape(r.capability_version)}</p>"
        f"<ol class='steps'>{steps}</ol>"
        f"<dl>{_row('Service', s.service)}{_row('Suspect', s.suspect)}{_row('Root cause', s.summary)}"
        f"{_row('Confidence', s.confidence)}{_row('Recommendation', rec.description if rec else None)}"
        f"{_row('Policy', f'{s.policy_decision} ({s.policy_rule})' if s.policy_decision else None)}"
        f"{_row('Approval', f'{s.approval_status} by {s.approved_by}' if s.approved_by else s.approval_status)}"
        f"{_row('Verification', f'p95 {s.p95_ms:.0f} ms (SLO {s.slo_p95_ms:.0f} ms)' if s.p95_ms is not None else None)}"
        f"{_row('Incident note', s.incident_note)}</dl>"
        f"<div class='actions'>{buttons}</div>{note}</article>")
