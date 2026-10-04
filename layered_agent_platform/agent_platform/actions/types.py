"""Contracts of the tool & action layer. Agents depend on `ToolPort` only."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Protocol


class Decision(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


def canonical(arguments: dict[str, Any]) -> str:
    return json.dumps({k: v for k, v in arguments.items() if k != "idempotency_key"}, sort_keys=True, separators=(",", ":"))


def digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]


@dataclass(frozen=True)
class Invocation:
    tool_id: str
    arguments: dict[str, Any]

    def digest(self) -> str:
        return digest(self.tool_id, canonical(self.arguments))


@dataclass(frozen=True)
class ActionContext:
    user_id: str
    agent_id: str
    workflow_id: str
    step: str
    incident_environment: str | None = None


@dataclass
class PolicyResult:
    decision: Decision
    rule_id: str
    reason: str
    digest: str
    environment: str | None = None
    approver_role: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["decision"] = self.decision.value
        return d


@dataclass(frozen=True)
class ApprovalGrant:
    """Proof that a human with the right role approved exactly this invocation."""

    digest: str
    approver: str
    role: str
    approved_at: str


@dataclass
class ActionResult:
    tool_id: str
    status: str  # executed | denied | approval_required | failed | unknown_tool
    result: Any = None
    error: str | None = None
    policy: PolicyResult | None = None
    attempts: int = 0
    replayed: bool = False
    latency_ms: float = 0.0
    operation_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "executed" and self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {"tool_id": self.tool_id, "status": self.status, "result": self.result, "error": self.error,
                "policy": self.policy.to_dict() if self.policy else None, "attempts": self.attempts,
                "replayed": self.replayed, "latency_ms": round(self.latency_ms, 1), "operation_id": self.operation_id}


class ToolPort(Protocol):
    """What an agent sees: tool definitions and a way to call them. Policy and transport stay hidden."""

    def definitions(self) -> list[dict[str, Any]]: ...

    async def call(self, exposed_name: str, arguments: dict[str, Any]) -> str: ...
