"""Platform-owned governance registry.

This is deliberately separate from what MCP servers publish (name, description,
inputSchema, annotations).  Server metadata is *input* to discovery; the registry is
the organisation's record of which implementation is authoritative, its lifecycle,
environment, region, side-effect class, risk, scopes and approval rule.

Trust model (POC): the registry is a file in version control, reviewed like code, and
its SHA-256 is pinned in the frozen run manifest; the gateway refuses to start if the
loaded registry does not match the pinned hash.  Servers cannot mutate it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..util import sha256_file


@dataclass(frozen=True)
class ApprovalRule:
    when: str  # "never" | "always" | "amount_gt"
    field: str | None = None
    threshold: float | None = None

    def requires(self, arguments: dict[str, Any]) -> tuple[bool, str]:
        if self.when == "always":
            return True, "capability always requires approval"
        if self.when == "amount_gt" and self.field:
            value = arguments.get(self.field)
            if isinstance(value, (int, float)) and self.threshold is not None and value > self.threshold:
                return True, f"{self.field}={value} exceeds approval threshold {self.threshold}"
        return False, "below approval threshold"


@dataclass(frozen=True)
class ImplementationRecord:
    implementation: str  # server.tool
    capability: str
    owner: str
    lifecycle: str  # active | retired
    replaced_by: str | None
    environment: str  # prod | staging
    region: str  # us | eu | global
    side_effect: str  # none | write | financial_write
    risk: str  # low | medium | high
    required_scopes: tuple[str, ...]
    approval: ApprovalRule
    binding_profile: str | None = None


@dataclass(frozen=True)
class CapabilityRecord:
    capability: str
    description: str
    owner: str
    authoritative: dict[str, str]  # region -> implementation ("global" key for region-independent)
    entity: str | None = None  # entity type the capability acts on, e.g. "order"
    user_owned: tuple[str, ...] = ()  # argument fields only the requester can supply (never invented or bound)


@dataclass
class Registry:
    version: str
    capabilities: dict[str, CapabilityRecord]
    implementations: dict[str, ImplementationRecord]
    roles: dict[str, frozenset[str]]
    agents: dict[str, frozenset[str]]
    source_path: Path | None = None
    source_sha256: str | None = None
    notes: dict[str, Any] = field(default_factory=dict)

    def get(self, implementation: str) -> ImplementationRecord | None:
        return self.implementations.get(implementation)

    def authoritative_for(self, capability: str, region: str | None) -> str | None:
        cap = self.capabilities.get(capability)
        if cap is None:
            return None
        if region and region in cap.authoritative:
            return cap.authoritative[region]
        return cap.authoritative.get("global")

    def is_authoritative(self, implementation: str, region: str | None) -> bool:
        rec = self.get(implementation)
        if rec is None:
            return False
        cap = self.capabilities.get(rec.capability)
        if cap is None:
            return False
        if region and region in cap.authoritative:
            return cap.authoritative[region] == implementation
        return implementation in cap.authoritative.values()


def load_registry(path: Path) -> Registry:
    path = Path(path)
    doc = yaml.safe_load(path.read_text())
    caps = {
        c: CapabilityRecord(
            capability=c,
            description=v["description"],
            owner=v["owner"],
            authoritative=dict(v["authoritative"]),
            entity=v.get("entity"),
            user_owned=tuple(v.get("user_owned", ())),
        )
        for c, v in doc["capabilities"].items()
    }
    impls = {}
    for name, v in doc["implementations"].items():
        a = v.get("approval") or {"when": "never"}
        impls[name] = ImplementationRecord(
            implementation=name,
            capability=v["capability"],
            owner=v["owner"],
            lifecycle=v["lifecycle"],
            replaced_by=v.get("replaced_by"),
            environment=v["environment"],
            region=v.get("region", "global"),
            side_effect=v["side_effect"],
            risk=v["risk"],
            required_scopes=tuple(v.get("required_scopes", [])),
            approval=ApprovalRule(a["when"], a.get("field"), a.get("threshold")),
            binding_profile=v.get("binding_profile"),
        )
    return Registry(
        version=str(doc["version"]),
        capabilities=caps,
        implementations=impls,
        roles={k: frozenset(v) for k, v in doc.get("roles", {}).items()},
        agents={k: frozenset(v) for k, v in doc.get("agents", {}).items()},
        source_path=path,
        source_sha256=sha256_file(path),
        notes=doc.get("notes", {}),
    )
