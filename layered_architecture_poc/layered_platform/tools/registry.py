"""Capability registry: capability id -> (MCP server, tool, kind, risk, adapter, idempotency parameter)."""

from __future__ import annotations

from typing import Any

from layered_platform.config import load


class Registry:
    def __init__(self, spec: dict[str, Any] | None = None):
        self.spec = spec or load("capabilities.yaml")
        self.caps: dict[str, dict[str, Any]] = self.spec["capabilities"]

    def get(self, capability: str) -> dict[str, Any] | None:
        return self.caps.get(capability)

    def contract(self, capability: str) -> dict[str, Any] | None:
        name = (self.caps.get(capability) or {}).get("contract")
        return self.spec.get("contracts", {}).get(name) if name else None

    def servers(self) -> list[str]:
        return list(self.spec["servers"])

    def reads(self) -> list[str]:
        return [c for c, m in self.caps.items() if m["kind"] == "read"]

    @staticmethod
    def exposed_name(capability: str) -> str:
        return capability.replace(".", "_")
