"""Identity resolution: what a channel saw → one enterprise principal.

    Slack U04ALICE ─┐
    Web oidc|alice ─┼─→ principal "alice" → roles from the layered platform
    CLI alice@...  ─┘

The resolver links identities; it does not grant anything. Roles come from the platform's principal directory, so
the same person has the same authority in every channel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from headless_ai_platform.contracts import Actor, CapabilityError, ErrorCode
from headless_ai_platform.settings import channel_identities


@dataclass(frozen=True)
class Principal:
    principal_id: str
    display_name: str
    roles: tuple[str, ...]
    via: str                           # how the link was made: "linked" or "on-call:<service>"

    def has_role(self, role: str | None) -> bool:
        return role is None or role in self.roles


Directory = Callable[[str], tuple[str, tuple[str, ...]] | None]  # principal_id -> (display name, roles)


class IdentityResolver:
    def __init__(self, directory: Directory, links: dict[str, Any] | None = None):
        self.directory = directory
        self.links = links if links is not None else channel_identities()

    def resolve(self, actor: Actor, *, service: str | None = None) -> Principal:
        if actor.channel == "event":
            principal_id, via = self._on_call(actor.channel_subject, service)
        else:
            principal_id = (self.links.get("channels", {}).get(actor.channel) or {}).get(actor.channel_subject)
            via = "linked"
        if principal_id is None:
            raise CapabilityError(ErrorCode.UNKNOWN_IDENTITY,
                                  f"{actor.channel} identity {actor.channel_subject!r} is not linked to an enterprise principal")
        return self.resolve_principal(principal_id, via)

    def resolve_principal(self, principal_id: str, via: str = "stored") -> Principal:
        entry = self.directory(principal_id)
        if entry is None:
            raise CapabilityError(ErrorCode.UNKNOWN_IDENTITY, f"principal {principal_id!r} is not in the directory")
        return Principal(principal_id, entry[0], entry[1], via)

    def _on_call(self, source: str, service: str | None) -> tuple[str | None, str]:
        rule = self.links.get("event_sources", {}).get(source)
        if not rule or rule.get("on_behalf_of") != "on_call":
            return None, "event"
        on_call = self.links.get("on_call", {})
        key = service if service in on_call else "default"
        return on_call.get(key), f"on-call:{key}"
