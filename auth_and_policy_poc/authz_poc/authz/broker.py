"""Credential broker: the only source of tool credentials. It issues them to the gateway, for one exact call, and only
after a permitting decision.

This is the part of non-bypassability the POC can model. The agent runtime holds no tool credentials, and the tools
(authz/tools.py) refuse any call that does not carry a credential this broker signed for that action, resource,
environment and argument set. A credential is single-use and expires a minute after issue. What the POC cannot model is
the network half: in production, network policy must also leave the runtime no route to Kubernetes, the log store or
the deploy system except through the gateway.

The signing key is fixed so that runs are deterministic. A production broker would hold a real key, or exchange the
execution identity for a short-lived, audience-bound token (RFC 8693) after the gateway's decision.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any

from .model import ALLOW, APPROVAL, CONSTRAINED, Decision, digest
from .pip import ts

TTL = timedelta(seconds=60)
CLAIMS = ("decision_id", "action", "resource", "environment", "arguments", "expires_at")


class CredentialError(PermissionError):
    """A tool refused the call: no credential, or one that does not cover it."""


def iso(t) -> str:
    return t.isoformat().replace("+00:00", "Z")


class CredentialBroker:
    def __init__(self, key: bytes = b"authz-poc broker key (fixed so runs are deterministic)"):
        self._key = key
        self._used: set[str] = set()
        self.issued: list[str] = []

    def _sign(self, claims: dict[str, Any]) -> str:
        return hmac.new(self._key, json.dumps(claims, sort_keys=True).encode(), hashlib.sha256).hexdigest()[:16]

    def issue(self, d: Decision, action: str, resource: str, environment: str, arguments: dict[str, Any], time: str,
              approval: dict[str, Any] | None = None) -> dict[str, Any]:
        """A credential for exactly this call. Refused without a permitting decision, and refused for an
        approval-gated call unless its approval has been granted."""
        if d.decision not in (ALLOW, CONSTRAINED, APPROVAL):
            raise CredentialError(f"no credential for a {d.decision} decision")
        if d.decision == APPROVAL and not (approval and approval.get("status") == "approved"):
            raise CredentialError("an approval-gated call needs a granted approval")
        claims = {"decision_id": d.decision_id, "action": action, "resource": resource, "environment": environment,
                  "arguments": digest(arguments, 16), "expires_at": iso(ts(time) + TTL)}
        token = {"id": "cred-" + digest(claims, 10), **claims, "sig": self._sign(claims)}
        self.issued.append(token["id"])
        return token

    def redeem(self, token: dict[str, Any] | None, action: str, resource: str, environment: str,
               arguments: dict[str, Any], time: str) -> None:
        """What a tool checks before any effect: signed by the broker, for this call, unexpired, unused."""
        if not token:
            raise CredentialError("no credential: tools are reachable only through the gateway")
        claims = {k: token.get(k) for k in CLAIMS}
        if not hmac.compare_digest(str(token.get("sig", "")), self._sign(claims)):
            raise CredentialError("credential was not issued by the broker")
        if (claims["action"], claims["resource"], claims["environment"], claims["arguments"]) != (
                action, resource, environment, digest(arguments, 16)):
            raise CredentialError("credential does not cover this call")
        if ts(time) >= ts(claims["expires_at"]):
            raise CredentialError("credential expired")
        if token["id"] in self._used:
            raise CredentialError("credential already used")
        self._used.add(token["id"])
