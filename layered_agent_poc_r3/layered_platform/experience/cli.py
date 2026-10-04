"""Command-line experience.  Talks only to PlatformService and the contracts.

    python -m layered_platform.experience.cli start INC-4917 --as sre.alice --request-id r1
    python -m layered_platform.experience.cli approve <workflow-id> --as ic.bob
    python -m layered_platform.experience.cli status <workflow-id> | resume <workflow-id> | recover
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid

from layered_platform.contracts import ApprovalDecision, StartRequest
from layered_platform.experience import render
from layered_platform.service import PlatformService


async def _main(a: argparse.Namespace) -> None:
    async with PlatformService.open(a.workdir) as svc:
        if a.cmd == "start":
            v = await svc.start(StartRequest(incident_id=a.target, requested_by=a.principal, channel="cli",
                                             request_id=a.request_id or uuid.uuid4().hex, instructions=a.instructions))
        elif a.cmd == "approve":
            v = await svc.approve(ApprovalDecision(workflow_id=a.target, decided_by=a.principal, approve=not a.reject, reason=a.reason))
        elif a.cmd == "resume":
            v = await svc.resume(a.target)
        elif a.cmd == "recover":
            for v in await svc.recover():
                print(render.text(v))
            return
        else:
            v = svc.view(a.target)
        print(json.dumps(render.chat(v)) if a.format == "chat" else render.text(v))


def main() -> None:
    p = argparse.ArgumentParser(prog="f2")
    p.add_argument("cmd", choices=["start", "approve", "resume", "status", "recover"])
    p.add_argument("target", nargs="?", default="")
    p.add_argument("--as", dest="principal", default="sre.alice")
    p.add_argument("--request-id", default="")
    p.add_argument("--instructions", default="Investigate the incident and remediate it safely.")
    p.add_argument("--reject", action="store_true")
    p.add_argument("--reason", default="")
    p.add_argument("--format", choices=["text", "chat"], default="text")
    p.add_argument("--workdir", default=os.environ.get("F2_WORKDIR", "var/platform"))
    asyncio.run(_main(p.parse_args()))


if __name__ == "__main__":
    main()
