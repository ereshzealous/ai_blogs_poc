"""Record a complete run: freeze hashes, capture the environment, run the tests, run every scenario live, run the
governance probes, build summary.json and verify the evidence.

    uv run python scripts/record_run.py [--run-id 2026-09-28-recorded] [--skip-model-tests]
    uv run python scripts/record_run.py --replay-from runs/<id>  --run-id <id>-replay     (no model is called)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx

POC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))

FROZEN = {
    "experiment_plan": "experiments/preregistration/experiment_plan.yaml",
    "scenario": "simulated_enterprise/data/inc4917.yaml",
    "runbooks": "simulated_enterprise/data/runbooks",
    "memory_seed": "simulated_enterprise/data/memory_seed.yaml",
    "policy": "config/policies.yaml",
    "capabilities": "config/capabilities.yaml",
    "model_config": "config/models.yaml",
    "prompts": ["monolith/incident_agent.py", "layered_platform/orchestration/agents.py", "layered_platform/runtime/agent_loop.py", "layered_platform/context/assembler.py"],
    "scoring": ["layered_platform/evals/checks.py", "experiments/scorers"],
    "change_patches": "experiments/changes",
    "mcp_servers": "mcp_servers/servers.py",
}
SKIP = {".venv", "var", "runs", "__pycache__", ".pytest_cache"}


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sha_paths(paths: str | list[str]) -> str:
    h = hashlib.sha256()
    for rel in [paths] if isinstance(paths, str) else paths:
        p = POC / rel
        files = sorted(x for x in p.rglob("*") if x.is_file() and "__pycache__" not in x.parts) if p.is_dir() else [p]
        for f in files:
            h.update(str(f.relative_to(POC)).encode() + b"\0" + f.read_bytes())
    return h.hexdigest()


def source_hashes() -> dict[str, str]:
    out = {}
    for f in sorted(POC.rglob("*")):
        if f.is_file() and not (set(f.relative_to(POC).parts) & SKIP) and f.suffix in (".py", ".yaml", ".md", ".patch", ".toml", ".lock"):
            out[str(f.relative_to(POC))] = sha_file(f)
    return out


async def tool_schemas() -> dict:
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters
    import tempfile

    from simulated_enterprise.world import World

    out = {}
    with tempfile.TemporaryDirectory() as d:
        World(Path(d) / "w.db").reset()
        env = dict(os.environ, PYTHONPATH=str(POC), F2_WORLD_DB=str(Path(d) / "w.db"))
        for server in ("itsm", "observability", "deploy", "deploy_v2"):
            async with Client(StdioServerParameters(command=sys.executable, args=["-m", "mcp_servers", server], env=env, cwd=str(POC))) as c:
                tools = (await c.list_tools()).tools
                out[server] = {t.name: {"description": t.description, "input_schema": t.input_schema} for t in tools}
    return out


def environment() -> dict:
    env = {"os": platform.platform(), "machine": platform.machine(), "python": sys.version.split()[0],
           "uv": subprocess.run(["uv", "--version"], capture_output=True, text=True).stdout.strip(),
           "cpu": subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip(),
           "memory_gb": round(int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout.strip() or 0) / 2**30, 1)}
    try:
        import importlib.metadata as md

        env["packages"] = {p: md.version(p) for p in ("mcp", "httpx", "pydantic", "opentelemetry-sdk", "pyyaml", "pytest")}
    except Exception:  # pragma: no cover
        pass
    try:
        env["ollama_version"] = httpx.get("http://localhost:11434/api/version", timeout=3).json().get("version")
        tags = httpx.get("http://localhost:11434/api/tags", timeout=3).json()["models"]
        env["ollama_models"] = {m["name"]: {"digest": m["digest"], "size": m["size"], "quantization": m.get("details", {}).get("quantization_level"),
                                            "parameter_size": m.get("details", {}).get("parameter_size")} for m in tags}
    except Exception as exc:
        env["ollama_error"] = str(exc)
    return env


def run_tests(run_dir: Path, skip_model: bool) -> dict:
    junit = run_dir / "tests.junit.xml"
    args = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", f"--junitxml={junit}"] + (["-m", "not model"] if skip_model else [])
    t0 = time.time()
    proc = subprocess.run(args, cwd=POC, capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=str(POC)))
    (run_dir / "logs").mkdir(exist_ok=True)
    (run_dir / "logs" / "pytest.log").write_text(proc.stdout + proc.stderr)
    cases = []
    for tc in ET.parse(junit).getroot().iter("testcase"):
        status = "failed" if tc.find("failure") is not None or tc.find("error") is not None else ("skipped" if tc.find("skipped") is not None else "passed")
        path = tc.get("classname", "").replace(".", "/")
        cat = path.split("/")[1] if path.startswith("tests/") else "other"
        cases.append({"id": f"{tc.get('classname')}::{tc.get('name')}", "category": cat, "status": status, "time_s": float(tc.get("time", 0))})
    model_ids = {c["id"] for c in cases if c["category"] == "model"}
    by_cat: dict[str, dict[str, int]] = {}
    for c in cases:
        by_cat.setdefault(c["category"], {"passed": 0, "failed": 0, "skipped": 0})[c["status"]] += 1
    return {"total": len(cases), "passed": sum(c["status"] == "passed" for c in cases), "failed": sum(c["status"] == "failed" for c in cases),
            "skipped": sum(c["status"] == "skipped" for c in cases), "by_category": by_cat, "require_local_models": len(model_ids),
            "returncode": proc.returncode, "wall_s": round(time.time() - t0, 1), "cases": cases}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("%Y-%m-%d") + "-recorded")
    ap.add_argument("--replay-from")
    ap.add_argument("--skip-model-tests", action="store_true")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    run_dir = POC / "runs" / a.run_id
    if run_dir.exists():
        raise SystemExit(f"{run_dir} exists; runs are never overwritten")
    run_dir.mkdir(parents=True)
    mode = "replay" if a.replay_from else "record"
    started = datetime.now(timezone.utc).isoformat()
    print(f"run {a.run_id} ({mode}) -> {run_dir}", flush=True)

    snap = run_dir / "config_snapshot"
    for rel in ("config", "experiments/preregistration", "experiments/changes", "simulated_enterprise/data"):
        shutil.copytree(POC / rel, snap / rel)
    hashes = {k: sha_paths(v) for k, v in FROZEN.items()}
    hashes["experiment_plan"] = sha_file(POC / FROZEN["experiment_plan"])
    schemas = asyncio.run(tool_schemas())
    (snap / "tool_schemas.json").write_text(json.dumps(schemas, indent=1))
    hashes["tool_schemas"] = hashlib.sha256(json.dumps(schemas, sort_keys=True).encode()).hexdigest()
    src = source_hashes()
    (run_dir / "source_hashes.json").write_text(json.dumps(src, indent=1))
    hashes["source_tree"] = hashlib.sha256(json.dumps(src, sort_keys=True).encode()).hexdigest()
    env = environment()
    (run_dir / "environment.json").write_text(json.dumps(env, indent=1))

    print("tests ...", flush=True)
    tests = run_tests(run_dir, a.skip_model_tests or bool(a.replay_from))
    (run_dir / "tests.json").write_text(json.dumps(tests, indent=1))
    print(f"  {tests['passed']}/{tests['total']} passed, {tests['failed']} failed, {tests['skipped']} skipped", flush=True)

    print("scenarios ...", flush=True)
    harness = [sys.executable, "-m", "experiments.runners.harness", "--run-dir", str(run_dir)] + (["--replay-from", str(Path(a.replay_from).resolve())] if a.replay_from else []) + (["--only", a.only] if a.only else [])
    t0 = time.time()
    subprocess.run(harness, cwd=POC, check=True, env=dict(os.environ, PYTHONPATH=str(POC)))
    harness_wall = round(time.time() - t0, 1)
    subprocess.run([sys.executable, "-m", "experiments.runners.probes", "--out", str(run_dir / "experiments" / "E6_probes.json")], cwd=POC, check=True,
                   env=dict(os.environ, PYTHONPATH=str(POC)))

    import yaml

    plan = yaml.safe_load((POC / FROZEN["experiment_plan"]).read_text())
    manifest = {
        "run_id": a.run_id, "mode": mode, "replay_of": a.replay_from and Path(a.replay_from).name,
        "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(), "harness_wall_s": harness_wall,
        "git": {"commit": None, "note": "the F2 folder is not a git repository; source state is pinned by source_hashes.json (hashes.source_tree)"},
        "platform": env["os"], "machine": env["machine"], "python": env["python"], "cpu": env.get("cpu"), "memory_gb": env.get("memory_gb"),
        "ollama_version": env.get("ollama_version"),
        "models": {k: {**v, "digest": env.get("ollama_models", {}).get(v["name"], {}).get("digest")} for k, v in plan["models"].items()},
        "temperature": 0, "seeds": plan["seeds"], "mcp_sdk": env.get("packages", {}).get("mcp"),
        "mcp_servers": {"itsm": "1.0.0", "observability": "1.0.0", "deploy": "1.0.0", "deploy_v2": "2.0.0"},
        "hashes": hashes,
        "tests": {k: tests[k] for k in ("total", "passed", "failed", "skipped", "require_local_models", "returncode")},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    subprocess.run([sys.executable, "scripts/build_summary.py", str(run_dir)], cwd=POC, check=True, env=dict(os.environ, PYTHONPATH=str(POC)))
    subprocess.run([sys.executable, "scripts/verify_evidence.py", str(run_dir)], cwd=POC, env=dict(os.environ, PYTHONPATH=str(POC)))
    print(f"done: {run_dir}", flush=True)


if __name__ == "__main__":
    main()
