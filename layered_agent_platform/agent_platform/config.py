"""Platform configuration: `config/platform.yaml` plus environment overrides. Paths resolve from the repo root."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


def load_yaml(name: str) -> dict[str, Any]:
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@dataclass
class Settings:
    raw: dict[str, Any]
    platform_db: Path
    enterprise_db: Path
    runs_dir: Path
    knowledge_dir: Path
    knowledge_index: Path
    ollama_url: str
    model_routes: dict[str, dict[str, Any]]
    model_profiles: dict[str, dict[str, Any]]
    extra: dict[str, Any] = field(default_factory=dict)

    def section(self, name: str) -> dict[str, Any]:
        return self.raw.get(name, {})


def _path(value: str, env: str) -> Path:
    """A default from platform.yaml is relative to this package. An environment override is relative to the working
    directory, like any other tool: a relative LAP_RUNS_DIR from another project must not write inside this one."""
    override = os.environ.get(env)
    if override:
        return Path(override).expanduser().absolute()
    p = Path(value)
    return p if p.is_absolute() else ROOT / p


def load_settings() -> Settings:
    raw = load_yaml("platform.yaml")
    paths, models = raw["paths"], raw["models"]
    routes = {k: dict(v) for k, v in models["routes"].items()}
    for route in routes:
        override = os.environ.get(f"LAP_MODEL_{route.upper()}")
        if override:
            routes[route]["model"] = override
    return Settings(
        raw=raw,
        platform_db=_path(paths["platform_db"], "LAP_PLATFORM_DB"),
        enterprise_db=_path(paths["enterprise_db"], "LAP_ENTERPRISE_DB"),
        runs_dir=_path(paths["runs_dir"], "LAP_RUNS_DIR"),
        knowledge_dir=ROOT / paths["knowledge_dir"],
        knowledge_index=_path(paths["knowledge_index"], "LAP_KNOWLEDGE_INDEX"),
        ollama_url=os.environ.get("OLLAMA_URL", models["url"]),
        model_routes=routes,
        model_profiles=models.get("profiles", {}),
    )


@lru_cache(maxsize=1)
def capabilities() -> dict[str, Any]:
    return load_yaml("capabilities.yaml")


@lru_cache(maxsize=1)
def policies() -> dict[str, Any]:
    return load_yaml("policies.yaml")


@lru_cache(maxsize=1)
def principals() -> dict[str, Any]:
    return load_yaml("principals.yaml")
