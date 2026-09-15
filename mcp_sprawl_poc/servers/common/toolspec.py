"""Tool specifications shared by the MCP servers, the catalog generator and the registry.

A ToolSpec has two halves that are owned by different parties in a real enterprise:

* the MCP half (name, description, input schema, annotations) is what a server publishes over
  `tools/list`; any team can change it by shipping a new server version;
* the registry half (`registry`) is enterprise metadata the control plane owns: owner, risk,
  environments, lifecycle, authority. It is never sent over MCP.

Keeping both in one record here is a convenience for the POC's catalog generator. At runtime the
servers only see the MCP half (manifest) and the control plane only trusts the registry half.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import mcp_types as types


@dataclass(frozen=True)
class ToolSpec:
    server: str  # server key, e.g. "observability"
    name: str  # tool name as published by the MCP server
    description: str
    input_schema: dict[str, Any]
    title: str | None = None
    read_only_hint: bool | None = None
    destructive_hint: bool | None = None
    idempotent_hint: bool | None = None
    open_world_hint: bool | None = None
    handler: str = ""  # "<backend>:<function>" resolved by servers.common.handlers
    family: str = "core"
    collision_group: str | None = None
    registry: dict[str, Any] | None = field(default=None, compare=False)

    @property
    def tool_id(self) -> str:
        return f"{self.server}.{self.name}"

    @property
    def exposed_name(self) -> str:
        return f"{self.server}__{self.name}"

    def to_mcp(self) -> types.Tool:
        annotations = None
        if any(v is not None for v in (self.read_only_hint, self.destructive_hint, self.idempotent_hint, self.open_world_hint)):
            annotations = types.ToolAnnotations(
                read_only_hint=self.read_only_hint,
                destructive_hint=self.destructive_hint,
                idempotent_hint=self.idempotent_hint,
                open_world_hint=self.open_world_hint,
            )
        return types.Tool(
            name=self.name,
            title=self.title,
            description=self.description,
            input_schema=self.input_schema,
            annotations=annotations,
        )

    def manifest_entry(self) -> dict[str, Any]:
        """The server-facing half: everything except registry metadata."""
        d = asdict(self)
        d.pop("registry")
        return d

    @classmethod
    def from_manifest(cls, d: dict[str, Any]) -> ToolSpec:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__ and k != "registry"})


def schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    """Small helper for JSON Schema objects with no additional properties."""
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


ENVIRONMENT = {
    "type": "string",
    "enum": ["production", "staging", "development"],
    "description": "Deployment environment.",
}
SERVICE = {"type": "string", "description": "Service name as registered in the service catalogue, e.g. checkout-api."}
TIME_RANGE = {
    "type": "string",
    "description": "Relative lookback window ending now, e.g. 15m, 1h, 6h.",
    "pattern": "^[0-9]+[mh]$",
}
