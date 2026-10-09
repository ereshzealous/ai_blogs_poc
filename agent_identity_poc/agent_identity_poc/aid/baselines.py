"""The two baselines the production pattern is compared with.  Each records the identity its own model carries, plus
the action and the approver (both baselines keep an approval step, to keep the comparison about identity).

shared_sa      Every agent, head and runtime uses one "AI automation" account per system.  The tool sees that account;
               the platform's identity of record is that account.
impersonation  The agent is handed the human's own token (token passthrough).  The tool sees the human; the actor is
               lost.  With no human (an event, a CI job) there is nothing to impersonate, so it falls back to the
               shared account, which is what such platforms end up doing.
"""

from __future__ import annotations

from typing import Any

from aid.config import Clock, load
from aid.contracts import ToolCredential
from aid.tools import shared_principals

FAR = 365 * 86400.0


def shared_credentials(clock: Clock, generation: int = 0) -> dict[str, ToolCredential]:
    """Static secrets: no audience, no binding, a year to live.  Rotation means a new generation for everyone."""
    sp = shared_principals(load("shared_sa.yaml"))
    return {s: ToolCredential(credential_id=f"sa-static-{s}-g{generation}", principal=p, tool_identity="ai-automation", aud="any",
                              permissions=(), iat=clock.now(), exp=clock.now() + FAR) for s, p in sp.items()}


def user_credentials(clock: Clock, human_oidc: str, execution_id: str) -> dict[str, ToolCredential]:
    """The human's session token, passed through to every system: the tool authorizes the human."""
    return {s: ToolCredential(credential_id=f"idt-{human_oidc.split('@')[0]}-{execution_id[-6:]}", principal=human_oidc,
                              tool_identity="user-session", aud="any", permissions=(), iat=clock.now(), exp=clock.now() + 8 * 3600,
                              execution_id=execution_id) for s in ("kubernetes", "jira", "slack", "telemetry")}


def baseline_record(mode: str, ctx: dict[str, Any], capability: str, arguments: dict[str, Any], cred: ToolCredential,
                    authorized_by: str | None, approval_id: str | None, ok: bool) -> dict[str, Any]:
    rec: dict[str, Any] = {"capability": capability, "arguments": arguments, "tool_principal": cred.principal,
                           "credential_id": cred.credential_id, "authorized_by": authorized_by, "approval_id": approval_id,
                           "status": "ok" if ok else "tool refused"}
    if mode == "impersonation" and ctx.get("subject"):
        rec["subject"] = ctx["subject"]           # the token's sub: the human.  No actor, no head, no scopes.
        rec["on_behalf_of"] = ctx["subject"]
    if mode == "impersonation" and not ctx.get("subject"):
        rec["fallback"] = "shared account (no human to impersonate)"
    return rec
