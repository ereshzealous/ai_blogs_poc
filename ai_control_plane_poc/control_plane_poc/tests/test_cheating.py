"""P2 must fail when the thing it holds fixed is not fixed.

P2 claims that behaviour changed with agent code, runtime process and request all unchanged.  Each test breaks exactly
one of the three between the two requests and asserts that P2 notices: the matching check fails and the scenario is
not HELD.  The runs happen in a scratch copy of the POC, because the "code" case edits an agent source file.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

from acp.common import POC

RUN_P2 = """
import json, sys
from pathlib import Path
from acp.experiments import p2
rec = p2(Path(sys.argv[1]), cheat=sys.argv[2] if sys.argv[2] != "none" else None)[0]
print(json.dumps({"outcome": rec["outcome"], "failed": [c["check"] for c in rec["checks"] if not c["passed"]],
                  "measures": dict(rec["measures"])}))
"""


@pytest.fixture(scope="module")
def scratch(tmp_path_factory):
    root = tmp_path_factory.mktemp("poc")
    copy = root / "poc"
    shutil.copytree(POC, copy, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "runs"))
    return copy


def p2_in(copy, cheat):
    out = copy / "runs" / f"cheat-{cheat}"
    out.mkdir(parents=True, exist_ok=True)
    # cwd first on sys.path: the scratch copy's acp package is the one imported, by this process and by its workers
    env = {**os.environ, "ACP_SCRATCH_COPY": str(copy), "PYTHONPATH": str(copy)}
    r = subprocess.run([sys.executable, "-c", RUN_P2, str(out), cheat], cwd=copy, env=env, capture_output=True, text=True, check=True)
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_unchanged_p2_holds(scratch):
    r = p2_in(scratch, "none")
    assert r["outcome"] == "held" and r["failed"] == []
    assert r["measures"]["agent_edits"] == 0 and r["measures"]["redeploys"] == 0


def test_p2_fails_if_the_request_changes(scratch):
    r = p2_in(scratch, "request")
    assert r["outcome"] == "broken"
    assert any(f.startswith("same request") for f in r["failed"])
    assert r["measures"]["request_hash_before"] != r["measures"]["request_hash_after"]


def test_p2_fails_if_the_runtime_process_is_restarted(scratch):
    r = p2_in(scratch, "process")
    assert r["outcome"] == "broken"
    assert any(f.startswith("same runtime process") for f in r["failed"])
    assert r["measures"]["runtime_pid_after"] == "rt-a/pid-2" and r["measures"]["redeploys"] == 1


def test_p2_fails_if_the_agent_code_changes(scratch):
    r = p2_in(scratch, "code")
    assert r["outcome"] == "broken"
    assert any(f.startswith("same agent code") for f in r["failed"])
    assert r["measures"]["agent_sha_before"] != r["measures"]["agent_sha_after"]


def test_the_code_cheat_refuses_to_edit_the_real_poc():
    from acp.experiments import p2

    with pytest.raises(AssertionError):
        p2(POC / "runs" / "never-written", cheat="code")
