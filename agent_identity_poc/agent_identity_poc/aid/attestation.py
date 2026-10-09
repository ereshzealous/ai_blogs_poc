"""Workload attestation, simulated: each runtime holds a short-lived SVID for its SPIFFE id, rotated on schedule.

The gateway asks the attestor who is presenting a call.  A quarantined workload fails attestation at once, which is
what makes runtime revocation immediate rather than waiting for a token to expire.
"""

from __future__ import annotations

from aid.config import Clock, short_id

SVID_TTL_S = 3600.0


class Attestor:
    def __init__(self, clock: Clock, spiffe_ids: list[str]):
        self.clock = clock
        self.quarantined: set[str] = set()
        self.svids: dict[str, dict] = {}
        for s in spiffe_ids:
            self.issue(s)

    def issue(self, spiffe_id: str) -> str:
        now = self.clock.now()
        svid = short_id("svid", spiffe_id, now)
        self.svids[svid] = {"spiffe": spiffe_id, "exp": now + SVID_TTL_S}
        return svid

    def current(self, spiffe_id: str) -> str:
        """The workload's live SVID, rotated when the old one is within ten minutes of expiry."""
        live = [(v["exp"], k) for k, v in self.svids.items() if v["spiffe"] == spiffe_id and v["exp"] > self.clock.now()]
        if not live or max(live)[0] - self.clock.now() < 600:
            return self.issue(spiffe_id)
        return max(live)[1]

    def verify(self, svid: str) -> str | None:
        """The attested SPIFFE id behind an SVID, or None."""
        v = self.svids.get(svid)
        if not v or v["exp"] <= self.clock.now() or v["spiffe"] in self.quarantined:
            return None
        return v["spiffe"]
