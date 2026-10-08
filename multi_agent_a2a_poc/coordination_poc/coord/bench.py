"""Benchmark runner: fixtures x architectures x repeats, one workflow at a time (serial: parallel inference on one
machine would distort latency), every run evaluated and measured, one JSON row per run.

    python -m coord.bench matrix --run-id 2026-10-08-dev --fixtures D1,D2,D3,D4 --archs A,B,C --repeats 1
    python -m coord.bench run --run-id try --fixture B1 --arch C --repeat 1
    add --scripted for the deterministic stand-in model (no Ollama)

Layout: runs/<run-id>/{rows.jsonl, manifest.json, session/{platform.db, world.db, traces/, logs/}, tape/}.
The architecture order is rotated per (fixture, repeat) so no architecture always runs first after a world reset.
Resumable: a (fixture, arch, repeat) that already has a row is skipped; a workflow that started but has no row (the
runner died) is re-run under a new id and the gap is recorded as an anomaly, never hidden.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import subprocess
import sys
import time
from importlib import metadata
from pathlib import Path
from typing import Any

import httpx

from coord.util import ROOT, digest, load_config

SEEDS = {1: 7, 2: 11, 3: 13}


def run_dir(run_id: str) -> Path:
    return ROOT / "runs" / run_id


def manifest(run_id: str, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_config("models.yaml")
    tags: Any = None
    try:
        tags = httpx.get(cfg["provider"]["url"].rstrip("/") + "/api/tags", timeout=5).json()
        tags = [m for m in tags.get("models", []) if m["name"] == cfg["profile"]["model"]]
    except Exception as exc:  # noqa: BLE001
        tags = f"unavailable: {exc}"
    pkgs = {p: metadata.version(p) for p in ("a2a-sdk", "mcp", "pydantic", "httpx", "opentelemetry-sdk", "uvicorn", "starlette", "protobuf")}
    files = sorted((ROOT / "coord").glob("*.py")) + sorted((ROOT / "config").glob("*.yaml"))
    return {"run_id": run_id, "argv": sys.argv, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "model_profile": cfg["profile"],
            "model_tags": tags, "scripted": bool(args.scripted), "python": sys.version.split()[0], "platform": platform.platform(),
            "machine": subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip(),
            "packages": pkgs, "a2a_spec": "1.0.1 (protocolVersion 1.0)",
            "source_digest": {str(f.relative_to(ROOT)): digest(f.read_text(), 16) for f in files}}


async def warmup() -> None:
    cfg = load_config("models.yaml")
    async with httpx.AsyncClient(timeout=600) as c:
        await c.post(cfg["provider"]["url"].rstrip("/") + "/api/chat",
                     json={"model": cfg["profile"]["model"], "messages": [{"role": "user", "content": "ok"}], "stream": False,
                           "options": dict(cfg["profile"]["options"], num_predict=1)})


async def matrix(args: argparse.Namespace) -> None:
    from coord.a2a_link import A2ALink
    from coord.arch_c import A2ADelegator
    from coord.evaluate import evaluate, labels
    from coord.metrics import measure
    from coord.runtime import envelope_for, invoke, open_session
    from coord.supervisor import Supervisor
    from coord.world import load_fixture

    rd = run_dir(args.run_id)
    if args.tape == "replay":
        # replay into a scratch copy: the recorded run's directory is never written to
        import shutil
        src_tape = rd / "tape" / "model_tape.jsonl"
        rd = rd / "replay"
        if rd.exists():
            shutil.rmtree(rd)
        (rd / "tape").mkdir(parents=True)
        shutil.copy2(src_tape, rd / "tape" / "model_tape.jsonl")
    home = rd / "session"
    home.mkdir(parents=True, exist_ok=True)
    os.environ["C1_HOME"] = str(home)
    os.environ["C1_WORLD_DB"] = str(home / "world.db")
    child_env: dict[str, str] = {}
    if args.scripted:
        child_env["C1_SCRIPTED"] = "1"
    elif args.tape:
        os.environ["C1_TAPE"] = f"{args.tape}:{rd / 'tape'}"
        child_env["C1_TAPE"] = os.environ["C1_TAPE"]
    overrides = json.loads(args.overrides) if args.overrides else {}
    (rd / "manifest.json").write_text(json.dumps(manifest(args.run_id, args) | {"overrides": overrides}, indent=2))

    provider = None
    if args.scripted:
        from coord.scripted import ScriptedProvider
        provider = ScriptedProvider()
    elif args.tape != "replay":
        await warmup()
    session = await open_session(home, provider=provider)
    sup = None
    archs = args.archs.split(",")
    if "C" in archs:
        sup = Supervisor(home, env=child_env)
        ready = await sup.start_all()
        link = A2ALink()
        session.extras.update(delegator=A2ADelegator(link, sup), link=link)
        print(f"agents ready: {ready}", flush=True)
    rows_path = rd / "rows.jsonl"
    done = set()
    if rows_path.exists():
        for line in rows_path.read_text().splitlines():
            r = json.loads(line)
            done.add((r["fixture"], r["arch"], r["repeat"]))
    lab = labels()
    try:
        for fixture in args.fixtures.split(","):
            for repeat in (args.repeat_list or range(1, args.repeats + 1)):
                k = (args.fixtures.split(",").index(fixture) + repeat) % len(archs)
                for arch in archs[k:] + archs[:k]:
                    if (fixture, arch, repeat) in done:
                        continue
                    wf_id = f"{args.run_id}-{fixture}-{arch}-r{repeat}"
                    anomaly = None
                    if session.store.workflow(wf_id):
                        anomaly = "previous attempt started but produced no row (runner died); re-run under a new id"
                        n = 2
                        while session.store.workflow(f"{wf_id}-x{n}"):
                            n += 1
                        wf_id = f"{wf_id}-x{n}"
                    if sup:
                        for a in sup.agents:
                            await sup.ensure(a)
                    session.world.reset(fixture)
                    spec = load_fixture(fixture)
                    t0 = time.time()
                    view = await invoke(session, envelope_for(spec, wf_id), arch=arch, workflow_id=wf_id, run_id=args.run_id,
                                        fixture_id=fixture, repeat=repeat, seed=SEEDS.get(repeat, 7), overrides=overrides)
                    ev = evaluate(session.store, session.world, wf_id, lab)
                    m = measure(session.store, wf_id, home / "traces")
                    row = {"run_id": args.run_id, "workflow_id": wf_id, "fixture": fixture, "arch": arch, "repeat": repeat,
                           "seed": SEEDS.get(repeat, 7), "split": ev["split"], "subset": ev["subset"], "eval": ev, "metrics": m,
                           "view_status": view.status, "anomaly": anomaly, "wall_started": t0}
                    with open(rows_path, "a") as fh:
                        fh.write(json.dumps(row, default=str) + "\n")
                    print(f"{fixture} {arch} r{repeat}: success={ev['success']} outcome={ev['outcome']} cat={ev['category']} "
                          f"term={m['termination']} {m['latency_ms'] / 1000:.0f}s tok={m['tokens_total']} llm={m['llm_calls']} "
                          f"tools={m['tool_calls']} dup={m['duplicate_tool_calls']} hand={m['handoffs']}", flush=True)
    finally:
        if sup:
            sup.stop_all()
        await session.close()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="coord.bench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("matrix", "run"):
        p = sub.add_parser(name)
        p.add_argument("--run-id", required=True)
        p.add_argument("--scripted", action="store_true")
        p.add_argument("--tape", choices=["record", "replay"], default=None)
        p.add_argument("--overrides", default=None, help="JSON merged into limits.yaml for this run (e.g. the E8 ablation)")
        if name == "matrix":
            p.add_argument("--fixtures", required=True)
            p.add_argument("--archs", default="A,B,C")
            p.add_argument("--repeats", type=int, default=1)
        else:
            p.add_argument("--fixture", required=True)
            p.add_argument("--arch", required=True)
            p.add_argument("--repeat", type=int, default=1)
    args = ap.parse_args(argv)
    args.repeat_list = None
    if args.cmd == "run":
        args.fixtures, args.archs, args.repeats, args.repeat_list = args.fixture, args.arch, args.repeat, [args.repeat]
    asyncio.run(matrix(args))


if __name__ == "__main__":
    main()
