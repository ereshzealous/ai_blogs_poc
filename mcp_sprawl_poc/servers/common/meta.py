"""Builds registry records (enterprise metadata) for tool specs.

Risk tiers are the control plane's vocabulary, not MCP's:
READ_ONLY < LOW_RISK_WRITE < HIGH_RISK_WRITE. `destructive` marks irreversible actions.
"""

from __future__ import annotations

from typing import Any

ALL_ENVS = ("production", "staging", "development")
RISKS = ("READ_ONLY", "LOW_RISK_WRITE", "HIGH_RISK_WRITE")


def registry_record(
    *,
    domain: str,
    capability: str,
    resource_type: str,
    operations: list[str],
    risk: str,
    owner: str,
    scopes: list[str],
    environments: tuple[str, ...] | list[str] = ALL_ENVS,
    authoritative_for: list[str] | None = None,
    destructive: bool = False,
    deprecated: bool = False,
    replaced_by: str | None = None,
    lifecycle: str | None = None,
    version: str = "1.0",
    notes: str | None = None,
) -> dict[str, Any]:
    if risk not in RISKS:
        raise ValueError(f"unknown risk tier {risk}")
    read_only = risk == "READ_ONLY"
    return {
        "domain": domain,
        "capability": capability,
        "resource_type": resource_type,
        "operations": operations,
        "environments": list(environments),
        "read_only": read_only,
        "side_effect": not read_only,
        "risk": risk,
        "destructive": destructive,
        "requires_approval": risk == "HIGH_RISK_WRITE",
        "owner": owner,
        "version": version,
        "deprecated": deprecated,
        "replaced_by": replaced_by,
        "lifecycle": lifecycle or ("deprecated" if deprecated else "active"),
        "authoritative_for": authoritative_for or [],
        "required_scopes": scopes,
        "notes": notes,
    }
