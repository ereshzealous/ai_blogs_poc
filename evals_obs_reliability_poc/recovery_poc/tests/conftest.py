import pytest

from recovery.common import scenarios


@pytest.fixture(scope="session")
def sc():
    return {s["id"]: s for s in scenarios()}
