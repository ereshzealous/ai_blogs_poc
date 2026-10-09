"""The platform audit: append-only and hash-chained.  One record per hop that matters, each carrying the identity
chain as it stood at that moment.  The tools' own logs are kept separately (aid/tools.py) and are never merged in.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from aid.config import Clock

GENESIS = "0" * 64


def _h(prev: str, t: float, kind: str, body: str) -> str:
    return hashlib.sha256(f"{prev}|{t}|{kind}|{body}".encode()).hexdigest()


class AuditLog:
    def __init__(self, clock: Clock):
        self.clock = clock
        self.rows: list[dict[str, Any]] = []

    def record(self, kind: str, /, **fields: Any) -> dict[str, Any]:
        prev = self.rows[-1]["hash"] if self.rows else GENESIS
        body = json.dumps(fields, sort_keys=True, default=str)
        t = self.clock.now()
        row = {"n": len(self.rows) + 1, "t": t, "kind": kind, "record": fields, "prev": prev, "hash": _h(prev, t, kind, body)}
        self.rows.append(row)
        return row

    def verify(self, rows: list[dict[str, Any]] | None = None) -> tuple[bool, int | None]:
        prev = GENESIS
        for r in rows if rows is not None else self.rows:
            if r["prev"] != prev or r["hash"] != _h(prev, r["t"], r["kind"], json.dumps(r["record"], sort_keys=True, default=str)):
                return False, r["n"]
            prev = r["hash"]
        return True, None

    def calls(self, capability: str | None = None) -> list[dict[str, Any]]:
        return [r["record"] for r in self.rows if r["kind"] == "capability.call" and (capability is None or r["record"]["capability"] == capability)]

    def jsonl(self) -> str:
        return "".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in self.rows)
