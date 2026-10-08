"""Shared fixtures.  Nothing here needs a model: the scripted provider stands in for it."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from coord.runtime import envelope_for, invoke, open_session
from coord.scripted import ScriptedProvider
from coord.world import load_fixture


def pytest_collection_modifyitems(items):
    """Run every async test (and its async fixtures) on anyio's runner: one task per test, as MCP's cancel scopes need."""
    for item in items:
        if inspect.iscoroutinefunction(getattr(item, "function", None)):
            item.add_marker(pytest.mark.anyio)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("C1_HOME", str(tmp_path))
    monkeypatch.setenv("C1_WORLD_DB", str(tmp_path / "world.db"))
    monkeypatch.delenv("C1_TAPE", raising=False)
    return tmp_path


@pytest.fixture
async def session(home: Path):
    s = await open_session(home, provider=ScriptedProvider(), service="c1-test")
    yield s
    await s.close()


async def run_one(session, fixture: str, arch: str, wf: str, overrides=None):
    session.world.reset(fixture)
    return await invoke(session, envelope_for(load_fixture(fixture), wf), arch=arch, workflow_id=wf, run_id="test", fixture_id=fixture,
                        repeat=1, seed=7, overrides=overrides)
