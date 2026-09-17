from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
# The platform's tracer is configured once per process, so one trace directory serves the whole session.
os.environ.setdefault("LAP_RUNS_DIR", tempfile.mkdtemp(prefix="hai-traces-"))
for var in ("LAP_MODEL_TRAFFIC", "LAP_PLATFORM_DB", "LAP_ENTERPRISE_DB", "HAI_HEADLESS_DB"):
    os.environ.pop(var, None)

REQUIRED_MODELS = {"gpt-oss:20b", "qwen3:8b", "nomic-embed-text:latest"}
sys.path.insert(0, str(ROOT))


def _ollama_models() -> set[str]:
    try:
        return {m["name"] for m in httpx.get("http://localhost:11434/api/tags", timeout=3).json()["models"]}
    except Exception:
        return set()


def pytest_collection_modifyitems(config, items):
    missing = REQUIRED_MODELS - _ollama_models()
    if missing:
        skip = pytest.mark.skip(reason=f"Ollama models missing: {sorted(missing)}")
        for item in items:
            if "ollama" in item.keywords:
                item.add_marker(skip)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture
def platform_env(tmp_path, monkeypatch):
    """Fresh platform, enterprise and headless databases, and replayed model answers for up to 8 workflows.

    Replayed answers are consumed in order per agent, so tests using this fixture run workflows one after another.
    """
    from experiments.harness import prepare_env

    env = prepare_env(tmp_path, replay_workflows=8)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return {"tmp": tmp_path, "env": env}
