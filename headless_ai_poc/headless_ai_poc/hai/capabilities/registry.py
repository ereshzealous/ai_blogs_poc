"""Capability registry: versioned business capabilities with owners, risk, scopes and contracts.

Discovery is scoped: an execution is shown only the capabilities its identity could ever be allowed to call, so the
reasoner never sees (and cannot be talked into) a capability outside its delegation.
"""

from __future__ import annotations

import re
from typing import Any

from hai.config import load


class SchemaError(ValueError):
    pass


class Registry:
    def __init__(self) -> None:
        cfg = load("capabilities.yaml")
        self.systems: list[str] = cfg["systems"]
        self.caps: dict[str, dict[str, Any]] = cfg["capabilities"]

    def get(self, name: str) -> dict[str, Any] | None:
        return self.caps.get(name)

    def discover(self, scopes: list[str]) -> list[dict[str, Any]]:
        """What this execution may see: capabilities whose scope it holds, plus approval-gated ones it may propose."""
        out = []
        for name, c in self.caps.items():
            if c.get("risk") == "destructive":
                continue
            gated = c.get("kind") == "write" and c.get("risk") == "high"
            if c["scope"] in scopes or gated:
                out.append({"name": name, "version": c["version"], "kind": c["kind"], "risk": c.get("risk", "none"),
                            "owner": c["owner"], "approval_gated": gated})
        return out

    @staticmethod
    def validate(cap: dict[str, Any], args: dict[str, Any]) -> None:
        """A small JSON-Schema subset: required, type, enum, pattern, min/max.  Unknown arguments are rejected."""
        schema = cap["schema"]
        props = schema.get("properties", {})
        for r in schema.get("required", []):
            if r not in args:
                raise SchemaError(f"missing argument {r}")
        for k, v in args.items():
            p = props.get(k)
            if p is None:
                raise SchemaError(f"unknown argument {k}")
            t = p.get("type")
            if t == "string" and not isinstance(v, str) or t == "integer" and (not isinstance(v, int) or isinstance(v, bool)):
                raise SchemaError(f"{k} must be {t}")
            if "enum" in p and v not in p["enum"]:
                raise SchemaError(f"{k} must be one of {p['enum']}")
            if "pattern" in p and not re.fullmatch(p["pattern"], v):
                raise SchemaError(f"{k} does not match {p['pattern']}")
            if "minimum" in p and v < p["minimum"] or "maximum" in p and v > p["maximum"]:
                raise SchemaError(f"{k} out of range")
