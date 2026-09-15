"""Capability registry: the enterprise's source of truth about tools.

MCP servers publish names, descriptions, schemas and *hints*. The registry adds what an enterprise
needs to decide what to surface and what to allow: owner, domain, capability, risk tier, environments,
lifecycle, authority and required scopes. It is backed by SQLite so filters are plain SQL.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from control_plane.paths import CATALOG_DIR

RISK_ORDER = {"READ_ONLY": 0, "LOW_RISK_WRITE": 1, "HIGH_RISK_WRITE": 2}
_JSON_FIELDS = ("operations", "environments", "authoritative_for", "required_scopes")
_COLUMNS = (
    "tool_id", "server", "name", "exposed_name", "description", "family", "collision_group", "domain", "capability",
    "resource_type", "operations", "environments", "read_only", "side_effect", "risk", "destructive", "requires_approval",
    "owner", "version", "deprecated", "replaced_by", "lifecycle", "authoritative_for", "required_scopes", "notes",
)


@dataclass(frozen=True)
class RegistryRecord:
    tool_id: str
    server: str
    name: str
    exposed_name: str
    description: str
    family: str
    collision_group: str | None
    domain: str
    capability: str
    resource_type: str
    operations: list[str]
    environments: list[str]
    read_only: bool
    side_effect: bool
    risk: str
    destructive: bool
    requires_approval: bool
    owner: str | None
    version: str
    deprecated: bool
    replaced_by: str | None
    lifecycle: str
    authoritative_for: list[str] = field(default_factory=list)
    required_scopes: list[str] = field(default_factory=list)
    notes: str | None = None

    @property
    def authoritative(self) -> bool:
        return bool(self.authoritative_for)

    def to_dict(self) -> dict[str, Any]:
        return {c: getattr(self, c) for c in _COLUMNS}


@dataclass
class DriftReport:
    unregistered: list[str]  # published over MCP, unknown to the registry
    not_published: list[str]  # registered, but no connected server publishes it
    annotation_mismatches: list[dict[str, Any]]  # server hints disagree with registry risk

    @property
    def clean(self) -> bool:
        return not (self.unregistered or self.annotation_mismatches)


class CapabilityRegistry:
    def __init__(self, records: Iterable[Mapping[str, Any]]):
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        cols = ", ".join(f"{c} TEXT" if c != "tool_id" else "tool_id TEXT PRIMARY KEY" for c in _COLUMNS)
        self._db.execute(f"CREATE TABLE tools ({cols})")
        rows = []
        for r in records:
            row = []
            for c in _COLUMNS:
                v = r.get(c)
                if c in _JSON_FIELDS:
                    v = json.dumps(v or [])
                elif isinstance(v, bool):
                    v = int(v)
                row.append(v)
            rows.append(row)
        self._db.executemany(f"INSERT INTO tools VALUES ({', '.join('?' for _ in _COLUMNS)})", rows)
        self._cache: dict[str, RegistryRecord] = {}

    @classmethod
    def load(cls, path: str | Path = CATALOG_DIR / "registry.json") -> CapabilityRegistry:
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh)["records"])

    # -- lookups ----------------------------------------------------------------------------
    def _record(self, row: sqlite3.Row) -> RegistryRecord:
        d = dict(row)
        for c in _JSON_FIELDS:
            d[c] = json.loads(d[c])
        for c in ("read_only", "side_effect", "destructive", "requires_approval", "deprecated"):
            d[c] = bool(int(d[c]))
        return RegistryRecord(**d)

    def get(self, tool_id: str) -> RegistryRecord | None:
        if tool_id not in self._cache:
            row = self._db.execute("SELECT * FROM tools WHERE tool_id = ?", (tool_id,)).fetchone()
            if row is None:
                return None
            self._cache[tool_id] = self._record(row)
        return self._cache[tool_id]

    def __contains__(self, tool_id: str) -> bool:
        return self.get(tool_id) is not None

    def __len__(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM tools").fetchone()[0]

    def find(
        self,
        *,
        tool_ids: Iterable[str] | None = None,
        domains: Iterable[str] | None = None,
        environment: str | None = None,
        read_only: bool | None = None,
        max_risk: str | None = None,
        lifecycles: Iterable[str] | None = ("active",),
        owner: str | None = None,
        capability: str | None = None,
    ) -> list[RegistryRecord]:
        """Metadata filter. Every argument narrows the result; None means "no constraint"."""
        where, args = [], []
        if tool_ids is not None:
            ids = list(tool_ids)
            where.append(f"tool_id IN ({', '.join('?' for _ in ids)})" if ids else "0")
            args += ids
        if domains is not None:
            ds = list(domains)
            where.append(f"domain IN ({', '.join('?' for _ in ds)})" if ds else "0")
            args += ds
        if environment is not None:
            where.append("EXISTS (SELECT 1 FROM json_each(tools.environments) WHERE value = ?)")
            args.append(environment)
        if read_only is not None:
            where.append("read_only = ?")
            args.append(int(read_only))
        if max_risk is not None:
            allowed = [r for r, lvl in RISK_ORDER.items() if lvl <= RISK_ORDER[max_risk]]
            where.append(f"risk IN ({', '.join('?' for _ in allowed)})")
            args += allowed
        if lifecycles is not None:
            ls = list(lifecycles)
            where.append(f"lifecycle IN ({', '.join('?' for _ in ls)})")
            args += ls
        if owner is not None:
            where.append("owner = ?")
            args.append(owner)
        if capability is not None:
            where.append("capability = ?")
            args.append(capability)
        sql = "SELECT * FROM tools" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY tool_id"
        return [self._record(r) for r in self._db.execute(sql, args)]

    def domains(self) -> list[str]:
        return [r[0] for r in self._db.execute("SELECT DISTINCT domain FROM tools ORDER BY domain")]

    # -- drift ------------------------------------------------------------------------------
    def sync(self, published: Mapping[str, Mapping[str, Any]]) -> DriftReport:
        """Compare what MCP servers publish ({tool_id: {"annotations": {...}}}) with the registry."""
        unregistered = sorted(t for t in published if t not in self)
        mismatches = []
        for tool_id, info in sorted(published.items()):
            rec = self.get(tool_id)
            if rec is None:
                continue
            ann = info.get("annotations") or {}
            hint_ro = ann.get("readOnlyHint", ann.get("read_only_hint"))
            hint_destructive = ann.get("destructiveHint", ann.get("destructive_hint"))
            if hint_ro is True and not rec.read_only:
                mismatches.append({"tool_id": tool_id, "hint": "readOnlyHint=true", "registry": rec.risk})
            if hint_destructive is False and rec.destructive:
                mismatches.append({"tool_id": tool_id, "hint": "destructiveHint=false", "registry": "destructive"})
        registered_servers = {t.split(".", 1)[0] for t in published}
        not_published = sorted(
            r.tool_id for r in self.find(lifecycles=None) if r.server in registered_servers and r.tool_id not in published
        )
        return DriftReport(unregistered=unregistered, not_published=not_published, annotation_mismatches=mismatches)
