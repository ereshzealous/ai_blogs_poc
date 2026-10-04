"""L13: six logical layers, one process. A layer is a responsibility boundary, not a deployment boundary.

The POC would be easy to misread as "six layers means six services". These tests pin the opposite: the platform
starts no server of its own, holds no per-layer address or port, and the recorded scenarios ran in one process until
a SIGKILL forced a second one. The MCP servers are separate processes because MCP's stdio transport says so — that
is a transport boundary inside the tool layer, not a service per layer.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "layered_platform"
RUNS = ROOT / "runs"


def published_run() -> Path:
    return RUNS / (RUNS / "PUBLISHED").read_text().strip()


def test_the_platform_starts_no_service_of_its_own():
    """No web server, no bind, no listen anywhere in the platform packages."""
    servers = ("fastapi", "flask", "uvicorn", "aiohttp.web", "http.server", "socketserver", "grpc")
    bad = []
    for path in sorted(PKG.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                bad += [f"{path.name} imports {a.name}" for a in node.names if a.name.startswith(servers)]
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(servers):
                bad.append(f"{path.name} imports {node.module}")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("bind", "listen"):
                bad.append(f"{path.name}:{node.lineno} {node.func.attr}()")
    assert not bad, f"the platform starts a service of its own, so a layer could be mistaken for a deployment: {bad}"


def test_no_layer_has_its_own_address():
    """A per-layer host, port or base URL would mean the layers talk over a network. Only the model provider has one."""
    bad = []
    for path in sorted(PKG.rglob("*.py")):
        if path.parts[-2:] == ("models", "ollama.py"):
            continue  # the provider adapter holds the Ollama base URL; that is one external dependency, not a layer hop
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if "http://" in line or "https://" in line:
                bad.append(f"{path.relative_to(ROOT)}:{i}")
    assert not bad, f"a layer carries a network address: {bad}"


# One span name per layer, as the platform emits them.  Policy is cross-cutting but still a boundary crossing.
LAYER_SPANS = {
    "experience": "request",
    "orchestration": "workflow.step",
    "runtime": "invoke_agent",
    "model services": "chat",
    "tools and actions": "execute_tool",
    "policy": "policy.evaluate",
}


def spans_of(run: Path, scenario: str) -> list[dict]:
    return [json.loads(line) for line in (run / "raw" / "traces.jsonl").read_text().splitlines()
            if line.strip() and json.loads(line).get("scenario") == scenario]


def test_every_layer_runs_inside_one_process():
    """L13: one OS process carries spans from all six layers. Six responsibilities, not six services."""
    run = published_run()
    if not run.exists():
        pytest.skip(f"{run.name} is not present")
    checked = 0
    for d in sorted((run / "scenarios").glob("E1-layered-*")):
        by_pid: dict[int, set[str]] = {}
        for span in spans_of(run, d.name):
            by_pid.setdefault(span["pid"], set()).add(span["name"])
        covered = {pid: {layer for layer, name in LAYER_SPANS.items() if name in names} for pid, names in by_pid.items()}
        best = max(covered.values(), key=len) if covered else set()
        assert best == set(LAYER_SPANS), f"{d.name}: no single process covered every layer; best was {sorted(best)}"
        checked += 1
    assert checked, "no layered E1 scenario found to check"


@pytest.mark.parametrize("arch", ["layered", "monolith"])
def test_processes_are_explained_by_harness_phases_not_by_layers(arch):
    """A scenario's process count equals the harness invocations it needed, plus a restart for each SIGKILL.

    The layered platform uses one more process than the monolith in the paired scenarios, and that extra process is
    the separate `approve` invocation — which is evidence for durable approval state (L10), not a layer boundary.
    """
    run = published_run()
    if not run.exists():
        pytest.skip(f"{run.name} is not present")
    for d in sorted((run / "scenarios").glob(f"*-{arch}-*")):
        score = json.loads((d / "score.json").read_text())
        phases = [json.loads(line) for line in (d / "phases_harness.jsonl").read_text().splitlines() if line.strip()]
        pids = {ph["pid"] for ph in phases if ph.get("pid")}
        assert score["processes"] == len(pids), f"{d.name}: score says {score['processes']} processes, the harness log shows {len(pids)}"
        assert len(phases) >= 1 + score.get("sigkills", 0), f"{d.name}: fewer invocations than kills"


def test_the_six_layers_are_one_package():
    """Six responsibilities, one importable unit, one database file — the shape L13 claims."""
    layers = {"experience", "orchestration", "runtime", "context", "memory", "tools", "models"}
    present = {p.name for p in PKG.iterdir() if p.is_dir() and not p.name.startswith("__")}
    assert layers <= present, f"missing layer packages: {sorted(layers - present)}"
    assert (PKG / "service.py").exists(), "no composition root: something has to wire the layers in one process"
