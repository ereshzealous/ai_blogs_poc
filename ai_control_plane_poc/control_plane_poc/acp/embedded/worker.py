"""BASELINE runtime: agents that carry their own governance, served by a long-lived process.

    python -m acp.embedded.worker <state-dir> <agents-dir>

It loads the three embedded agents from <agents-dir> once, at start, like a deployed service. There is no control plane
to consult: each call is checked against the constants inside the agent's own file, and executed with the agent's own
long-lived static credential. A governance change is therefore a code change, and it takes effect only in a process
started after the edit (a redeploy).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

from acp.systems import ModelGateway, SystemRefused, Systems

SERVERS = {
    "query_logs": "observability-mcp",
    "query_metrics": "observability-mcp",
    "restart_service": "deploy-mcp",
    "read_case": "support-mcp",
    "refund_customer": "billing-mcp",
    "read_ledger": "billing-mcp",
    "flag_transaction": "billing-mcp",
}
FILES = {"incident-agent": "incident_agent.py", "support-agent": "support_agent.py", "finance-agent": "finance_agent.py"}


class Tools:
    """What the embedded agents call. Every rule it applies was passed in from the agent's own file."""

    def __init__(self, state: Path, agent: str, tick: int):
        self.systems, self.models, self.agent, self.tick, self.n, self.calls = Systems(state), ModelGateway(state), agent, tick, 0, []

    def call(self, tool, allowed, credentials, max_calls, needs_approval, **args):
        self.tick += 1
        if tool not in allowed:
            out = {"status": "denied", "reason": "NOT_IN_AGENT_ALLOWLIST"}
        elif self.n >= max_calls:
            out = {"status": "denied", "reason": "AGENT_MAX_TOOL_CALLS"}
        elif needs_approval(tool, args):
            out = {"status": "pending_approval", "reason": "AGENT_APPROVAL_RULE"}
        else:
            self.n += 1
            cred = {"id": credentials[tool], "agent": self.agent, "audience": tool, "expires_tick": 10**9}  # a long-lived static secret
            try:
                out = {"status": "executed", "value": self.systems.call(SERVERS[tool], tool, args, self.agent, cred, self.tick)}
            except SystemRefused as e:
                out = {"status": "denied", "reason": str(e)}
        self.calls.append({"kind": "tool", "name": tool, "status": out["status"], "reason": out.get("reason")})
        return out

    def model(self, model, purpose, data):
        self.tick += 1
        r = self.models.complete(model["name"], model, purpose + " " + " ".join(map(str, data)), self.agent, "unclassified", self.tick)
        self.calls.append({"kind": "model", "name": model["name"], "status": "executed", "reason": None})
        return r


def load(agents_dir: Path) -> dict:
    mods = {}
    for name, f in FILES.items():
        spec = importlib.util.spec_from_file_location(f"embedded_{name.replace('-', '_')}", agents_dir / f)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        mods[name] = m
    return mods


def main() -> None:
    state, agents_dir = Path(sys.argv[1]), Path(sys.argv[2])
    agents = load(agents_dir)
    sys.stdout.write(json.dumps({"ready": True, "pid": os.getpid()}) + "\n")
    sys.stdout.flush()
    for line in sys.stdin:
        req = json.loads(line)
        if req["op"] == "exit":
            return
        t = Tools(state, req["agent"], req["tick"])
        result = agents[req["agent"]].run(req["task"], t)
        sys.stdout.write(json.dumps({"response": {"agent": req["agent"], "calls": t.calls, "result": result}, "pid": os.getpid()}, sort_keys=True) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
