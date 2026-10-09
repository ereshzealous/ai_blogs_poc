"""Named crash points, in the style of F2's crashpoints.py and T3's crash.py.

    LINEAGE_CRASH_AT=after_dispatch      SIGKILL this process the first time that point is reached

A real SIGKILL: no cleanup, no finally blocks, no span export, no metrics flush.  A marker file makes each point fire once,
so the restarted process runs through it.
"""

from __future__ import annotations

import os
import signal
from pathlib import Path

POINTS = ("awaiting_approval", "after_dispatch")


def hit(point: str) -> None:
    if os.environ.get("LINEAGE_CRASH_AT", "") != point:
        return
    marker = Path(os.environ.get("LINEAGE_CRASH_MARKER", ".crashed"))
    if marker.exists():
        return
    marker.write_text(f"{point} pid={os.getpid()}\n")
    os.kill(os.getpid(), signal.SIGKILL)
