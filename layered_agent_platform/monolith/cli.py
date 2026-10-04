"""CLI for the monolith: `monolith run INC-4917 "..." [--yes]`. The conversation lives only in this process."""

from __future__ import annotations

import argparse
import asyncio
import logging

from monolith.incident_agent import IncidentAgent, ask_on_terminal

REQUEST = ("Checkout API latency increased after the 10:15 production deployment on INC-4917. Investigate the cause, "
           "recommend the safest remediation, apply the approved action and update the incident.")


async def _auto_yes(tool: str, args: dict) -> bool:
    print(f"[auto-approved] {tool} {args}")
    return True


async def main_async(args: argparse.Namespace) -> None:
    agent = IncidentAgent(model=args.model, approver=_auto_yes if args.yes else ask_on_terminal)
    await agent.connect()
    try:
        answer = await agent.run(args.request or REQUEST)
        print(answer)
        print(f"\n(tokens: {agent.token_count})")
    finally:
        await agent.close()


def main() -> None:
    p = argparse.ArgumentParser(prog="monolith")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("incident")
    r.add_argument("request", nargs="?")
    r.add_argument("--model", default="gpt-oss:20b")
    r.add_argument("--yes", action="store_true", help="approve every write without asking")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
