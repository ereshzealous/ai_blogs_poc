"""The token broker: turns an execution identity into a tool credential at the last boundary.

One tool-facing identity per capability class and environment, never one per platform.  Each credential names one
audience and lives ten minutes.  Agents never see these credentials; only the gateway asks for them.
"""

from __future__ import annotations

from aid.config import Clock, load, short_id
from aid.contracts import ExecutionToken, ToolCredential


class BrokerError(Exception):
    pass


class TokenBroker:
    def __init__(self, clock: Clock, env: str = "production"):
        cfg = load("tool_identities.yaml")
        self.identities = cfg["tool_identities"]
        self.ttl = float(cfg["credential_ttl_s"])
        self.clock, self.env = clock, env
        self.disabled: set[str] = set()
        self.minted: list[ToolCredential] = []

    def mint(self, tok: ExecutionToken, capability_class: str) -> ToolCredential:
        key = f"{capability_class}@{self.env}"
        ident = self.identities.get(key)
        if ident is None:
            raise BrokerError(f"no tool identity for {key}")
        if key in self.disabled:
            raise BrokerError(f"tool identity {key} is disabled")
        now = self.clock.now()
        cred = ToolCredential(credential_id=short_id("cred", tok.execution_id, key, now, len(self.minted)), principal=ident["principal"],
                              tool_identity=key, aud=ident["system"], permissions=tuple(ident["permissions"]), iat=now, exp=now + self.ttl,
                              execution_id=tok.execution_id)
        self.minted.append(cred)
        return cred
