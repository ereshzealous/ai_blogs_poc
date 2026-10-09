"""Canonical action representation.  The one definition every component uses to say "this exact invocation".

Canonical JSON: keys sorted, no insignificant whitespace, UTF-8, strings NFC-normalised.  The invocation digest is
SHA-256 over that byte string.  Approval records, capability claims, idempotency keys and evidence all carry this digest,
so a change to any bound field (tool, operation, arguments, environment, tenant, requester, agent, workflow) is a change
of identity: an approval or capability for the old digest does not cover the new one.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any

SCHEMA = "invocation/v1"
# The fields an invocation digest binds.  Nothing else (timestamps, trace ids, rationale text) is part of the action.
BOUND = ("schema", "tenant", "environment", "tool", "tool_version", "operation", "arguments", "incident", "workflow_id", "agent", "on_behalf_of")


def _norm(v: Any) -> Any:
    if isinstance(v, str):
        return unicodedata.normalize("NFC", v)
    if isinstance(v, dict):
        return {_norm(k): _norm(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    return v


def canonical_json(obj: Any) -> str:
    return json.dumps(_norm(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_id(prefix: str, *parts: object, n: int = 12) -> str:
    """Content-derived identifiers: the same run produces the same ids, in any process, after any restart."""
    return f"{prefix}-" + sha256(canonical_json([str(p) for p in parts]))[:n]


def invocation(*, tenant: str, environment: str, tool: str, tool_version: str, operation: str, arguments: dict[str, Any],
               incident: str, workflow_id: str, agent: str, on_behalf_of: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "tenant": tenant, "environment": environment, "tool": tool, "tool_version": tool_version,
            "operation": operation, "arguments": dict(arguments), "incident": incident, "workflow_id": workflow_id,
            "agent": agent, "on_behalf_of": on_behalf_of}


def invocation_digest(inv: dict[str, Any]) -> str:
    missing = [k for k in BOUND if k not in inv]
    if missing:
        raise ValueError(f"invocation is missing bound fields: {missing}")
    return sha256(canonical_json({k: inv[k] for k in BOUND}))
