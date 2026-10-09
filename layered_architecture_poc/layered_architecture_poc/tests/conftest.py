from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("F2_TAPE", None)
os.environ.pop("F2_CRASH_AT", None)


@pytest.fixture
def world(tmp_path, monkeypatch):
    from simulated_enterprise.world import World

    w = World(tmp_path / "world.db")
    w.reset()
    monkeypatch.setenv("F2_WORLD_DB", str(w.path))
    return w


def ollama_models() -> set[str]:
    try:
        return {m["name"] for m in httpx.get("http://localhost:11434/api/tags", timeout=2).json()["models"]}
    except Exception:
        return set()


def need_model(name: str):
    return pytest.mark.skipif(name not in ollama_models(), reason=f"Ollama model {name} not available")
