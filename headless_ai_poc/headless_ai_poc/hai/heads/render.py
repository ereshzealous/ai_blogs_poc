"""Renderers: each head turns the same ExecutionView into its own shape.  Rendering is the only thing a head does
with intelligence; it never changes it."""

from __future__ import annotations

import json
from typing import Any

from hai.contracts import ExecutionView


def _lead(v: ExecutionView) -> dict[str, Any] | None:
    if not v.assessment:
        return None
    return next(h.model_dump() for h in v.assessment.hypotheses if h.id == v.assessment.leading)


def chat(v: ExecutionView) -> str:
    lead = _lead(v)
    lines = [f"*{v.incident_id or v.execution_id}* · {v.status.lower().replace('_', ' ')}" + (" (you joined an investigation already running)" if v.joined else "")]
    if lead:
        lines.append(f"> {lead['statement']} — confidence *{lead['confidence']}*")
        lines += [f"• {e}" for e in lead["evidence"][:3]]
    if v.approval and v.approval.get("status") == "PENDING":
        lines.append(f"Needs an *{v.approval['required_role']}* to approve `{v.approval['call']['capability']}` "
                     f"{v.approval['call']['arguments'].get('from_version')} → {v.approval['call']['arguments'].get('to_version')}  [Approve] [Reject]")
    if v.verdict:
        lines.append(f"Verdict: {json.dumps(v.verdict, sort_keys=True)}")
    return "\n".join(lines)


def web(v: ExecutionView) -> dict[str, Any]:
    return {"id": v.execution_id, "incident": v.incident_id, "status": v.status, "lead": _lead(v),
            "hypotheses": [h.model_dump() for h in v.assessment.hypotheses] if v.assessment else [], "approval": v.approval, "action": v.action}


def api(v: ExecutionView) -> dict[str, Any]:
    return json.loads(v.model_dump_json())


def cli(v: ExecutionView) -> str:
    lead = _lead(v)
    return f"{v.execution_id}  {v.status:<17} {v.incident_id or '-':<9} {lead['id'] + ' ' + lead['confidence'] if lead else ''}"


RENDER = {"chat": chat, "web": web, "api": api, "event": chat, "workflow": api, "scheduler": api, "cicd": api, "agent": api, "cli": cli}
