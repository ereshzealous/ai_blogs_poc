"""The identity contracts.  Everything that crosses a boundary in this POC is one of these models, extra="forbid".

The shapes follow OAuth 2.0 Token Exchange (RFC 8693) semantics without its wire format: a token has a subject (whose
authority), an actor chain (who is acting, nested, most recent first), scopes, an audience, an expiry and a
confirmation claim that binds it to one workload (sender-constrained, RFC 9700).  This is a simulation, not an
implementation of either RFC.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EventProvenance(Strict):
    """What an event says about itself.  Recorded next to, never instead of, the sender's authenticated identity."""

    source: str          # e.g. datadog/monitors
    event_id: str        # unique per source
    rule: str            # the monitor rule that fired; whoever edits it is an invoker nobody sees


class Actor(Strict):
    """RFC 8693 `act`: the current actor, with the previous actor nested inside."""

    sub: str             # agent@version
    act: Actor | None = None

    def chain(self) -> list[str]:
        out, a = [], self
        while a:
            out.append(a.sub)
            a = a.act
        return out


class ExecutionToken(Strict):
    """Who is acting, on whose authority, with how much of it, from which workload, until when."""

    token_id: str
    execution_id: str
    sub: str                     # the subject: the human it acts for, or the invoking workload when there is none
    invoker: str                 # the authenticated head that started the execution
    on_behalf_of: str | None     # a human, if any; None is a recorded fact, not a gap
    grant_id: str | None         # the delegation grant from the human, revocable on its own
    act: Actor
    scopes: tuple[str, ...]
    cnf: str                     # the SPIFFE id of the only workload allowed to present this token
    iat: float
    exp: float
    depth: int = 0
    provenance: EventProvenance | None = None
    invoker_credential: str


class ToolCredential(Strict):
    """A tool-facing credential minted by the broker for one capability class, one audience, ten minutes."""

    credential_id: str
    principal: str               # what the tool authenticates, e.g. system:serviceaccount:payments:incident-remediator
    tool_identity: str           # class@environment
    aud: str                     # the one system that accepts it
    permissions: tuple[str, ...]
    iat: float
    exp: float
    execution_id: str | None = None
    impersonated_user: str | None = None


class CapabilityCall(Strict):
    capability: str
    arguments: dict[str, Any]


class Decision(Strict):
    effect: Literal["ALLOW", "DENY", "REQUIRE_APPROVAL", "EXECUTED", "REJECTED"]
    rule: str
    reason: str
    approval_id: str | None = None
    output: dict[str, Any] | None = None
