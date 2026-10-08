"""Starts, watches, kills and restarts architecture C's agent processes (one OS process per agent).

Readiness = the agent's Agent Card is served.  `kill` is a real SIGKILL (experiment E6); `ensure` restarts an agent
whose process has died, which is what the coordinator's retry path calls after a transport failure.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from coord.util import ROOT, load_config


class Supervisor:
    def __init__(self, home: Path, env: dict[str, str] | None = None):
        cfg = load_config("agents.yaml")
        self.host, self.agents = cfg["host"], cfg["agents"]
        self.home = home
        self.env = dict(os.environ, PYTHONPATH=str(ROOT), C1_HOME=str(home), C1_WORLD_DB=str(home / "world.db"), **(env or {}))
        self.procs: dict[str, subprocess.Popen[bytes]] = {}
        self.restarts: dict[str, int] = {}
        (home / "logs").mkdir(parents=True, exist_ok=True)

    def url(self, agent: str) -> str:
        return f"http://{self.host}:{self.agents[agent]['port']}"

    def start(self, agent: str) -> None:
        log = open(self.home / "logs" / f"agent-{agent}.log", "ab")  # noqa: SIM115 - owned by the child for its lifetime
        self.procs[agent] = subprocess.Popen([sys.executable, "-m", "coord.a2a_server", agent], env=self.env, cwd=str(ROOT),
                                             stdout=log, stderr=log)

    async def ready(self, agent: str, timeout_s: float = 60) -> float:
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=2) as c:
            while time.perf_counter() - t0 < timeout_s:
                p = self.procs.get(agent)
                if p and p.poll() is not None:
                    raise RuntimeError(f"agent {agent} exited with {p.returncode}; see logs/agent-{agent}.log")
                try:
                    r = await c.get(self.url(agent) + "/.well-known/agent-card.json")
                    if r.status_code == 200:
                        return round(time.perf_counter() - t0, 2)
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.2)
        raise TimeoutError(f"agent {agent} not ready after {timeout_s}s")

    async def start_all(self) -> dict[str, float]:
        for a in self.agents:
            self.start(a)
        return {a: await self.ready(a) for a in self.agents}

    def alive(self, agent: str) -> bool:
        p = self.procs.get(agent)
        return bool(p and p.poll() is None)

    def pid(self, agent: str) -> int | None:
        p = self.procs.get(agent)
        return p.pid if p else None

    def kill(self, agent: str) -> int | None:
        p = self.procs.get(agent)
        if p and p.poll() is None:
            os.kill(p.pid, signal.SIGKILL)
            p.wait()
            return p.pid
        return None

    async def ensure(self, agent: str) -> dict[str, Any]:
        """Restart a dead agent.  Returns what happened, for the delegation record."""
        if self.alive(agent):
            return {"restarted": False}
        old = self.pid(agent)
        self.start(agent)
        secs = await self.ready(agent)
        self.restarts[agent] = self.restarts.get(agent, 0) + 1
        return {"restarted": True, "old_pid": old, "new_pid": self.pid(agent), "ready_s": secs}

    def stop_all(self) -> None:
        for p in self.procs.values():
            if p.poll() is None:
                p.terminate()
        for p in self.procs.values():
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
