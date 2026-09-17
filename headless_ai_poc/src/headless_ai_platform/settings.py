"""Paths and configuration for the headless boundary. Environment variables override (HAI_*)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(os.environ.get("HAI_CONFIG_DIR", ROOT / "config"))


def load_yaml(name: str) -> dict[str, Any]:
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _path(value: str, env: str) -> Path:
    p = Path(os.environ.get(env, value))
    return p if p.is_absolute() else ROOT / p


@dataclass(frozen=True)
class Settings:
    headless_db: Path
    platform_db: Path
    enterprise_db: Path
    runs_dir: Path
    knowledge_index: Path
    raw: dict[str, Any]

    def capability(self, name: str) -> dict[str, Any] | None:
        return self.raw.get("capabilities", {}).get(name)

    def platform_env(self) -> dict[str, str]:
        """Environment for the layered platform. Values already set by the caller win."""
        return {"LAP_PLATFORM_DB": str(self.platform_db), "LAP_ENTERPRISE_DB": str(self.enterprise_db),
                "LAP_RUNS_DIR": str(self.runs_dir), "LAP_KNOWLEDGE_INDEX": str(self.knowledge_index)}


def load_settings() -> Settings:
    raw = load_yaml("headless.yaml")
    p = raw["paths"]
    return Settings(headless_db=_path(p["headless_db"], "HAI_HEADLESS_DB"),
                    platform_db=_path(os.environ.get("LAP_PLATFORM_DB", p["platform_db"]), "HAI_PLATFORM_DB"),
                    enterprise_db=_path(os.environ.get("LAP_ENTERPRISE_DB", p["enterprise_db"]), "HAI_ENTERPRISE_DB"),
                    runs_dir=_path(os.environ.get("LAP_RUNS_DIR", p["runs_dir"]), "HAI_RUNS_DIR"),
                    knowledge_index=_path(os.environ.get("LAP_KNOWLEDGE_INDEX", p["knowledge_index"]), "HAI_KNOWLEDGE_INDEX"),
                    raw=raw)


@lru_cache(maxsize=1)
def channel_identities() -> dict[str, Any]:
    return load_yaml("channel_identities.yaml")
