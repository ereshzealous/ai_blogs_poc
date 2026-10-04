"""The long-lived agent runtime process: `python -m acp.runtime.worker <state-dir> <instance>`.

It imports the agents once, at start, and then serves JSON-line requests on stdin for as long as the experiment
lasts. Control-plane changes are published by a different process (the experiment driver) while this one keeps
running, so a proof can show the same process, with the same loaded code, behaving differently.

Requests:  {"op": "run", "agent", "task", "run_id", "tick", "checkpoint_after"?}
           {"op": "resume", "approval_id", "tick"}     {"op": "status", "tick"}     {"op": "exit"}
While a run is paused at a checkpoint the worker writes {"checkpoint": ...} and waits for {"op": "continue"}.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from acp.runtime.sdk import Runtime


def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, sort_keys=True) + "\n")
    sys.stdout.flush()


def main() -> None:
    state, instance = Path(sys.argv[1]), sys.argv[2]
    live = os.environ.get("ACP_LIVE_BACKEND")  # set only by `acp live`: LLM-planned agents and a real model backend
    if live:
        from acp.live import runtime_options

        rt = Runtime(state, instance, **runtime_options(live))
    else:
        rt = Runtime(state, instance)
    send({"ready": True, "instance": instance, "pid": os.getpid(), "loaded_code_sha256": rt.loaded_code_sha256})
    for line in sys.stdin:
        req = json.loads(line)
        op = req["op"]
        if op == "exit":
            send({"bye": True, "pid": os.getpid()})
            return
        if op == "run":
            n = req.get("checkpoint_after")

            def pause(rs, n=n):
                if n is not None and sum(1 for c in rs.calls if c["kind"] == "tool") == n:
                    send({"checkpoint": {"run_id": rs.run_id, "tool_calls_so_far": n, "tick": rs.tick}})
                    nxt = json.loads(sys.stdin.readline())
                    assert nxt["op"] == "continue", nxt

            rt.checkpoint = pause if n is not None else None
            out = rt.run(req["agent"], req["task"], req["run_id"], req["tick"])
            rt.checkpoint = None
        elif op == "resume":
            out = rt.resume(req["approval_id"], req["tick"])
        elif op == "status":
            out = rt.status(req["tick"])
        else:
            out = {"error": f"unknown op {op}"}
        send({"response": out, "pid": os.getpid(), "code_sha256": rt.status(0)["code_sha256"], "loaded_code_sha256": rt.loaded_code_sha256})


if __name__ == "__main__":
    main()
