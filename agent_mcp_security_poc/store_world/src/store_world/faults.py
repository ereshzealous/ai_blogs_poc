"""Fault hooks for the notes after F1. Built here so the world they switch on is the world F1 measured.

F1 runs with every fault off: its question is capability resolution and execution governance, not reliability. A
later note turns one on and keeps everything else identical, so the difference it measures is the fault.
"""

from __future__ import annotations

from dataclasses import dataclass, field

AVAILABLE: tuple[str, ...] = (
    "payment_timeout",        # the payment API does not answer within the timeout
    "payment_lost_response",  # the capture succeeds but the response never arrives: how a double charge happens
    "carrier_down",           # a carrier API is unavailable, so tracking and redirects fail
    "duplicate_webhook",      # the same event is delivered twice
)


@dataclass(frozen=True)
class Faults:
    enabled: tuple[str, ...] = ()
    available: tuple[str, ...] = field(default=AVAILABLE)

    @classmethod
    def default(cls) -> Faults:
        """F1's setting: everything off."""
        return cls()

    def with_enabled(self, *names: str) -> Faults:
        for name in names:
            if name not in self.available:
                raise ValueError(f"unknown fault {name!r}; available: {', '.join(self.available)}")
        return Faults(enabled=tuple(sorted({*self.enabled, *names})), available=self.available)

    def is_on(self, name: str) -> bool:
        return name in self.enabled
