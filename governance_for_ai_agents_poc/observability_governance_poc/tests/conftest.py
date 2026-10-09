import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

POC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))


@pytest.fixture
def deploy_api(tmp_path):
    """A real deployment API process on a random port, in a scratch scenario directory."""
    from lineage.deploysvc import init_db

    def start(faults=None, hold=1.2):
        for sub in ("deploy", "logs", "telemetry"):
            (tmp_path / sub).mkdir(exist_ok=True)
        (tmp_path / "deploy" / "faults.json").write_text(json.dumps({"drop_hold_s": hold, "faults": faults or []}))
        init_db(tmp_path)
        p = subprocess.Popen([sys.executable, "-m", "lineage.deploysvc", str(tmp_path)], cwd=POC)
        t = time.time()
        while not (tmp_path / "deploy" / "port").exists():
            assert time.time() - t < 15
            time.sleep(0.05)
        started.append(p)
        return tmp_path, int((tmp_path / "deploy" / "port").read_text())

    started: list = []
    yield start
    (tmp_path / "deploy" / "stop").touch()
    for p in started:
        p.wait(timeout=15)


def published_run():
    f = POC / "runs" / "PUBLISHED"
    return POC / "runs" / f.read_text().strip() if f.exists() else None
