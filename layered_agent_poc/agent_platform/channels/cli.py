"""Command-line channel.

    lap doctor                                   check Ollama models and MCP servers
    lap run INC-4917 "Checkout latency ..." --as alice
    lap status <workflow>        lap list        lap trace <workflow>        lap eval <workflow>
    lap approve <workflow> --as alice [--reject]
    lap resume <workflow>        lap recover     lap serve --port 8080
    lap report <workflow> [--out FILE]           HTML report, default runs/reports/<workflow>.html
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent_platform.channels import html_report, render
from agent_platform.contracts import ApprovalDecision, StartInvestigation
from agent_platform.service import Forbidden, PlatformService

DEFAULT_REQUEST = ("Checkout API latency increased after the 10:15 production deployment. Investigate the cause, "
                   "recommend the safest remediation, apply the approved action and update the incident.")


def command_from_args(args: argparse.Namespace) -> StartInvestigation:
    return StartInvestigation(incident_id=args.incident, request=args.request or DEFAULT_REQUEST, user_id=args.user, channel="cli")


async def _run(args: argparse.Namespace) -> int:
    async with PlatformService.open() as svc:
        if args.cmd == "doctor":
            missing = await svc.models.missing_models()
            print(f"MCP tools: {len(svc.pool.tools)} from {len(svc.pool.clients)} servers")
            print("Ollama models: " + ("all present" if not missing else f"MISSING {missing} (ollama pull ...)"))
            return 1 if missing else 0
        if args.cmd == "run":
            view = await svc.start_investigation(command_from_args(args), run_until=args.until)
        elif args.cmd == "approve":
            view = await svc.decide_approval(ApprovalDecision(workflow_id=args.workflow, approver_id=args.user,
                                                              approve=not args.reject, comment=args.comment))
        elif args.cmd == "resume":
            view = await svc.resume(args.workflow)
        elif args.cmd == "recover":
            for v in await svc.recover():
                print(render.text(v))
            return 0
        elif args.cmd == "status":
            view = svc.workflow(args.workflow)
        elif args.cmd == "list":
            for v in svc.workflows(args.status):
                print(render.text(v).splitlines()[0])
            return 0
        elif args.cmd == "trace":
            print(render.trace_tree(svc.trace(args.workflow)))
            return 0
        elif args.cmd == "eval":
            print(json.dumps(svc.evaluate(args.workflow), indent=2))
            return 0
        elif args.cmd == "report":
            out = Path(args.out) if args.out else svc.settings.runs_dir / "reports" / f"{args.workflow}.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            out.write_text(html_report.workflow_page(svc.workflow_record(args.workflow), stamp), encoding="utf-8")
            print(f"wrote {out}")
            return 0
        else:
            raise SystemExit(f"unknown command {args.cmd}")
        print(json.dumps(view, indent=2, default=str) if args.json else render.text(view))
        return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lap", description="Layered agent platform (INC-4917 POC)")
    p.add_argument("--json", action="store_true", help="print the raw workflow view")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    r = sub.add_parser("run")
    r.add_argument("incident")
    r.add_argument("request", nargs="?")
    r.add_argument("--as", dest="user", default="alice")
    r.add_argument("--until", help="stop after this step (for demos)")
    a = sub.add_parser("approve")
    a.add_argument("workflow")
    a.add_argument("--as", dest="user", required=True)
    a.add_argument("--reject", action="store_true")
    a.add_argument("--comment", default="")
    for name in ("status", "resume", "trace", "eval"):
        sub.add_parser(name).add_argument("workflow")
    rp = sub.add_parser("report", help="write an HTML report for one workflow")
    rp.add_argument("workflow")
    rp.add_argument("--out", help="output file (default: runs/reports/<workflow>.html)")
    sub.add_parser("recover")
    ls = sub.add_parser("list")
    ls.add_argument("--status")
    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8080)
    return p


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if args.cmd == "serve":
        import uvicorn

        from agent_platform.channels.rest import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")
        return
    try:
        sys.exit(asyncio.run(_run(args)))
    except Forbidden as exc:
        print(f"forbidden: {exc}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
