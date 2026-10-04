"""Live mode: the same control plane and the same enforcement code, with an LLM planning the agent's steps.

The recorded run (acp/experiments.py) keeps fixed plans so it is byte-reproducible. Live mode swaps in two things only:
LLM-planned agents (acp/agents/live/) and a real model backend behind the gateway (backends.py). The worker process
picks them up from ACP_LIVE_BACKEND, set by `acp live` before it starts the runtime.
"""

from __future__ import annotations

from acp.common import AGENTS_DIR

LIVE_AGENTS_DIR = AGENTS_DIR / "live"
LIVE_AGENTS = {"incident-agent": "acp.agents.live.incident_agent"}


def runtime_options(backend_name: str) -> dict:
    from acp.live.backends import make_backend

    return {"agents": LIVE_AGENTS, "agents_dir": LIVE_AGENTS_DIR, "backend": make_backend(backend_name)}
