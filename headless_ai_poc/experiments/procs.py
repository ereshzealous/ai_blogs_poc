"""Start and stop real processes for the multi-process experiments."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Proc:
    def __init__(self, name: str, args: list[str], env: dict[str, str], port: int, log_dir: Path):
        self.name, self.port = name, port
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log = (log_dir / f"{name}.log").open("a")
        self.p = subprocess.Popen([sys.executable, *args], cwd=ROOT, env={**os.environ, **env},
                                  stdout=self.log, stderr=subprocess.STDOUT)
        self.url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.p.poll() is not None:
                raise RuntimeError(f"{name} exited early; see {self.log.name}")
            try:
                if httpx.get(f"{self.url}/healthz", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.2)
        raise TimeoutError(f"{name} did not become healthy")

    @property
    def pid(self) -> int:
        return self.p.pid

    def kill(self) -> None:
        """SIGKILL: no shutdown hooks, no goodbye. The adapter simply disappears."""
        self.p.send_signal(signal.SIGKILL)
        self.p.wait(10)

    def stop(self) -> None:
        if self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(15)
            except subprocess.TimeoutExpired:
                self.kill()
        self.log.close()


def server(name: str, channels: str, env: dict[str, str], log_dir: Path, extra: dict[str, str] | None = None) -> Proc:
    port = free_port()
    args = ["-m", "uvicorn", "--factory", "headless_ai_platform.server:create_app", "--host", "127.0.0.1",
            "--port", str(port), "--log-level", "warning"]
    return Proc(name, args, {**env, "HAI_CHANNELS": channels, **(extra or {})}, port, log_dir)


def sink(env: dict[str, str], log_dir: Path) -> Proc:
    port = free_port()
    return Proc("slack-api", ["-m", "experiments.sink", "--port", str(port), "--log", str(log_dir / "slack-messages.jsonl")],
                env, port, log_dir)


def cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "headless_ai_platform.channels.cli", *args], cwd=ROOT,
                          env={**os.environ, **env}, capture_output=True, text=True, timeout=900)
