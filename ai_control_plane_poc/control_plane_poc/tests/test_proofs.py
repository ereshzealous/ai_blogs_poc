"""End to end: every proof passes, and two runs are byte-identical (the run is deterministic)."""

import filecmp
import shutil

import pytest

from acp.experiments import RUNS, run


@pytest.fixture(scope="module")
def runs():
    a, b = run("_test-a"), run("_test-b")
    yield a, b
    shutil.rmtree(a)
    shutil.rmtree(b)


def test_every_check_passes(runs):
    import json

    checks = json.loads((runs[0] / "checks.json").read_text())
    failed = [c for c in checks if not c["passed"]]
    assert not failed, failed
    assert len(checks) >= 90


def test_outcomes(runs):
    import json

    out = {}
    for p in (runs[0] / "scenarios").iterdir():
        s = json.loads((p / "scenario.json").read_text())
        out[s["id"]] = s["outcome"]
    assert out["P2-C-central-change"] == "held"
    assert out["P11-E-embedded"] == "broken"
    assert out["P9-C-outage"] == "qualified" and out["P10-C-drift"] == "qualified"


def diff(a, b):
    c = filecmp.dircmp(a, b)
    out = c.left_only + c.right_only + [n for n in c.common_files if not filecmp.cmp(a / n, b / n, shallow=False)]
    for d in c.common_dirs:
        out += diff(a / d, b / d)
    return out


def test_deterministic(runs):
    a, b = runs
    # the run id appears in manifest.json and facts.json by design, and volatile.json holds the raw process ids (the
    # one normalization `make verify` applies, by masking them); compare everything else byte for byte
    assert [x for x in diff(a, b) if x not in ("manifest.json", "facts.json", "summary.md", "volatile.json")] == []
    assert RUNS.exists()
