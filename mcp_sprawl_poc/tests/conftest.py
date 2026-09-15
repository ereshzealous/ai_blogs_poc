from __future__ import annotations

from pathlib import Path

import pytest

from control_plane.policy.engine import Identity, PolicyEngine
from control_plane.policy.environment import ResourceInventory
from control_plane.registry.registry import CapabilityRegistry
from servers.common.world import World


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def registry() -> CapabilityRegistry:
    return CapabilityRegistry.load()


@pytest.fixture(scope="session")
def policy() -> PolicyEngine:
    return PolicyEngine.load()


@pytest.fixture(scope="session")
def inventory() -> ResourceInventory:
    return ResourceInventory.from_scenario()


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path / "world.sqlite")


@pytest.fixture(scope="session")
def oncall() -> Identity:
    return Identity("oncall-1", ("sre-oncall",))


@pytest.fixture(scope="session")
def developer() -> Identity:
    return Identity("dev-7", ("developer",))
