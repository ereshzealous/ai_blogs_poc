"""Append-only, hash-chained audit log.

Each record carries the previous record's hash, so an edited or deleted line breaks
verification.  This is tamper-*evident* within the POC, not tamper-proof storage: a
production deployment would ship records to WORM / external storage.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..util import append_jsonl, canonical_json, read_jsonl, sha256_text

GENESIS = "0" * 64


class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        records = read_jsonl(self.path)
        self._prev = records[-1]["record_hash"] if records else GENESIS
        self._seq = len(records)

    def append(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {"seq": self._seq, "ts": round(time.time(), 3), "kind": kind, "payload": payload, "prev_hash": self._prev}
        record_hash = sha256_text(canonical_json(body))
        record = {**body, "record_hash": record_hash}
        append_jsonl(self.path, record)
        self._prev = record_hash
        self._seq += 1
        return record

    def records(self) -> list[dict[str, Any]]:
        return read_jsonl(self.path)

    @staticmethod
    def verify(path: Path) -> tuple[bool, str]:
        prev = GENESIS
        for i, rec in enumerate(read_jsonl(path)):
            body = {k: v for k, v in rec.items() if k != "record_hash"}
            if rec.get("prev_hash") != prev:
                return False, f"record {i}: prev_hash mismatch"
            if sha256_text(canonical_json(body)) != rec.get("record_hash"):
                return False, f"record {i}: record_hash mismatch"
            prev = rec["record_hash"]
        return True, "ok"
