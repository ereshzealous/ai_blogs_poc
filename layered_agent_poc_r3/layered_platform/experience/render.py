"""Channel renderers: the same WorkflowView, formatted for a terminal and for a chat message."""

from __future__ import annotations

from typing import Any

from layered_platform.contracts import WorkflowView


def text(v: WorkflowView) -> str:
    lines = [f"{v.incident_id} · workflow {v.workflow_id} · {v.status} (next: {v.step})"]
    if v.diagnosis:
        lines.append(f"  diagnosis : {v.diagnosis['root_cause']} [release {v.diagnosis.get('suspect_release')}, {v.diagnosis['confidence']}]")
    if v.proposal:
        p = v.proposal
        lines.append(f"  proposal  : {p['action']} {p['service']}/{p['environment']} {p.get('target_release') or ''}".rstrip())
    if v.policy:
        lines.append(f"  policy    : {v.policy['effect']} by {v.policy['rule']}")
    if v.approval:
        lines.append(f"  approval  : {v.approval['id']} {v.approval['status']}" + (f" by {v.approval.get('decided_by')}" if v.approval.get("decided_by") else ""))
    if v.report:
        lines += ["", v.report]
    return "\n".join(lines)


def chat(v: WorkflowView) -> dict[str, Any]:
    """A Slack-style message payload: blocks, plus approve/reject buttons while a decision is pending."""
    blocks: list[dict[str, Any]] = [{"type": "header", "text": f"{v.incident_id} · {v.status}"}]
    if v.diagnosis:
        blocks.append({"type": "section", "text": f"*Diagnosis* {v.diagnosis['summary']}"})
    if v.status == "WAITING_APPROVAL" and v.approval:
        blocks.append({"type": "actions", "approval_id": v.approval["id"], "elements": ["approve", "reject"],
                       "text": f"Approve {v.proposal['action'] if v.proposal else ''}? Needs {v.approval['required_role']}."})
    if v.report:
        blocks.append({"type": "section", "text": v.report})
    return {"workflow_id": v.workflow_id, "blocks": blocks}
