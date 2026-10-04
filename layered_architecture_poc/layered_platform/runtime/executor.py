"""Durable step execution.  The orchestrator supplies the steps; the runtime makes running them survivable.

Each step is a function (state) -> StepResult.  After it returns, the executor writes one checkpoint (state + the next
step + status) atomically, then continues.  On resume it reads the workflow record and starts at the step after the
last checkpoint, so a completed step is never run again.  A step interrupted mid-way *is* run again, which is why
side effects inside a step must carry an operation id (tools/idempotency.py).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import crashpoints
from layered_platform.runtime.checkpoints import CheckpointStore
from layered_platform.telemetry.tracing import annotate, continue_trace, span

TERMINAL = {"COMPLETED", "FAILED", "ESCALATED", "REJECTED"}


@dataclass
class StepResult:
    next_step: str
    status: str = "RUNNING"          # RUNNING | WAITING_APPROVAL | COMPLETED | FAILED | ESCALATED | REJECTED
    updates: dict[str, Any] = field(default_factory=dict)


Step = Callable[[str, dict[str, Any]], Awaitable[StepResult]]


class DurableExecutor:
    def __init__(self, store: CheckpointStore):
        self.store = store

    async def run(self, wf: str, steps: dict[str, Step]) -> dict[str, Any]:
        rec = self.store.load(wf)
        self.store.acquire(wf)
        try:
            with continue_trace(rec["trace_id"], rec["root_span_id"]):
                if rec["status"] != "RUNNING":
                    return rec
                resumed = bool(self.store.history(wf))
                self.store.event(wf, "run.resumed" if resumed else "run.started", rec["step"], {"from_step": rec["step"]})
                while True:
                    rec = self.store.load(wf)
                    step, state = rec["step"], rec["state"]
                    if rec["status"] != "RUNNING" or step not in steps:
                        return rec
                    with span("workflow.step", **{"f2.workflow_id": wf, "f2.step": step, "f2.request_id": rec["request_id"]}):
                        self.store.event(wf, "step.started", step)
                        try:
                            result = await steps[step](wf, state)
                        except Exception as exc:  # the step stays current, so a resume retries it
                            self.store.event(wf, "step.failed", step, {"error": f"{type(exc).__name__}: {exc}"})
                            raise
                        new_state = {**state, **result.updates, "completed_steps": [*state.get("completed_steps", []), step]}
                        seq = self.store.checkpoint(wf, step, result.next_step, result.status, new_state)
                        annotate(**{"f2.checkpoint.seq": seq, "f2.next_step": result.next_step, "f2.status": result.status})
                        self.store.event(wf, "checkpoint.saved", step, {"seq": seq, "next_step": result.next_step, "status": result.status})
                    crashpoints.hit(f"after_checkpoint:{step}")
                    if result.status != "RUNNING":
                        return self.store.load(wf)
        finally:
            self.store.release(wf)
