"""The scripted human approvers (SIMULATED): a separate process that answers approval requests as the scenario says.

    python -m lineage.operator <scenario-dir>

Each approver acts only on a request the approval service shows as pending, after a short think time, and only through the
approval service (which authenticates them and signs the decision).  The script names who decides what; nothing here can
approve on the agent's behalf.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .approval import ApprovalService
from .common import load

WORLD = load("world.toml")


def main() -> None:
    sdir = Path(sys.argv[1])
    spec = json.loads((sdir / "spec.json").read_text())
    svc = ApprovalService(sdir)
    by_incident = {WORLD["incident"]["id"]: spec["executions"]["target"]["decisions"],
                   WORLD["background"]["id"]: spec["executions"]["background"]["decisions"]}
    delay = spec["run"]["approval_delay_s"]
    done: set[tuple[str, str]] = set()
    stop = sdir / "state" / "operator.stop"
    while not stop.exists():
        for req in svc.pending():
            for d in by_incident.get(req["incident"], []):
                k = (req["approval_id"], d["who"])
                if k in done:
                    continue
                time.sleep(delay)
                svc.decide(req["approval_id"], d["who"], d["decision"], d["reason"])
                done.add(k)
                if d["decision"] == "REJECTED":
                    break
        time.sleep(0.05)


if __name__ == "__main__":
    main()
