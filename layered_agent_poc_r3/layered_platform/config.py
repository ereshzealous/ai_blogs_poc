"""Loads the YAML files in config/, expanding ${VAR:-default} from the environment."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path(os.environ.get("F2_CONFIG_DIR", ROOT / "config"))
_VAR = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def load(name: str) -> dict[str, Any]:
    text = (CONFIG / name).read_text()
    return yaml.safe_load(_VAR.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), text))
