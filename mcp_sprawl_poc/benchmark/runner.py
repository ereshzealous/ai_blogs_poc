"""Benchmark runner.

    python -m benchmark.runner retrieval --run-id R1                     # discovery only, no LLM
    python -m benchmark.runner selection --run-id R1 [--catalogs ...] [--modes ...] [--cases D01,A02] [--split test]
    python -m benchmark.runner agent --run-id R1 [--catalogs ...] [--modes ...]

Every row is appended to `benchmark/runs/<run-id>/*.jsonl` as soon as it is produced, and a rerun with
the same run id skips rows that already exist, so long runs can be interrupted and resumed. Reports are
built only from these raw files (`python -m benchmark.reports.build_report`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anyio
import httpx

from agent.llm import PROVIDERS, ChatModel, ProviderError, describe_connect_error, make_llm, temperature_arg
from agent.selection import select_tool
from benchmark.evaluator.metrics import Case, load_cases, retrieval_scores, score_selection
from control_plane.discovery.pipeline import DiscoveryService
from control_plane.discovery.semantic import OllamaEmbedder
from control_plane.gateway.gateway import Gateway, InvocationContext
from control_plane.paths import CATALOG_DIR, REPO_ROOT
from control_plane.policy.approvals import ApprovalRequest
from control_plane.policy.engine import Identity, PolicyEngine, PolicyResult
from control_plane.registry.registry import CapabilityRegistry
from control_plane.telemetry import AuditLog, configure_tracing, span

RUNS_DIR = REPO_ROOT / "benchmark" / "runs"
LADDER = ["catalog_10", "catalog_25", "catalog_50", "catalog_100", "catalog_250", "catalog_500"]
OVERLAP = ["low_overlap_100", "high_overlap_100"]
MODES = ["baseline", "search", "control_plane"]
ENFORCEMENT = {"baseline": "observe", "search": "observe", "control_plane": "enforce"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class JsonlWriter:
    def __init__(self, path: Path, key_fields: tuple[str, ...]):
        self.path, self.key_fields = path, key_fields
        self.done: set[tuple] = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.done.add(tuple(row.get(k) for k in key_fields))

    def has(self, **key: Any) -> bool:
        return tuple(key.get(k) for k in self.key_fields) in self.done

    def write(self, row: dict[str, Any]) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        self.done.add(tuple(row.get(k) for k in self.key_fields))


def _manifest_tools(catalog: str) -> dict[str, tuple[str, str, str, dict[str, Any]]]:
    manifest = json.loads((CATALOG_DIR / f"{catalog}.json").read_text(encoding="utf-8"))
    return {f"{t['server']}.{t['name']}": (t["server"], t["name"], t["description"], t["input_schema"]) for t in manifest["tools"]}


def _write_config(run_dir: Path, section: str, config: dict[str, Any]) -> None:
    path = run_dir / "config.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data.setdefault(section, [])
    data[section].append(config)
    path.write_text(json.dumps(data, indent=1, default=str) + "\n")


def _base_config(args: argparse.Namespace, catalogs: list[str]) -> dict[str, Any]:
    return {
        "started_at": _now(),
        "catalogs": {c: {"sha256": _sha256(CATALOG_DIR / f"{c}.json")} for c in catalogs},
        "registry_sha256": _sha256(CATALOG_DIR / "registry.json"),
        "policy_sha256": _sha256(REPO_ROOT / "control_plane" / "policy" / "policies.yaml"),
        "cases_sha256": _sha256(REPO_ROOT / "benchmark" / "prompts" / "cases.yaml"),
        "k": getattr(args, "k", None),
        "argv": vars(args),
    }


def _select_cases(args: argparse.Namespace) -> list[Case]:
    cases = load_cases()
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [c for c in cases if c.id in wanted]
    if args.split != "all":
        cases = [c for c in cases if c.split == args.split]
    return cases


# ----------------------------------------------------------------------------------------------
# Retrieval-only evaluation
# ----------------------------------------------------------------------------------------------
def run_retrieval(args: argparse.Namespace) -> None:
    run_dir = RUNS_DIR / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    catalogs = args.catalogs.split(",")
    registry = CapabilityRegistry.load()
    embedder = OllamaEmbedder()
    cases = _select_cases(args)
    _write_config(run_dir, "retrieval", _base_config(args, catalogs) | {"embedding_model": embedder.model, "embedding_digest": embedder.digest})
    out = JsonlWriter(run_dir / "retrieval.jsonl", ("catalog", "mode", "retrieval", "case_id"))
    c10 = set(_manifest_tools("catalog_10"))
    for catalog in catalogs:
        tools = _manifest_tools(catalog)
        t0 = time.perf_counter()
        service = DiscoveryService(tools, registry, embedder)
        print(f"[retrieval] {catalog}: index built in {time.perf_counter() - t0:.1f}s", flush=True)
        for case in cases:
            if case.golden_tool not in tools:
                continue
            for mode in ("search", "control_plane"):
                for retrieval in ("bm25", "semantic", "hybrid"):
                    if out.has(catalog=catalog, mode=mode, retrieval=retrieval, case_id=case.id):
                        continue
                    if mode == "search":
                        res = service.search(case.prompt, k=10, retrieval=retrieval)
                    else:
                        res = service.control_plane(case.prompt, k=10, retrieval=retrieval)
                    rec = registry.get(case.golden_tool)
                    route = res.route
                    out.write({
                        "run_id": args.run_id, "catalog": catalog, "catalog_size": len(tools), "mode": mode, "retrieval": retrieval,
                        "case_id": case.id, "category": case.category, "split": case.split, "ladder_subset": case.golden_tool in c10,
                        "golden_tool": case.golden_tool, "candidates": res.tool_ids, "latency_ms": round(res.latency_ms, 3),
                        "stages": res.stages,
                        "route_domains": route.domains if route else None,
                        "route_operation": route.operation if route else None,
                        "route_domain_correct": (rec.domain in route.domains) if route and rec else None,
                        "route_operation_correct": (route.operation == ("write" if rec.side_effect else "read")) if route and rec else None,
                        "golden_filtered_out": (case.golden_tool not in set(service.filter_candidates(route))) if route else None,
                        **retrieval_scores(case, res.tool_ids),
                    })
        print(f"[retrieval] {catalog}: done", flush=True)


# ----------------------------------------------------------------------------------------------
# Selection benchmark (one decision per case, executed through the gateway)
# ----------------------------------------------------------------------------------------------
async def run_selection(args: argparse.Namespace) -> None:
    run_dir = RUNS_DIR / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    configure_tracing(run_dir / "spans.jsonl")
    audit = AuditLog(run_dir / "audit.jsonl")
    catalogs, modes = args.catalogs.split(","), args.modes.split(",")
    registry, policy = CapabilityRegistry.load(), PolicyEngine.load()
    llm = make_llm(args.provider, args.model, seed=args.seed, num_ctx=args.num_ctx, think=args.think, temperature=args.temperature)
    embedder = OllamaEmbedder()
    cases = _select_cases(args)
    _write_config(run_dir, "selection", _base_config(args, catalogs) | {
        "model": llm.model_info(), "embedding_model": embedder.model, "embedding_digest": embedder.digest,
        "modes": modes, "enforcement": ENFORCEMENT,
        "approver": "scripted: approves only the golden tool with correct arguments; rejects everything else",
    })
    out = JsonlWriter(run_dir / "selection.jsonl", ("catalog", "mode", "case_id"))
    tokens_path = run_dir / "prompt_tokens_without_tools.json"
    no_tool_tokens: dict[str, int] = json.loads(tokens_path.read_text()) if tokens_path.exists() else {}
    c10 = set(_manifest_tools("catalog_10"))
    world_db = run_dir / "world.sqlite"

    for case in cases:  # prompt size without any tool definitions, measured once per case
        if case.id not in no_tool_tokens:
            identity = Identity(case.user_id, case.roles)
            from agent.prompts import system_prompt

            r = llm.chat([{"role": "system", "content": system_prompt(identity.user_id, identity.roles)},
                          {"role": "user", "content": case.prompt}], None, {"num_predict": 1})
            if r.prompt_tokens is None:  # e.g. a model that is not pulled: stop before any benchmark row is written
                raise ProviderError(f"could not measure the no-tools prompt size for {case.id}: {r.error}")
            no_tool_tokens[case.id] = r.prompt_tokens
            tokens_path.write_text(json.dumps(no_tool_tokens, indent=1, sort_keys=True) + "\n")

    for catalog in catalogs:
        manifest = CATALOG_DIR / f"{catalog}.json"
        eligible = [c for c in cases if c.golden_tool in _manifest_tools(catalog)]
        pending = [(m, c) for m in modes for c in eligible if not out.has(catalog=catalog, mode=m, case_id=c.id)]
        if not pending:
            print(f"[selection] {catalog}: nothing to do", flush=True)
            continue
        async with Gateway(manifest, registry, policy, audit=audit, world_db=world_db) as gw:
            published = {p.tool_id: (p.server, p.tool.name, p.tool.description or "", p.tool.input_schema) for p in gw.tools.values()}
            by_tool_id = {p.tool_id: p for p in gw.tools.values()}
            discovery = DiscoveryService(published, registry, embedder) if any(m != "baseline" for m, _ in pending) else None
            all_defs = [p.definition() for p in gw.tools.values()]
            for mode in modes:
                block = [c for m, c in pending if m == mode]
                print(f"[selection] {catalog} / {mode}: {len(block)} cases", flush=True)
                for case in block:
                    await _selection_case(args, gw, discovery, by_tool_id, all_defs, llm, registry, case, catalog, mode, out,
                                          no_tool_tokens, c10)


async def _selection_case(args, gw: Gateway, discovery: DiscoveryService | None, by_tool_id, all_defs, llm: ChatModel,
                          registry: CapabilityRegistry, case: Case, catalog: str, mode: str, out: JsonlWriter,
                          no_tool_tokens: dict[str, int], c10: set[str]) -> None:
    identity = Identity(case.user_id, case.roles)
    run_id = f"{args.run_id}:{catalog}:{mode}:{case.id}"
    disc = None
    t_case = time.perf_counter()
    with span("benchmark.case", case_id=case.id, catalog=catalog, mode=mode, scenario_id="INC-4917", catalog_size=len(gw.tools)) as s:
        if mode == "baseline":
            defs = all_defs
        else:
            assert discovery is not None
            disc = discovery.search(case.prompt, k=args.k) if mode == "search" else discovery.control_plane(case.prompt, k=args.k)
            defs = [by_tool_id[t].definition() for t in disc.tool_ids if t in by_tool_id]
            s.set_attribute("discovery.candidates", ",".join(disc.tool_ids))
            s.set_attribute("discovery.latency_ms", round(disc.latency_ms, 3))
        with span("agent.select_tool", tools_in_prompt=len(defs)):
            sel = select_tool(llm, defs, case.prompt, identity)
        s.set_attribute("selected_tool", sel.tool_id or "")
        props = by_tool_id[sel.tool_id].tool.input_schema.get("properties", {}) if sel.tool_id in by_tool_id else {}
        score = score_selection(case, sel.tool_id, sel.arguments, registry=registry, catalog_tool_ids=set(by_tool_id),
                                schema_properties=props)

        async def approver(req: ApprovalRequest, decision: PolicyResult) -> bool:
            return bool(score["exact"] and score["args_correct"])

        outcome = None
        if sel.exposed_name:
            ctx = InvocationContext(f"{run_id}:1", run_id, identity, ENFORCEMENT[mode], approver)  # type: ignore[arg-type]
            outcome = await gw.call_tool(sel.exposed_name, sel.arguments, ctx)
    resp = sel.response
    row = {
        "run_id": args.run_id, "catalog": catalog, "catalog_size": len(gw.tools), "mode": mode, "k": args.k,
        "case_id": case.id, "category": case.category, "split": case.split, "ladder_subset": case.golden_tool in c10,
        "prompt": case.prompt, "golden_tool": case.golden_tool, "expected_policy": case.expected_policy,
        "arguments": sel.arguments, "tool_calls_returned": sel.tool_call_count, **score,
        "candidates": disc.tool_ids if disc else None, "discovery_latency_ms": round(disc.latency_ms, 3) if disc else None,
        "discovery_stages": disc.stages if disc else None, "route": disc.route.to_dict() if disc and disc.route else None,
        **({f"retrieval_{k}": v for k, v in retrieval_scores(case, disc.tool_ids, ks=(1, 3, 5)).items()} if disc else {}),
        "golden_in_prompt": (case.golden_tool in disc.tool_ids) if disc else True,
        "tools_in_prompt": len(all_defs) if mode == "baseline" else len(disc.tool_ids) if disc else 0,
        "policy_decision": outcome.policy.decision.value if outcome and outcome.policy else None,
        "policy_rule": outcome.policy.rule_id if outcome and outcome.policy else None,
        "enforcement": ENFORCEMENT[mode], "status": outcome.status if outcome else "no_call",
        "executed": bool(outcome and outcome.executed), "execution_error": bool(outcome and outcome.is_error),
        "execution_latency_ms": round(outcome.latency_ms, 2) if outcome else None,
        "unsafe_execution": bool(score["unsafe_selection"] and outcome and outcome.executed),
        "prompt_tokens": resp.prompt_tokens, "completion_tokens": resp.completion_tokens,
        "total_tokens": (resp.prompt_tokens or 0) + (resp.completion_tokens or 0) if resp.prompt_tokens is not None else None,
        "prompt_tokens_without_tools": no_tool_tokens.get(case.id),
        "tool_definition_tokens": (resp.prompt_tokens - no_tool_tokens[case.id]) if resp.prompt_tokens and case.id in no_tool_tokens else None,
        "llm_latency_ms": round(resp.latency_ms, 1), "prompt_eval_ms": round(resp.prompt_eval_ms, 1) if resp.prompt_eval_ms else None,
        "thinking_chars": resp.thinking_chars, "done_reason": resp.done_reason, "llm_error": resp.error,
        "assistant_content": (resp.content or "")[:400], "case_wall_ms": round((time.perf_counter() - t_case) * 1000, 1),
        "finished_at": _now(),
    }
    out.write(row)
    mark = "✓" if score["exact"] else ("~" if score["capability_correct"] else "✗")
    print(f"  {mark} {case.id:4s} {mode:13s} {str(sel.tool_id):45s} policy={row['policy_decision']} "
          f"tok={resp.prompt_tokens} {resp.latency_ms / 1000:.1f}s", flush=True)


# ----------------------------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="MCP tool-sprawl benchmark runner")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("retrieval", "selection", "agent"):
        p = sub.add_parser(name)
        p.add_argument("--run-id", required=True)
        p.add_argument("--catalogs", default=",".join(LADDER + OVERLAP))
        p.add_argument("--cases", default="")
        p.add_argument("--split", default="all", choices=["all", "dev", "test"])
        if name != "retrieval":
            p.add_argument("--modes", default=",".join(MODES))
            p.add_argument("--k", type=int, default=5)
            p.add_argument("--provider", default="ollama", choices=PROVIDERS,
                           help="openai reads the key from OPENAI_API_KEY (use `uv run --env-file .env`)")
            p.add_argument("--model", default=None, help="default gpt-oss:20b for ollama; required for openai")
            p.add_argument("--think", default=None, help="ollama think level (default low) or openai reasoning_effort (omitted unless set)")
            p.add_argument("--temperature", type=temperature_arg, default=0.0, help='a number, or "none" for the provider default')
            p.add_argument("--seed", type=int, default=7)
            p.add_argument("--num-ctx", type=int, default=131072, help="ollama only")
        if name == "agent":
            p.add_argument("--max-steps", type=int, default=16)
    args = parser.parse_args()
    try:
        if args.command == "retrieval":
            run_retrieval(args)
        elif args.command == "selection":
            anyio.run(run_selection, args)
        else:
            from benchmark.agent_runner import run_agent_benchmark

            anyio.run(run_agent_benchmark, args)
    except (ProviderError, ValueError) as exc:  # setup problems: say what to fix, not a traceback
        parser.exit(2, f"error: {exc}\n")
    except httpx.ConnectError as exc:
        parser.exit(2, f"error: {describe_connect_error(exc)}\n")


if __name__ == "__main__":
    main()
