import pytest

from aid.platform import Platform


@pytest.fixture
def chain():
    return Platform("chain")


@pytest.fixture
def shared():
    return Platform("shared_sa")
