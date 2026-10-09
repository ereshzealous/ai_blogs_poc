"""I1–I7 and the global assertions G01–G11: every declared check holds in a fresh run (the same functions `aid experiments`
runs; nothing is written)."""
import pytest

from aid import experiments as X

EXPS = ["I1", "I2", "I3", "I4", "I5", "I6", "I7", "GA"]


@pytest.fixture(scope="module")
def checks():
    X.SCENARIOS.clear()
    res = {"I1": X.i1(), "I2": X.i2(), "I3": X.i3(), "I4": X.i4(), "I5": X.i5(), "I6": X.i6(), "I7": X.i7()}
    return X.checks_for(res)


@pytest.mark.parametrize("exp", EXPS)
def test_experiment(exp, checks):
    failed = [f"{c['id']} {c['check']}" for c in checks if c["experiment"] == exp and not c["passed"]]
    assert not failed, failed
