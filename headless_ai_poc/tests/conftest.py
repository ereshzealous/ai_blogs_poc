import pytest

from hai.experiments import Lab


@pytest.fixture
def lab(tmp_path):
    return Lab(tmp_path, "t")
