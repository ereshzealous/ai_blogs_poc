"""Capability registry: risk, tags, authority and retry policy for every MCP tool (config/capabilities.yaml)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_platform.config import capabilities


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 1
    timeout_s: float = 8.0
    backoff_ms: int = 200


@dataclass(frozen=True)
class ToolRecord:
    tool_id: str
    risk: str
    tags: tuple[str, ...]
    retry: RetryPolicy
    idempotency_key: bool = False
    authoritative_for: tuple[str, ...] = field(default_factory=tuple)

    @property
    def server(self) -> str:
        return self.tool_id.split(".", 1)[0]

    @property
    def name(self) -> str:
        return self.tool_id.split(".", 1)[1]

    @property
    def exposed_name(self) -> str:
        return f"{self.server}__{self.name}"

    @property
    def is_write(self) -> bool:
        return self.risk != "READ_ONLY"


class CapabilityRegistry:
    def __init__(self, data: dict[str, Any] | None = None):
        data = data or capabilities()
        self.services: dict[str, dict[str, Any]] = data.get("services", {})
        self.tools: dict[str, ToolRecord] = {}
        for tool_id, spec in data["tools"].items():
            self.tools[tool_id] = ToolRecord(
                tool_id=tool_id, risk=spec["risk"], tags=tuple(spec.get("tags", [])),
                retry=RetryPolicy(**spec.get("retry", {})), idempotency_key=bool(spec.get("idempotency_key")),
                authoritative_for=tuple(spec.get("authoritative_for", [])))

    def get(self, tool_id: str) -> ToolRecord | None:
        return self.tools.get(tool_id)

    def by_exposed_name(self, exposed: str) -> ToolRecord | None:
        return next((r for r in self.tools.values() if r.exposed_name == exposed), None)

    def discover(self, *, tags: set[str], read_only: bool = True) -> list[ToolRecord]:
        """Capability discovery. The POC filters by tag; the previous article's control plane ranks with search."""
        return [r for r in self.tools.values() if tags & set(r.tags) and (not read_only or not r.is_write)]

    def service(self, name: str | None) -> dict[str, Any]:
        return self.services.get(name or "", {})
