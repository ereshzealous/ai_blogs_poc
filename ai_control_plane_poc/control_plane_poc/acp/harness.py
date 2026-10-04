"""Drive long-lived worker processes from the experiment (the control plane runs in this, separate, process)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from acp.common import POC


class Worker:
    """One runtime process. It is started once; the proofs then change the control plane around it."""

    def __init__(self, state: Path, instance: str, module: str = "acp.runtime.worker", extra: list[str] | None = None):
        args = [sys.executable, "-m", module, str(state), *(extra if extra is not None else [instance])]
        self.p = subprocess.Popen(args, cwd=POC, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        hello = self._read()
        self.pid, self.loaded_code_sha256 = hello["pid"], hello.get("loaded_code_sha256")
        self.pids = {self.pid}
        self.last_pid = self.pid  # the process that answered the latest request (recorded, normalized, per scenario)

    def _read(self) -> dict:
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError(f"worker exited: {self.p.wait()}")
        return json.loads(line)

    def send(self, req: dict) -> dict:
        self.p.stdin.write(json.dumps(req) + "\n")
        self.p.stdin.flush()
        msg = self._read()
        if "pid" in msg:
            self.pids.add(msg["pid"])
            self.last_pid = msg["pid"]
        return msg

    def request(self, req: dict) -> dict:
        return self.send(req)["response"]

    def run_with_checkpoint(self, req: dict, at_checkpoint) -> dict:
        """Start a run that pauses after N tool calls; call at_checkpoint() (e.g. publish a change); then let it finish."""
        first = self.send(req)
        assert "checkpoint" in first, first
        at_checkpoint(first["checkpoint"])
        return self.send({"op": "continue"})["response"]

    @property
    def same_process(self) -> bool:
        return len(self.pids) == 1 and self.p.poll() is None

    def close(self) -> None:
        if self.p.poll() is None:
            self.p.stdin.write(json.dumps({"op": "exit"}) + "\n")
            self.p.stdin.flush()
            self.p.wait(timeout=10)
