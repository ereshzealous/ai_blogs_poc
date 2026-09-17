"""CLI channel. Runs the capability in this process; the workflow lives in the platform, not in the terminal.

    hai start INC-4917 [--request TEXT] [--detach]      start; waits until the workflow pauses or ends
    hai status <workflow>                               read the capability state
    hai approve <workflow> | hai reject <workflow>      take an available action (waits for the result)
    hai retry <workflow>
    hai serve [--channels slack,web,rest,event] [--port 8090]
    global: --as SUBJECT (or HAI_CLI_SUBJECT)   --json   print the contract instead of text

Exit codes: 0 completed · 10 waiting for approval · 11 running · 20 rejected · 1 failed · 2 usage · 3 not allowed
· 4 conflict or not found.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from headless_ai_platform.channels import CAPABILITY
from headless_ai_platform.contracts import CapabilityError, CapabilityResponse, ErrorCode
from headless_ai_platform.renderers import cli as text

CHANNEL = "cli"
VERB = {"approve": "approve-remediation", "reject": "reject-remediation", "retry": "retry"}
ERROR_EXIT = {ErrorCode.FORBIDDEN: 3, ErrorCode.UNKNOWN_IDENTITY: 3, ErrorCode.CONFLICT: 4, ErrorCode.NOT_FOUND: 4}


def request_from_args(args: argparse.Namespace, binding: str | None = None) -> dict[str, Any]:
    actor = {"channel": CHANNEL, "channel_subject": args.subject}
    ctx = {"thread_ref": f"tty:{os.getpid()}"}
    if args.cmd == "start":
        return {"capability": CAPABILITY, "operation": "start", "actor": actor, "channel_context": ctx,
                "input": {"incident_id": args.incident, **({"request": args.request} if args.request else {})}}
    if args.cmd == "status":
        return {"capability": CAPABILITY, "operation": "get", "workflow_id": args.workflow, "actor": actor}
    return {"capability": CAPABILITY, "operation": "act", "workflow_id": args.workflow, "action_id": VERB[args.cmd],
            "binding": binding, "actor": actor, "channel_context": ctx,
            "input": {"comment": args.comment} if getattr(args, "comment", "") else {}}


def show(resp: CapabilityResponse, as_json: bool) -> int:
    print(json.dumps(resp.model_dump(mode="json"), indent=2) if as_json else text.render(resp))
    return text.exit_code(resp)


async def run(args: argparse.Namespace) -> int:
    from headless_ai_platform.runtime import open_gateway

    async with open_gateway() as gw:
        try:
            wait = not getattr(args, "detach", False)
            resp = await gw.handle(request_from_args(args), wait=wait and args.cmd != "status")
        except CapabilityError as exc:
            print(f"{exc.code.value}: {exc.message}", file=sys.stderr)
            return ERROR_EXIT.get(exc.code, 2)
        return show(resp, args.json)


def serve(args: argparse.Namespace) -> int:
    import uvicorn

    os.environ["HAI_CHANNELS"] = args.channels
    uvicorn.run("headless_ai_platform.server:create_app", factory=True, host=args.host, port=args.port, log_level="warning")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hai", description="Headless incident capability, CLI channel")
    p.add_argument("--as", dest="subject", default=os.environ.get("HAI_CLI_SUBJECT", "alice@company.example"))
    p.add_argument("--json", action="store_true", help="print the capability response as JSON")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("incident")
    s.add_argument("--request")
    s.add_argument("--detach", action="store_true", help="return at once (the workflow keeps running only while this process lives)")
    sub.add_parser("status").add_argument("workflow")
    for verb in VERB:
        a = sub.add_parser(verb)
        a.add_argument("workflow")
        a.add_argument("--comment", default="")
    sv = sub.add_parser("serve")
    sv.add_argument("--channels", default="slack,web,rest,event")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8090)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.cmd == "serve":
        return serve(args)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
