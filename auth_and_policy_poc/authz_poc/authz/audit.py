"""Hash-chained decision log, the same shape as the Headless and Identity POCs: editing any record breaks the chain."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class AuditLog:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def write(self, kind: str, time: str, record: dict[str, Any]) -> dict[str, Any]:
        prev = self.records[-1]["hash"] if self.records else "0" * 16
        record = json.loads(json.dumps(record, default=str))  # snapshot: later changes to the caller's dict must not leak in
        body = {"seq": len(self.records) + 1, "time": time, "kind": kind, "record": record, "prev": prev}
        body["hash"] = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]
        self.records.append(body)
        return body

    def verify(self) -> bool:
        prev = "0" * 16
        for r in self.records:
            body = {k: v for k, v in r.items() if k != "hash"}
            if r["prev"] != prev:
                return False
            if hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16] != r["hash"]:
                return False
            prev = r["hash"]
        return True

    def dump(self, path: Path) -> None:
        path.write_text("".join(json.dumps(r, sort_keys=False) + "\n" for r in self.records))
