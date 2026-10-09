"""Scoped, short-lived execution capabilities: the contract between the enforcement plane and the execution boundary.

The broker issues a capability only after policy, approval and budget have passed.  It is a compact signed token
(base64url(header).base64url(claims).base64url(HMAC-SHA256)) naming exactly one invocation: the tool, the operation, the
bound arguments, the invocation digest, the agent, the user it acts for, the workload, an audience, an expiry and a
single-use id.  The resource side (here: the release-pipeline MCP server) verifies it against the call it actually
receives, so a caller that bypasses the platform's gateway still cannot act.

What this models, and what it does not: it models the architectural contract of a credential broker (authorize first,
then mint something narrow and short-lived for this exact action).  It is not a secrets platform: one symmetric key from
the environment stands in for asymmetric signing keys, key rotation, sender-constrained tokens (DPoP / mTLS-bound) and a
real token service.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from agentic_platform.canonical import BOUND, canonical_json, invocation_digest

ISSUER = "capability-broker"
DEFAULT_TTL_S = 120


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class CapabilityError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail = code, detail


def mint(key: bytes, claims: dict[str, Any]) -> str:
    head = _b64(canonical_json({"alg": "HS256", "typ": "cap+jwt"}).encode())
    body = _b64(canonical_json(claims).encode())
    sig = _b64(hmac.new(key, f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}"


def issue(key: bytes, inv: dict[str, Any], *, workload: str, audience: str, decision_id: str, approval_id: str | None,
          ttl_s: int = DEFAULT_TTL_S, now: float | None = None, jti: str | None = None) -> tuple[str, dict[str, Any]]:
    now = time.time() if now is None else now
    claims = {
        "iss": ISSUER, "sub": inv["agent"], "act": inv["on_behalf_of"], "wl": workload, "aud": audience,
        "tool": inv["tool"], "op": inv["operation"], "args": inv["arguments"],
        "ctx": {k: inv[k] for k in BOUND if k != "arguments"},
        "digest": invocation_digest(inv), "decision": decision_id, "approval": approval_id,
        "iat": int(now), "exp": int(now) + ttl_s, "jti": jti or "cap-" + uuid.uuid4().hex[:16], "uses": 1,
    }
    return mint(key, claims), claims


def decode_unverified(token: str) -> dict[str, Any]:
    return json.loads(_unb64(token.split(".")[1]))


@dataclass
class Verified:
    claims: dict[str, Any]
    digest: str


def verify(key: bytes, token: str | None, *, audience: str, tool: str, arguments: dict[str, Any], seen_jti: set[str] | None = None,
           now: float | None = None, operation: str | None = None) -> Verified:
    """Check a capability against the call actually being made.  Raises CapabilityError(code) on the first failure."""
    if not token:
        raise CapabilityError("CAPABILITY_MISSING", "consequential tool called without an execution capability")
    parts = token.split(".")
    if len(parts) != 3:
        raise CapabilityError("CAPABILITY_MALFORMED")
    want = _b64(hmac.new(key, f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(want, parts[2]):
        raise CapabilityError("CAPABILITY_SIGNATURE_INVALID")
    c = json.loads(_unb64(parts[1]))
    now = time.time() if now is None else now
    if now >= c["exp"]:
        raise CapabilityError("CAPABILITY_EXPIRED", f"expired {int(now - c['exp'])} s ago")
    if c["aud"] != audience:
        raise CapabilityError("CAPABILITY_AUDIENCE_MISMATCH", f"issued for {c['aud']}")
    if c["tool"] != tool:
        raise CapabilityError("CAPABILITY_SCOPE_MISMATCH", f"tool: issued for {c['tool']}, called {tool}")
    if operation is not None and c.get("op") != operation:   # the resource knows what its own tool does; the claim must say the same
        raise CapabilityError("CAPABILITY_SCOPE_MISMATCH", f"operation: issued for {c.get('op')}, called {operation}")
    for k in sorted(set(c["args"]) | set(arguments)):
        if c["args"].get(k) != arguments.get(k):
            raise CapabilityError("CAPABILITY_SCOPE_MISMATCH", f"{k}: issued for {c['args'].get(k)!r}, called with {arguments.get(k)!r}")
    actual = invocation_digest({**c["ctx"], "arguments": arguments})
    if actual != c["digest"]:
        raise CapabilityError("CAPABILITY_DIGEST_MISMATCH", f"token digest {c['digest'][:12]}…, call digest {actual[:12]}…")
    if seen_jti is not None and c["jti"] in seen_jti:
        raise CapabilityError("CAPABILITY_REPLAYED", f"{c['jti']} was already used")
    return Verified(c, actual)
