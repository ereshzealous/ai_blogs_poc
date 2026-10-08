"""In-memory transport. Every 'outbound' call (HTTP POST, email send, MCP call to a mock server) goes here. Nothing is
ever put on a socket: external networking is disabled for the lab. The transport records what WOULD have been sent, which
is exactly what the oracle inspects to decide whether data left the simulation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Sent:
    channel: str                 # "http_post" | "email" | "mcp"
    destination: str             # a mock host or address (always .invalid for sinks)
    payload: Any                 # the bytes/body that would have travelled
    labels: list[str] = field(default_factory=list)


class InMemoryTransport:
    """A sink the oracle reads. `deliver` records and returns; it never opens a connection."""

    def __init__(self) -> None:
        self.sent: list[Sent] = []

    def deliver(self, channel: str, destination: str, payload: Any, labels: list[str] | None = None) -> dict[str, Any]:
        rec = Sent(channel=channel, destination=destination, payload=payload, labels=labels or [])
        self.sent.append(rec)
        # A mock 200 so the toy (arm A) believes the exfiltration "worked" — the point of the demo.
        return {"status": 200, "destination": destination, "recorded": True}

    def to_destination(self, destination: str) -> list[Sent]:
        return [s for s in self.sent if s.destination == destination]

    def all_payloads_text(self) -> str:
        """Everything that left, flattened to text, so the oracle can scan for planted canaries."""
        from redteam.base import canonical
        return "\n".join(canonical(s.payload) for s in self.sent)
