"""The declared capability catalog (discovery v5): which job each tool does, and which tool does it for the organisation.

Built by `benchmark/catalog_generator/capabilities.py`. Discovery shows one implementation per capability, chosen by
declared role, never by text similarity:

    authoritative  >  environment variant for the routed environment  >  active substitute

Legacy implementations are never chosen.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from control_plane.paths import CATALOG_DIR

CAPABILITIES_PATH = CATALOG_DIR / "capabilities.json"


@dataclass(frozen=True)
class Implementation:
    tool_id: str
    role: str  # authoritative | environment_variant | substitute | legacy
    environments: tuple[str, ...]
    lifecycle: str


@dataclass(frozen=True)
class Capability:
    id: str
    system: str
    resource: str
    action: str
    domain: str
    core: bool
    authoritative: str | None
    risk: str
    side_effect: bool
    use_when: str
    not_for: str
    summary: str
    entity_types: tuple[str, ...]
    not_equivalent: tuple[str, ...]
    implementations: tuple[Implementation, ...]

    def value(self, dimension: str) -> str:
        return {"system": self.system, "resource": self.resource, "action": self.action}[dimension]


class CapabilityCatalog:
    def __init__(self, data: dict[str, Any]):
        self.capabilities: dict[str, Capability] = {}
        for cid, c in data["capabilities"].items():
            impls = tuple(Implementation(i["tool_id"], i["role"], tuple(i["environments"]), i["lifecycle"]) for i in c["implementations"])
            fields = {k: v for k, v in c.items() if k not in ("implementations", "entity_types", "not_equivalent")}
            self.capabilities[cid] = Capability(**fields, entity_types=tuple(c["entity_types"]),
                                                not_equivalent=tuple(c["not_equivalent"]), implementations=impls)
        self.tools: dict[str, dict[str, str]] = data["tools"]
        self._impl = {i.tool_id: i for c in self.capabilities.values() for i in c.implementations}

    @classmethod
    def load(cls, path: str | Path = CAPABILITIES_PATH) -> CapabilityCatalog:
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def capability_of(self, tool_id: str | None) -> str | None:
        entry = self.tools.get(tool_id or "")
        return entry["capability"] if entry else None

    def role_of(self, tool_id: str) -> str | None:
        entry = self.tools.get(tool_id)
        return entry["role"] if entry else None

    def implementation(self, tool_id: str) -> Implementation | None:
        return self._impl.get(tool_id)

    def get(self, tool_id: str | None) -> Capability | None:
        cid = self.capability_of(tool_id)
        return self.capabilities.get(cid) if cid else None

    def canonical(self, capability_id: str, allowed: Collection[str], environment: str | None) -> str | None:
        """The implementation discovery shows for a capability, among the `allowed` tools."""
        impls = [i for i in self.capabilities[capability_id].implementations if i.tool_id in allowed]
        for role in ("authoritative", "environment_variant", "substitute"):
            for i in impls:
                if i.role != role:
                    continue
                if role == "environment_variant" and environment is not None and environment not in i.environments:
                    continue
                return i.tool_id
        return None

    def guidance(self, tool_id: str) -> str:
        cap = self.get(tool_id)
        if cap is None or not (cap.use_when or cap.not_for):
            return ""
        return f"Use for: {cap.use_when}. Not for: {cap.not_for}."
