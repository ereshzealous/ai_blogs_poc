"""Deterministic policy engine: ALLOW, REQUIRE_APPROVAL or DENY for one concrete invocation.

The engine never calls a model and never reads MCP annotations. Same inputs, same decision.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from control_plane.paths import POLICY_FILE
from control_plane.registry.registry import RegistryRecord


class Decision(StrEnum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


@dataclass(frozen=True)
class Identity:
    user_id: str
    roles: tuple[str, ...]
    agent_id: str = "incident-agent"


@dataclass(frozen=True)
class PolicyInput:
    identity: Identity
    tool_id: str
    arguments: dict[str, Any]
    record: RegistryRecord | None
    environment: str
    request_id: str


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    rule_id: str
    reason: str
    tool_id: str
    environment: str
    risk: str | None
    missing_scopes: list[str] = field(default_factory=list)
    invocation_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"decision": self.decision.value, "rule_id": self.rule_id, "reason": self.reason, "tool_id": self.tool_id,
                "environment": self.environment, "risk": self.risk, "missing_scopes": self.missing_scopes,
                "invocation_digest": self.invocation_digest}


def invocation_digest(tool_id: str, arguments: dict[str, Any], environment: str, request_id: str) -> str:
    canonical = json.dumps({"tool_id": tool_id, "arguments": arguments, "environment": environment, "request_id": request_id},
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class PolicyEngine:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.rules = config["rules"]
        self.default = Decision(config.get("default_decision", "DENY"))

    @classmethod
    def load(cls, path: str | Path = POLICY_FILE) -> PolicyEngine:
        with open(path, encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh))

    # -- scopes -----------------------------------------------------------------------------
    def _granted(self, patterns: list[str], scope: str) -> bool:
        return any(fnmatch.fnmatchcase(scope, p) for p in patterns)

    def missing_scopes(self, identity: Identity, required: list[str]) -> list[str]:
        user_patterns = [p for role in identity.roles for p in self.config["roles"].get(role, [])]
        agent_patterns = self.config["agents"].get(identity.agent_id, [])
        return [s for s in required if not (self._granted(user_patterns, s) and self._granted(agent_patterns, s))]

    # -- evaluation ---------------------------------------------------------------------------
    def evaluate(self, inp: PolicyInput) -> PolicyResult:
        rec = inp.record
        digest = invocation_digest(inp.tool_id, inp.arguments, inp.environment, inp.request_id)
        missing = self.missing_scopes(inp.identity, rec.required_scopes) if rec else []
        facts: dict[str, Any] = {
            "registered": rec is not None,
            "lifecycle": rec.lifecycle if rec else None,
            "deprecated": rec.deprecated if rec else None,
            "environment": inp.environment,
            "environment_allowed": (inp.environment in rec.environments) if rec else None,
            "scopes_satisfied": not missing,
            "destructive": rec.destructive if rec else None,
            "risk": rec.risk if rec else None,
        }
        for rule in self.rules:
            if self._matches(rule["when"], facts):
                reason = rule.get("reason", "").format(
                    lifecycle=facts["lifecycle"], replaced_by=(rec.replaced_by if rec else None) or "the replacement tool",
                    environment=inp.environment, missing_scopes=", ".join(missing))
                return PolicyResult(Decision(rule["decision"]), rule["id"], reason, inp.tool_id, inp.environment,
                                    facts["risk"], missing, digest)
        return PolicyResult(self.default, "default", "No rule matched.", inp.tool_id, inp.environment, facts["risk"], missing, digest)

    @staticmethod
    def _matches(when: dict[str, Any], facts: dict[str, Any]) -> bool:
        for key, expected in when.items():
            actual = facts.get(key)
            if actual is None:
                return False
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True
