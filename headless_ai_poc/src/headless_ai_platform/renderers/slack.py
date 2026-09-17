"""Slack-shaped Block Kit message: short, threaded, buttons."""

from __future__ import annotations

from typing import Any

from headless_ai_platform.contracts import ActionType, CapabilityResponse, Status

EMOJI = {Status.RUNNING: ":hourglass_flowing_sand:", Status.WAITING_APPROVAL: ":raised_hand:",
         Status.COMPLETED: ":white_check_mark:", Status.REJECTED: ":no_entry_sign:", Status.FAILED: ":x:"}


def render(r: CapabilityResponse) -> dict[str, Any]:
    s = r.state
    head = f"{EMOJI[r.status]} *{s.incident_id}* · `{r.workflow_id}` · *{r.status.value.replace('_', ' ').lower()}*"
    lines = [head]
    if s.summary:
        lines.append(f"*Root cause:* {s.summary}")
    if s.recommended_action and r.status is Status.WAITING_APPROVAL:
        lines.append(f"*Recommended:* {s.recommended_action.description} (needs `{s.approval_required_role}`)")
    if r.status is Status.COMPLETED:
        lines.append(f"*Done:* {s.recommended_action.description if s.recommended_action else 'remediated'}; "
                     f"approved by {s.approved_by or 'policy'}; p95 {s.p95_ms:.0f} ms" if s.p95_ms is not None else "*Done.*")
    blocks: list[dict[str, Any]] = [{"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}]
    buttons = []
    for a in r.available_actions:
        if a.type in (ActionType.APPROVE, ActionType.REJECT) and not a.allowed_for_actor:
            continue  # Slack shows only what this person may press; the platform still checks
        button: dict[str, Any] = {"type": "button", "action_id": a.action_id, "text": {"type": "plain_text", "text": a.label[:75]},
                                  "value": f"{r.workflow_id}|{a.binding or ''}"}
        if a.type is ActionType.APPROVE:
            button["style"] = "primary"
        elif a.type is ActionType.REJECT:
            button["style"] = "danger"
        buttons.append(button)
    if buttons:
        blocks.append({"type": "actions", "block_id": f"wf:{r.workflow_id}", "elements": buttons})
    elif r.status is Status.WAITING_APPROVAL:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
                       "text": f"Waiting for someone with `{s.approval_required_role}` to approve."}]})
    return {"text": f"{s.incident_id} {r.status.value}", "blocks": blocks}
