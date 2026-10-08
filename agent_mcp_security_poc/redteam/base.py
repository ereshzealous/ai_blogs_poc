"""Shared primitives: canonical JSON, hashing, a fake clock, config loading, and the enums the gates speak.

No randomness and no wall-clock time enter a result: the clock is fixed and every hash is over canonical JSON, so two
runs on two machines produce byte-identical evidence.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

POC = Path(__file__).resolve().parents[1]
CONFIG = POC / "config"


def canonical(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace drift. The one serialization every hash and digest uses."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(obj).encode()).hexdigest()


def action_digest(tool: str, args: dict[str, Any]) -> str:
    """The identity of a proposed action: tool name + arguments. Approvals bind to this (T3)."""
    return sha({"tool": tool, "args": args})


def load_yaml(name: str) -> dict[str, Any]:
    return yaml.safe_load((CONFIG / name).read_text())


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    QUARANTINE = "QUARANTINE"          # an MCP tool whose metadata changed / is untrusted
    UNRESOLVED = "UNRESOLVED"          # capability not in the registry allowlist


class Arm(str, Enum):
    A = "A"   # vulnerable toy: model output executed directly; no deterministic gates
    B = "B"   # prompt + imperfect classifier/guard in front of the same unrestricted path
    C = "C"   # deterministic production-style enforcement


# The fixed, fake clock. The incident/session is 2026-11-30 (store_world session_start).
CLOCK = "2026-11-30T09:20:00Z"

# The one fake secret value in the whole lab. It is planted so the oracle can detect a leak; it is not a real credential.
MOCK_SECRET_VALUE = "SYNTHETIC_SECRET_12345"


@dataclass
class ProposedAction:
    """One step the model proposes: a tool and its arguments, plus where the idea came from (provenance)."""
    tool: str
    args: dict[str, Any]
    source: str                      # the scenario ingress that motivated it: "task" | "email" | "kb" | ...
    hostile: bool = False            # True if this step came from an untrusted-instruction marker (model-labelled only)

    @property
    def digest(self) -> str:
        return action_digest(self.tool, self.args)


@dataclass
class GateEvent:
    """One recorded decision at one gate, for the audit (I-AUDIT) and the evidence record."""
    gate: str
    decision: Decision
    rule: str
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"gate": self.gate, "decision": self.decision.value, "rule": self.rule, "detail": self.detail}
