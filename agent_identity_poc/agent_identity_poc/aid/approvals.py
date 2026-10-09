"""Approvals bound to one exact call.  Kept only as far as identity needs it: who may approve, and what an approval
grants.  An approval grants a non-delegable scope (deploy:rollback) for one call digest, once.  It can narrow what is
allowed; it never widens a scope the execution does not already hold.
"""

from __future__ import annotations

from typing import Any

from aid.config import Clock, digest, short_id
from aid.directory import Directory


class Approvals:
    def __init__(self, directory: Directory, clock: Clock):
        self.d, self.clock = directory, clock
        self.items: dict[str, dict[str, Any]] = {}

    @staticmethod
    def call_digest(execution_id: str, capability: str, arguments: dict[str, Any]) -> str:
        return digest({"execution": execution_id, "capability": capability, "arguments": arguments})

    def request(self, execution_id: str, capability: str, arguments: dict[str, Any], role: str, grant: str,
                requested_by: str) -> dict[str, Any]:
        dg = self.call_digest(execution_id, capability, arguments)
        aid = short_id("apr", dg)
        self.items.setdefault(aid, {"approval_id": aid, "digest": dg, "execution_id": execution_id, "capability": capability,
                                    "arguments": arguments, "role": role, "grant": grant, "requested_by": requested_by,
                                    "status": "PENDING", "decided_by": None})
        return self.items[aid]

    def decide(self, approval_id: str, who: str, dg: str | None = None) -> tuple[bool, str]:
        a = self.items.get(approval_id)
        if a is None:
            return False, "unknown approval"
        if a["status"] != "PENDING":
            return False, f"approval already {a['status'].lower()}"
        if self.d.kind(who) != "human":
            return False, f"{who} is not a human"
        if not self.d.has_role(who, a["role"]) or not self.d.holds(who, a["grant"]):
            return False, f"{who} lacks role {a['role']} or scope {a['grant']}"
        if (dg or a["digest"]) != a["digest"]:
            return False, "approval digest does not match the call"
        a.update(status="APPROVED", decided_by=who, decided_at=self.clock.now())
        return True, "approved"

    def consume(self, approval_id: str, dg: str) -> dict[str, Any] | None:
        a = self.items.get(approval_id)
        if not a or a["status"] != "APPROVED" or a["digest"] != dg:
            return None
        a["status"] = "CONSUMED"
        return a
