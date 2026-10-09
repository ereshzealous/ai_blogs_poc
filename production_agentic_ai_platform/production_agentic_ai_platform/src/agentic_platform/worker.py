"""A runtime process the proof can kill.

    python -m agentic_platform.worker <exp_dir> start            submit INC-4917 as sre.alice and run until parked
    python -m agentic_platform.worker <exp_dir> resume <wf_id>   continue the workflow from its last checkpoint

Environment: PAP_CRASH_AT=<point> (wait at that point to be SIGKILLed), PAP_RECOVERY=lookup|resend,
PAP_NAIVE_IDEMPOTENCY=1 (a fresh idempotency key per attempt: the bug R10 measures).  Prints one RESULT line.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import anyio

from agentic_platform.runtime import Runtime

REQUEST = "Investigate INC-4917. Determine the safe remediation. Execute it only if authorized."


async def main(exp_dir: Path, mode: str, wf_id: str | None) -> None:
    keys = json.loads((exp_dir / ".keys.json").read_text())
    async with Runtime(exp_dir, config_dir=exp_dir / "control-plane", keys=keys) as rt:
        if mode == "start":
            wf_id = await rt.submit(user_id="sre.alice", channel="pager", text=REQUEST, incident_id="INC-4917")
        st = await rt.run(wf_id)
    print("RESULT " + json.dumps({"workflow_id": wf_id, "status": st["status"], "error": st.get("error"), "approval_id": st.get("approval_id"),
                                  "digest": st.get("digest"), "result": st.get("result")}), flush=True)


if __name__ == "__main__":
    anyio.run(main, Path(sys.argv[1]), sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
