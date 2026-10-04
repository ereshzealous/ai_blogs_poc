from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
# One trace directory for the whole session (the tracer provider is configured once per process).
os.environ.setdefault("LAP_RUNS_DIR", tempfile.mkdtemp(prefix="lap-runs-"))
os.environ.setdefault("LAP_KNOWLEDGE_INDEX", str(ROOT / "var" / "knowledge_index.json"))

REQUIRED_MODELS = {"gpt-oss:20b", "qwen3:8b", "nomic-embed-text:latest"}


def _ollama_models() -> set[str]:
    try:
        return {m["name"] for m in httpx.get("http://localhost:11434/api/tags", timeout=3).json()["models"]}
    except Exception:
        return set()


def pytest_collection_modifyitems(config, items):
    have = _ollama_models()
    missing = REQUIRED_MODELS - have
    if missing:
        skip = pytest.mark.skip(reason=f"Ollama models missing: {sorted(missing)}")
        for item in items:
            if "ollama" in item.keywords:
                item.add_marker(skip)


@pytest.fixture
def platform_env(tmp_path, monkeypatch):
    """Fresh platform and enterprise databases for one test."""
    monkeypatch.setenv("LAP_PLATFORM_DB", str(tmp_path / "platform.db"))
    monkeypatch.setenv("LAP_ENTERPRISE_DB", str(tmp_path / "enterprise.db"))
    from mock_enterprise.world import World

    world = World(tmp_path / "enterprise.db")
    world.reset()
    return {"tmp": tmp_path, "world": world, "env": dict(os.environ)}


def lap(*args: str, env: dict[str, str], timeout: int = 2700) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "agent_platform.channels.cli", *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=timeout)
