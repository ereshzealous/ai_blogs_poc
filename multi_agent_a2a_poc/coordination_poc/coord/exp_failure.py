"""E6: kill an independent agent's OS process during a real architecture-C workflow, and watch who recovers what.

    python -m coord.exp_failure --run-id <id> [--repeats 3] [--scripted]

Variants (fixture B1, INC-4917, the real model unless --scripted):
  K1      SIGKILL the diagnosis agent while its A2A task is in flight (after its first model call is recorded).
  K2      SIGKILL the remediation agent right after its production write executed, before it returns its artifact.
  K2-neg  K2 with the workflow-owned idempotency key switched off (negative control).

A watcher polls the shared ledgers and pulls the trigger from outside, the way an OOM-kill or a node loss would.
Recovery is the coordinator runtime's ordinary path: classify the failure, restart the agent, probe the old task id
with GetTask, retry the same delegation (same delegation id, new A2A task).  Everything is read back from ledgers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from typing import Any

from coord.bench import SEEDS, run_dir

VARIANTS = {"K1": ("diagnosis", "workflow"), "K2": ("remediation", "workflow"), "K2-neg": ("remediation", "off")}


async def watch(session: Any, sup: Any, wf: str, variant: str, fired: dict[str, Any]) -> None:
    agent = VARIANTS[variant][0]
    while True:
        await asyncio.sleep(0.05)
        if variant == "K1":
            row = session.store.one("SELECT d.delegation_id FROM delegations d JOIN model_usage u ON u.delegation_id=d.delegation_id "
                                    "WHERE d.workflow_id=? AND d.agent='diagnosis' AND d.state='DISPATCHED' LIMIT 1", (wf,))
        else:
            row = session.store.one("SELECT seq FROM gateway_calls WHERE workflow_id=? AND component='agent.remediation' AND kind='write' "
                                    "AND outcome='ok' LIMIT 1", (wf,))
        if row:
            fired.update(at=time.time(), agent=agent, pid=sup.kill(agent), trigger=dict(row))
            return


async def run(args: argparse.Namespace) -> None:
    from coord.a2a_link import A2ALink
    from coord.arch_c import A2ADelegator
    from coord.bench import manifest, warmup
    from coord.evaluate import evaluate
    from coord.metrics import measure
    from coord.runtime import envelope_for, invoke, open_session
    from coord.supervisor import Supervisor
    from coord.world import load_fixture

    rd = run_dir(args.run_id)
    home = rd / "session"
    home.mkdir(parents=True, exist_ok=True)
    os.environ.update(C1_HOME=str(home), C1_WORLD_DB=str(home / "world.db"))
    child_env = {"C1_SCRIPTED": "1"} if args.scripted else {}
    if not args.scripted:
        os.environ["C1_TAPE"] = f"record:{rd / 'tape'}"
        child_env["C1_TAPE"] = os.environ["C1_TAPE"]
        await warmup()
    (rd / "manifest.json").write_text(json.dumps(manifest(args.run_id, args) | {"experiment": "E6"}, indent=2))
    provider = None
    if args.scripted:
        from coord.scripted import ScriptedProvider
        provider = ScriptedProvider()
    session = await open_session(home, provider=provider)
    sup = Supervisor(home, env=child_env)
    await sup.start_all()
    link = A2ALink()
    session.extras.update(delegator=A2ADelegator(link, sup), link=link)
    out = rd / "rows.jsonl"
    try:
        for variant in args.variants.split(","):
            for repeat in range(1, args.repeats + 1):
                wf = f"{args.run_id}-{variant}-r{repeat}"
                if session.store.workflow(wf):
                    continue
                for a in sup.agents:
                    await sup.ensure(a)
                session.world.reset("B1")
                fired: dict[str, Any] = {}
                watcher = asyncio.create_task(watch(session, sup, wf, variant, fired))
                view = await invoke(session, envelope_for(load_fixture("B1"), wf), arch="C", workflow_id=wf, run_id=args.run_id, fixture_id="B1",
                                    repeat=repeat, seed=SEEDS[repeat], overrides={"idempotency": VARIANTS[variant][1]})
                watcher.cancel()
                ev = evaluate(session.store, session.world, wf)
                m = measure(session.store, wf, home / "traces")
                dels = session.store.rows("SELECT delegation_id, attempt, agent, state, error, a2a_task_id, a2a_state, client_ms, server_ms "
                                          "FROM delegations WHERE workflow_id=? ORDER BY started", (wf,))
                retries = session.store.rows("SELECT detail FROM steps WHERE workflow_id=? AND kind='delegation_retry'", (wf,))
                writes = [c for c in session.store.calls(wf) if c["kind"] == "write"]
                row = {"run_id": args.run_id, "workflow_id": wf, "variant": variant, "repeat": repeat, "seed": SEEDS[repeat],
                       "kill": fired or None, "killed": bool(fired), "eval": ev, "metrics": m, "delegations": dels,
                       "retries": [json.loads(r["detail"]) for r in retries], "gateway_writes": [
                           {k: w[k] for k in ("capability", "args", "outcome", "idem_key", "component")} for w in writes],
                       "world_executions": ev["world_executions"], "world_idempotent_replays": ev["world_idempotent_replays"],
                       "outcome": view.verdict["outcome"], "termination": view.verdict["termination"]}
                with open(out, "a") as fh:
                    fh.write(json.dumps(row, default=str) + "\n")
                print(f"{variant} r{repeat}: killed={bool(fired)} outcome={row['outcome']} success={ev['success']} "
                      f"attempts={len(dels)} executions={ev['world_executions']} replays={ev['world_idempotent_replays']} "
                      f"trace_complete={m['trace'].get('complete')}", flush=True)
    finally:
        sup.stop_all()
        await session.close()


def main() -> None:
    ap = argparse.ArgumentParser(prog="coord.exp_failure")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--variants", default="K1,K2,K2-neg")
    ap.add_argument("--scripted", action="store_true")
    ap.add_argument("--tape", default=None)
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
