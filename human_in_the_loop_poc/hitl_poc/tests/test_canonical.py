"""The 30 canonical HITL tests, run through pytest (the same functions `hitl suite` and `hitl proof` run)."""
from pathlib import Path

import pytest

from hitl.suite import TESTS, run_suite


@pytest.mark.canonical
@pytest.mark.parametrize("tid", [t[0] for t in TESTS])
def test_canonical(tid: str, tmp_path: Path):
    (o,) = run_suite(tmp_path, only=[tid])
    failed = {k: v for k, v in o.assertions.items() if not v["held"]}
    assert o.error is None, o.error
    assert not failed, failed
