"""Named crash points shared by both architectures.

    F2_CRASH_AT=after_tool_result:rollback_release     SIGKILL this process the first time that point is reached

The experiment harness sets the variable; the process kills itself with a real SIGKILL (no cleanup, no finally
blocks, no flush), which is what a node failure or OOM kill looks like to the code.  A marker file makes each crash
point fire once per scenario directory, so the restarted process runs through it.
"""

from __future__ import annotations

import os
import signal
from pathlib import Path


def hit(point: str) -> None:
    want = os.environ.get("F2_CRASH_AT", "")
    if not want or want != point:
        return
    marker = Path(os.environ.get("F2_CRASH_MARKER", ".crashed"))
    if marker.exists():
        return
    marker.write_text(f"{point} pid={os.getpid()}\n")
    os.kill(os.getpid(), signal.SIGKILL)
