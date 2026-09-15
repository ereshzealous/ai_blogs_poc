"""mcpcp: command-line entry point for the MCP capability control plane POC.

    mcpcp catalog                                   regenerate benchmark/catalogs (deterministic)
    mcpcp drift --catalog catalog_500               compare what MCP servers publish with the registry
    mcpcp discover "roll back checkout" --catalog catalog_500 [--mode search|control_plane] [--k 5]
    mcpcp policy source_control.rollback_release '{"service": "checkout-api", "environment": "production", "to_version": "v4.16"}'
    mcpcp demo [--catalog catalog_500] [--mode control_plane] [--auto-approve]
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid

import anyio

from control_plane.paths import CACHE_DIR, CATALOG_DIR
from control_plane.policy.engine import Identity, PolicyEngine, PolicyInput
from control_plane.policy.environment import ResourceInventory, resolve_environment
from control_plane.registry.registry import CapabilityRegistry

IDENTITY = Identity("oncall-1", ("sre-oncall",))
FLAGSHIP = ("Checkout API latency increased immediately after the 10:15 production deployment. Investigate the incident, "
            "identify the likely cause, recommend the safest remediation, and update the incident.")


def cmd_catalog(_: argparse.Namespace) -> None:
    from benchmark.catalog_generator.generator import write_catalogs

    summary = write_catalogs()
    print(json.dumps({k: summary[k] for k in ("counts", "catalogs")}, indent=1))


async def _drift(args: argparse.Namespace) -> None:
    from control_plane.gateway.gateway import Gateway

    registry = CapabilityRegistry.load()
    async with Gateway(CATALOG_DIR / f"{args.catalog}.json", registry, PolicyEngine.load(), world_db=CACHE_DIR / "cli-world.sqlite") as gw:
        report = registry.sync(gw.published_annotations())
    print(f"published tools: {len(gw.tools)}")
    print(f"unregistered (published over MCP, unknown to the registry): {report.unregistered}")
    print("annotation mismatches (server hint vs registry):")
    for m in report.annotation_mismatches:
        print(f"  {m['tool_id']}: server says {m['hint']}, registry says {m['registry']}")


def cmd_discover(args: argparse.Namespace) -> None:
    from control_plane.discovery.pipeline import DiscoveryService
    from control_plane.discovery.semantic import OllamaEmbedder

    manifest = json.loads((CATALOG_DIR / f"{args.catalog}.json").read_text())
    tools = {f"{t['server']}.{t['name']}": (t["server"], t["name"], t["description"], t["input_schema"]) for t in manifest["tools"]}
    service = DiscoveryService(tools, CapabilityRegistry.load(), None if args.lexical_only else OllamaEmbedder())
    res = service.search(args.request, k=args.k) if args.mode == "search" else service.control_plane(args.request, k=args.k)
    print(json.dumps(res.to_dict(), indent=1))


def cmd_policy(args: argparse.Namespace) -> None:
    registry, policy = CapabilityRegistry.load(), PolicyEngine.load()
    arguments = json.loads(args.arguments)
    rec = registry.get(args.tool_id)
    env = resolve_environment(arguments, rec, ResourceInventory.from_scenario())
    roles = tuple(args.roles.split(","))
    result = policy.evaluate(PolicyInput(Identity(args.user, roles), args.tool_id, arguments, rec, env.environment, "cli"))
    print(json.dumps(result.to_dict() | {"environment_source": env.source}, indent=1))


async def _demo(args: argparse.Namespace) -> None:
    from agent.incident_agent import run_incident_agent
    from agent.llm import make_llm
    from control_plane.discovery.pipeline import DiscoveryService
    from control_plane.discovery.semantic import OllamaEmbedder
    from control_plane.gateway.gateway import Gateway, InvocationContext
    from control_plane.telemetry import AuditLog, configure_tracing

    llm = make_llm(args.provider, args.model, think=args.think)  # fails fast on a missing key, before any server starts
    run_id = f"demo-{uuid.uuid4().hex[:8]}"
    out_dir = CACHE_DIR / run_id
    configure_tracing(out_dir / "spans.jsonl")
    registry, policy = CapabilityRegistry.load(), PolicyEngine.load()

    async def approver(req, decision) -> bool:
        print(f"\n  APPROVAL REQUIRED  {req.tool_id}  {req.arguments_json}  env={req.environment}")
        print(f"  reason: {decision.reason}  digest={req.digest[:16]}")
        if args.auto_approve:
            print("  --auto-approve: approved")
            return True
        answer = await anyio.to_thread.run_sync(lambda: input("  approve / reject? ").strip().lower())
        return answer in ("a", "approve", "y", "yes")

    async with Gateway(CATALOG_DIR / f"{args.catalog}.json", registry, policy, audit=AuditLog(out_dir / "audit.jsonl"),
                       world_db=out_dir / "world.sqlite") as gw:
        published = {p.tool_id: (p.server, p.tool.name, p.tool.description or "", p.tool.input_schema) for p in gw.tools.values()}
        discovery = DiscoveryService(published, registry, OllamaEmbedder())

        def discover(q: str) -> list[str]:
            res = discovery.search(q, k=args.k) if args.mode == "search" else discovery.control_plane(q, k=args.k)
            return [t.replace(".", "__", 1) for t in res.tool_ids]

        ctx = InvocationContext(run_id, run_id, IDENTITY, "enforce" if args.mode == "control_plane" else "observe", approver)
        print(f"{len(gw.tools)} tools on {len(gw._clients)} MCP servers; mode={args.mode}; request:\n  {args.request}\n")
        run = await run_incident_agent(llm, gw,args.request, ctx, mode=args.mode,
                                       discover=None if args.mode == "baseline" else discover)
    for s in run.steps:
        if s.tool:
            print(f"  step {s.index}: {s.tool} {json.dumps(s.arguments)} -> {s.status} {s.policy or ''}")
    print(f"\nFINAL ANSWER ({run.stopped}):\n{run.final_answer}\n\naudit and spans: {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="mcpcp", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("catalog").set_defaults(fn=cmd_catalog)
    p = sub.add_parser("drift")
    p.add_argument("--catalog", default="catalog_500")
    p.set_defaults(fn=lambda a: anyio.run(_drift, a))
    p = sub.add_parser("discover")
    p.add_argument("request")
    p.add_argument("--catalog", default="catalog_500")
    p.add_argument("--mode", default="control_plane", choices=["search", "control_plane"])
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--lexical-only", action="store_true", help="skip embeddings (no Ollama needed)")
    p.set_defaults(fn=cmd_discover)
    p = sub.add_parser("policy")
    p.add_argument("tool_id")
    p.add_argument("arguments", help="JSON object")
    p.add_argument("--user", default="oncall-1")
    p.add_argument("--roles", default="sre-oncall")
    p.set_defaults(fn=cmd_policy)
    p = sub.add_parser("demo")
    p.add_argument("--request", default=FLAGSHIP)
    p.add_argument("--catalog", default="catalog_500")
    p.add_argument("--mode", default="control_plane", choices=["baseline", "search", "control_plane"])
    p.add_argument("--provider", default="ollama", choices=["ollama", "openai"],
                   help="openai reads the key from OPENAI_API_KEY (use `uv run --env-file .env`)")
    p.add_argument("--model", default=None, help="default gpt-oss:20b for ollama; required for openai")
    p.add_argument("--think", default=None, help="ollama think level (default low) or openai reasoning_effort")
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--auto-approve", action="store_true")
    p.set_defaults(fn=lambda a: anyio.run(_demo, a))
    args = parser.parse_args()
    import httpx

    from agent.llm import ProviderError, describe_connect_error

    try:
        args.fn(args)
    except (ProviderError, ValueError) as exc:  # setup problems: say what to fix, not a traceback
        parser.exit(2, f"error: {exc}\n")
    except httpx.ConnectError as exc:
        parser.exit(2, f"error: {describe_connect_error(exc)}\n")


if __name__ == "__main__":
    sys.exit(main())
