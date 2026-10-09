"""The approval gate. Deliberately thin: Human-in-the-Loop is the next article.

What it shows here is only the boundary: authorization returned ALLOW_WITH_APPROVAL, so the call is valid in principle;
the gate decides whether it may *proceed*. An approval opens only for an ALLOW_WITH_APPROVAL decision (there is no path
from DENY to a human), and it is bound to one exact call: the request fingerprint (principal, acting-for, action,
resource, environment, incident, arguments), the policy version and decision that required it, one approver role, a
deadline, and a single use. Escalation, reminders, quorum and intervention belong to the Human-in-the-Loop article.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .model import APPROVAL, Decision, Request, digest
from .pip import PIP, ts


def minutes(s: str) -> timedelta:
    return timedelta(minutes=int(s.rstrip("m")))


class ApprovalGate:
    def __init__(self, pip: PIP):
        self.pip = pip
        self.pending: dict[str, dict[str, Any]] = {}

    def open(self, req: Request, d: Decision) -> dict[str, Any]:
        if d.decision != APPROVAL:
            raise ValueError(f"an approval opens only for ALLOW_WITH_APPROVAL, not {d.decision}")
        apr = {
            "approval_id": "apr-" + digest([req.fingerprint(), d.decision_id], 10),
            "decision_id": d.decision_id,
            "request_fingerprint": req.fingerprint(),
            "incident_id": req.context.get("incident_id"),
            "policy_version": d.policy_version,
            "requested_by": req.principal,
            "acting_for": req.acting_for,
            "approver_role": d.constraints["approverRole"],
            "requested_at": req.context["time"],
            "expires_at": (ts(req.context["time"]) + minutes(d.constraints["expiresIn"])).isoformat().replace("+00:00", "Z"),
            "status": "pending",
        }
        self.pending[apr["approval_id"]] = apr
        return apr

    def decide(self, approval_id: str, approver: str, time: str) -> tuple[bool, str]:
        apr = self.pending.get(approval_id)
        if apr is None:
            return False, "unknown approval"
        if apr["status"] != "pending":
            return False, f"approval is already {apr['status']}"
        if approver == apr["requested_by"]:
            return False, "The requester cannot approve its own action"
        if not self.pip.is_human(approver):
            return False, f"{approver} is not a human principal"
        if apr["approver_role"] not in self.pip.roles_of(approver):
            return False, f"{approver} does not hold {apr['approver_role']}"
        if ts(time) >= ts(apr["expires_at"]):
            return False, "Approval window expired"
        apr.update(status="approved", approved_by=approver, approved_at=time)
        return True, "approved"

    def consume(self, approval_id: str, time: str) -> None:
        """Single use: once the approved call has executed, the approval covers nothing else."""
        self.pending[approval_id].update(status="used", used_at=time)
