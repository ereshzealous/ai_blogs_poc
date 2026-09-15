"""Resolves the environment an invocation will touch, before it runs.

Order: an explicit `environment` argument; the registry's environments when the tool can only touch
one; the resource inventory (pods, instances, tasks, databases); otherwise **production**. Treating an
unknown target as production is the fail-safe default: it can only make a decision stricter.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from control_plane.paths import SCENARIO_FILE
from control_plane.registry.registry import RegistryRecord

KNOWN = ("production", "staging", "development")


@dataclass(frozen=True)
class ResolvedEnvironment:
    environment: str
    source: str  # argument | registry | inventory | default


class ResourceInventory:
    """Maps resource identifiers to environments, standing in for a CMDB lookup."""

    def __init__(self, mapping: dict[str, str]):
        self._mapping = mapping

    @classmethod
    def from_scenario(cls, path: str | Path = SCENARIO_FILE) -> ResourceInventory:
        with open(path, encoding="utf-8") as fh:
            sc = yaml.safe_load(fh)
        mapping: dict[str, str] = {}
        for r in sc["cloud"]["resources"]:
            mapping[r["id"]] = r["environment"]
        for envs in sc["kubernetes"].values():
            for env, wl in envs.items():
                for pod in wl["pods"]:
                    mapping[pod["name"]] = env
                mapping[wl["cluster"]] = env
        return cls(mapping)

    def lookup(self, value: Any) -> str | None:
        return self._mapping.get(value) if isinstance(value, str) else None


def resolve_environment(arguments: dict[str, Any], record: RegistryRecord | None, inventory: ResourceInventory) -> ResolvedEnvironment:
    env = arguments.get("environment")
    if isinstance(env, str) and env in KNOWN:
        return ResolvedEnvironment(env, "argument")
    if record is not None and len(record.environments) == 1:
        return ResolvedEnvironment(record.environments[0], "registry")
    for value in arguments.values():
        found = inventory.lookup(value)
        if found:
            return ResolvedEnvironment(found, "inventory")
    return ResolvedEnvironment("production", "default")
