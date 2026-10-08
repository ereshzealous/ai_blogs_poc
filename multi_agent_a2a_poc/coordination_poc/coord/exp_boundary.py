"""E7: what does an agent boundary cost, and what does it buy, when the agent's work is held constant?

    python -m coord.exp_boundary --run-id <id> [--n 100]

The same diagnosis-agent code (coord/specialists.run_specialist) with the same scripted model, the same token, the
same world and the same one MCP read, invoked two ways, interleaved:
  in-process   a function call in the host process (no protocol, no serialization, no network)
  A2A          SendStreamingMessage to the agent's own OS process over loopback HTTP (JSON-RPC), Agent Card resolved once
The difference is the process/protocol boundary alone: no model variance, no coordination.  It also records the
one-off costs (process start to Agent Card served, card discovery) and what each path exposes when it fails.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time

from coord.bench import manifest, run_dir


def q(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


async def run(args: argparse.Namespace) -> None:
    from coord.a2a_link import A2ALink
    from coord.arch_c import InProcessDelegator
    from coord.runtime import open_session
    from coord.scripted import ScriptedProvider
    from coord.specialists import SpecialistEnv
    from coord.supervisor import Supervisor

    rd = run_dir(args.run_id)
    home = rd / "session"
    home.mkdir(parents=True, exist_ok=True)
    os.environ.update(C1_HOME=str(home), C1_WORLD_DB=str(home / "world.db"))
    os.environ.pop("C1_TAPE", None)
    args.scripted = True
    (rd / "manifest.json").write_text(json.dumps(manifest(args.run_id, args) | {"experiment": "E7"}, indent=2))
    session = await open_session(home, provider=ScriptedProvider())
    session.world.reset("B1")
    sup = Supervisor(home, env={"C1_SCRIPTED": "1"})
    t0 = time.perf_counter()
    sup.start("diagnosis")
    ready_s = await sup.ready("diagnosis")
    cold_start_s = round(time.perf_counter() - t0, 3)
    link = A2ALink()
    t1 = time.perf_counter()
    await link.client("diagnosis")
    discovery_ms = round((time.perf_counter() - t1) * 1000, 1)
    local = InProcessDelegator(SpecialistEnv(session.gateway, session.model, session.tokens, session.limits))
    rows = []
    try:
        for i in range(args.n):
            for mode in (("inproc", "a2a") if i % 2 == 0 else ("a2a", "inproc")):
                wf = f"{args.run_id}-{mode}-{i}"
                session.store.create_workflow(workflow_id=wf, run_id=args.run_id, arch="E7", fixture_id="B1", status="RUNNING", started=time.time(), seed=7)
                root = session.tokens.issue_root(subject="alice", invoker="svc.incident-console", actor="agent.coordinator", wf=wf)
                dlg = f"{wf}-d1"
                tok = session.tokens.encode(session.tokens.exchange(root, target="agent.diagnosis", dlg=dlg))
                payload = {"workflow_id": wf, "delegation_id": dlg, "agent": "diagnosis", "objective": "Diagnose the incident.",
                           "authorize_execution": False, "inputs": [],
                           "incident": {"id": "INC-4917", "service": "checkout-api", "environment": "production", "alert": "p95 above 2 s"}}
                d = local if mode == "inproc" else link
                s = time.perf_counter()
                out = await d.delegate("diagnosis", payload, tok, timeout_s=60, message_id=dlg)
                total = round((time.perf_counter() - s) * 1000, 3)
                rows.append({"i": i, "mode": mode, "total_ms": total, "client_ms": out.client_ms, "server_ms": out.out["server_ms"],
                             "req_bytes": out.req_bytes, "resp_bytes": out.resp_bytes, "states": out.states, "kind": out.out["kind"]})
        # failure semantics: what each path tells the caller when the far side is gone
        from coord.a2a_link import DelegationError
        sup.kill("diagnosis")
        try:
            await link.delegate("diagnosis", payload, tok, timeout_s=10, message_id="after-kill")
            failure_a2a = "no error"
        except DelegationError as e:
            failure_a2a = f"{e.kind}: {e.detail[:120]}"
    finally:
        sup.stop_all()
        await link.close()
        await session.close()
    summary = {"n_per_mode": args.n, "cold_start_s": cold_start_s, "card_ready_s": ready_s, "card_discovery_ms": discovery_ms,
               "failure_signal_a2a": failure_a2a, "failure_signal_inproc": "the exception propagates in the caller's own process"}
    for mode in ("inproc", "a2a"):
        xs = [r["total_ms"] for r in rows if r["mode"] == mode]
        sv = [r["server_ms"] for r in rows if r["mode"] == mode]
        summary[mode] = {"median_ms": round(statistics.median(xs), 2), "p90_ms": round(q(xs, 0.9), 2), "max_ms": round(max(xs), 2),
                         "median_agent_ms": round(statistics.median(sv), 2),
                         "median_req_bytes": statistics.median(r["req_bytes"] for r in rows if r["mode"] == mode),
                         "median_resp_bytes": statistics.median(r["resp_bytes"] for r in rows if r["mode"] == mode)}
    summary["a2a_minus_inproc_median_ms"] = round(summary["a2a"]["median_ms"] - summary["inproc"]["median_ms"], 2)
    summary["a2a_states"] = next(r["states"] for r in rows if r["mode"] == "a2a")
    (rd / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (rd / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(prog="coord.exp_boundary")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--n", type=int, default=100)
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
