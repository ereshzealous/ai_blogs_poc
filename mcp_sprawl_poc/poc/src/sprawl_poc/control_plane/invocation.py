"""Capability → implementation → invocation.

A *capability* is the business job (``order.refund``).  An *implementation* is one
MCP tool that can do it (``refunds.refund_order``).  An *invocation* is an
implementation plus concrete canonical arguments in a concrete context.  Policy,
approval and the gateway only ever see invocations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..util import canonical_json, sha256_obj


@dataclass(frozen=True)
class CallContext:
    request_id: str
    requester_id: str
    requester_role: str
    user_scopes: frozenset[str]
    agent_id: str
    agent_scopes: frozenset[str]
    environment: str  # the environment this session is allowed to act in, e.g. "prod"

    def as_record(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "requester_id": self.requester_id,
            "requester_role": self.requester_role,
            "user_scopes": sorted(self.user_scopes),
            "agent_id": self.agent_id,
            "agent_scopes": sorted(self.agent_scopes),
            "environment": self.environment,
        }


@dataclass(frozen=True)
class Invocation:
    implementation: str  # qualified "server.tool"
    arguments: dict[str, Any]
    context: CallContext
    bound_fields: tuple[str, ...] = field(default=())  # which argument values the platform bound

    @property
    def server(self) -> str:
        return self.implementation.split(".", 1)[0]

    @property
    def tool(self) -> str:
        return self.implementation.split(".", 1)[1]

    def canonical(self) -> dict[str, Any]:
        return {
            "implementation": self.implementation,
            "arguments": self.arguments,
            "environment": self.context.environment,
            "requester_id": self.context.requester_id,
            "agent_id": self.context.agent_id,
            "request_id": self.context.request_id,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.canonical())

    def digest(self, policy_version: str) -> str:
        """The approval binding: any change to tool, argument, env, requester or request voids it."""
        return sha256_obj({**self.canonical(), "policy_version": policy_version})
