"""Crash injection for experiments. `LAP_CRASH_ON=<event>` kills this process with SIGKILL when <event> happens,
e.g. `after_step:await_approval` or `timeout:source_control.rollback_release`. Never set in normal operation."""

from __future__ import annotations

import os
import signal
import sys


def maybe_crash(event: str) -> None:
    wanted = os.environ.get("LAP_CRASH_ON")
    if wanted and wanted == event:
        sys.stdout.flush()
        sys.stderr.write(f"\n[fault injection] SIGKILL at {event}\n")
        sys.stderr.flush()
        os.kill(os.getpid(), signal.SIGKILL)
