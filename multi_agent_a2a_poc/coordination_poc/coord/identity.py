"""Simulated token service: who is acting, for whom, with what authority, for which audience, until when.

Tokens are HMAC-signed JSON (header-less, JWT-like).  Claims, modelled on OAuth 2.0 Token Exchange (RFC 8693) as the
series does in T1 and F3; this is a simulation, not an implementation of the RFC:

    sub    the human (or workload) whose authority is being exercised
    act    actor chain, outermost first: [{"sub": "agent.diagnosis"}, {"sub": "agent.coordinator"}, ...]
    aud    who may accept the token (an agent principal, or "gateway")
    scope  capabilities granted; always the intersection of the parent's scope, the target's allowed scopes and the
           requested scopes, so authority only narrows across a hop
    wf     workflow id; dlg delegation id (when the token was minted for a delegation); depth hop count

A2A does not define any of this (spec v1.0.1 §7, §13.1: authorization is the agent's own model).  The token travels as
an HTTP `Authorization: Bearer` header, which is how A2A expects credentials to travel (§7.3).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from coord.util import load_config

SECRET = os.environ.get("C1_TOKEN_SECRET", "c1-simulated-token-service-secret").encode()


class AuthError(PermissionError):
    pass


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@dataclass
class Token:
    sub: str
    act: list[str]
    aud: str
    scope: list[str]
    wf: str
    exp: float
    jti: str
    depth: int = 0
    dlg: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def actor(self) -> str:
        return self.act[0] if self.act else self.sub

    def chain(self) -> str:
        return " <- ".join(self.act + [self.sub])

    def claims(self) -> dict[str, Any]:
        return {"sub": self.sub, "act": self.act, "aud": self.aud, "scope": self.scope, "wf": self.wf, "exp": self.exp,
                "jti": self.jti, "depth": self.depth, "dlg": self.dlg, **({"x": self.extra} if self.extra else {})}


class TokenService:
    def __init__(self) -> None:
        cfg = load_config("principals.yaml")
        self.principals: dict[str, dict[str, Any]] = cfg["principals"]
        self.ttl = float(cfg["token_ttl_s"])
        self.max_depth = int(cfg["max_depth"])
        self._n = 0

    # ---- encode / decode -------------------------------------------------------------------------------------------
    def encode(self, t: Token) -> str:
        body = _b64(json.dumps(t.claims(), sort_keys=True, separators=(",", ":")).encode())
        sig = _b64(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())
        return f"{body}.{sig}"

    def decode(self, raw: str, *, audience: str, now: float | None = None) -> Token:
        try:
            body, sig = raw.split(".", 1)
        except ValueError:
            raise AuthError("malformed token") from None
        good = _b64(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(good, sig):
            raise AuthError("bad signature")
        c = json.loads(_unb64(body))
        if c["aud"] != audience:
            raise AuthError(f"token audience {c['aud']} is not {audience}")
        if (now or time.time()) >= c["exp"]:
            raise AuthError("token expired")
        return Token(sub=c["sub"], act=c["act"], aud=c["aud"], scope=c["scope"], wf=c["wf"], exp=c["exp"], jti=c["jti"],
                     depth=c.get("depth", 0), dlg=c.get("dlg"), extra=c.get("x", {}))

    # ---- issue and exchange ----------------------------------------------------------------------------------------
    def _jti(self, wf: str) -> str:
        self._n += 1
        return f"tok-{wf}-{os.getpid()}-{self._n}"

    def issue_root(self, *, subject: str, invoker: str, actor: str, wf: str) -> Token:
        """The capability's execution identity: what `actor` may do for `subject`, invoked via `invoker`."""
        delegable = set(self.principals[subject]["delegable"]) & set(self.principals[invoker]["delegable"])
        scopes = sorted(delegable & set(self.principals[actor]["scopes"]))
        return Token(sub=subject, act=[actor, invoker], aud=actor, scope=scopes, wf=wf, exp=time.time() + self.ttl,
                     jti=self._jti(wf), depth=0)

    def exchange(self, parent: Token, *, target: str, requested: list[str] | None = None, dlg: str | None = None,
                 extra: dict[str, Any] | None = None) -> Token:
        """Mint a token for `target` acting under `parent`.  Scopes = parent ∩ target-allowed ∩ requested."""
        actor = parent.actor
        if target == "gateway":
            allowed = set(self.principals[actor].get("tool_scopes", self.principals[actor]["scopes"]))
            act, depth = parent.act, parent.depth
        else:
            edges = self.principals.get(actor, {}).get("may_delegate_to", [])
            if target not in edges:
                raise AuthError(f"{actor} may not delegate to {target}")
            if parent.depth + 1 > self.max_depth:
                raise AuthError(f"delegation depth {parent.depth + 1} exceeds {self.max_depth}")
            allowed = set(self.principals[target]["scopes"])
            act, depth = [target] + parent.act, parent.depth + 1
        scopes = set(parent.scope) & allowed
        if requested is not None:
            scopes &= set(requested)
        return Token(sub=parent.sub, act=act, aud=target, scope=sorted(scopes), wf=parent.wf,
                     exp=min(parent.exp, time.time() + self.ttl), jti=self._jti(parent.wf), depth=depth, dlg=dlg or parent.dlg,
                     extra=extra or {})
