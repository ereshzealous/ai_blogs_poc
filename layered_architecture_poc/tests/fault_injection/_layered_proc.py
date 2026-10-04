"""Helper process for the SIGKILL test: runs the layered platform with the scripted model."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from layered_platform.contracts import ApprovalDecision, StartRequest  # noqa: E402
from layered_platform.service import PlatformService  # noqa: E402
from tests.fakes import ScriptedModel  # noqa: E402


async def main(workdir: str, phase: str) -> None:
    async with PlatformService.open(workdir) as svc:
        svc.workflow.model = ScriptedModel()
        if phase == "start":
            await svc.start(StartRequest(incident_id="INC-4917", requested_by="sre.alice", request_id="r-kill"))
        elif phase == "approve":
            await svc.approve(ApprovalDecision(workflow_id=svc.workflows()[0].workflow_id, decided_by="ic.bob", approve=True))
        else:
            await svc.recover()


asyncio.run(main(sys.argv[1], sys.argv[2]))
