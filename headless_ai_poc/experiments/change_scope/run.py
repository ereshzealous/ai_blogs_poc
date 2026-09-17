"""H3 · change scope. Apply each requirement change to a scratch tree that mirrors the monorepo and measure it.

    uv run python -m experiments.change_scope.run [--out FILE]

For each patch: it must apply cleanly and compile; touched modules must import; files and lines are counted and each
file is classified as core, adapter, renderer, config or baseline. For the headless patches the import contracts are
re-run on the patched tree, and the patched system is started (model answers replayed) to read what every channel
now gets. For the baseline patches each copy's approval rule is evaluated.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from agent_platform.config import ROOT as LAYERED

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def numstat(patch: Path) -> dict:
    added = removed = 0
    files: list[str] = []
    for line in patch.read_text().splitlines():
        if line.startswith("+++ "):
            files.append(line[4:].split("\t")[0].removeprefix("b/"))
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return {"added": added, "removed": removed, "files": files}


def classify(path: str, core: list[str]) -> str:
    if any(path.startswith(c) for c in core):
        return "core"
    if path.startswith("layered/config/"):
        return "platform-config"
    if path.startswith("headless/config/"):
        return "channel-config"
    if "/renderers/" in path:
        return "renderer"
    if "/channels/" in path or path.endswith("server.py"):
        return "adapter"
    if path.startswith("headless/baseline/"):
        return "baseline-app"
    return "other"


def scratch(tmp: Path) -> Path:
    ignore = shutil.ignore_patterns("__pycache__", "*.db", "*.db-*")
    for d in ("agent_platform", "config", "mock_enterprise", "traffic"):
        shutil.copytree(LAYERED / d, tmp / "layered" / d, ignore=ignore)
    (tmp / "layered" / "var").mkdir()
    # Our own copy of the runbook index, so a fresh clone needs neither Ollama nor a built index in the layered POC.
    shutil.copy(ROOT / "data" / "knowledge_index.json", tmp / "layered" / "var" / "knowledge_index.json")
    for d in ("src", "config", "baseline", "experiments"):
        shutil.copytree(ROOT / d, tmp / "headless" / d, ignore=ignore)
    shutil.copy(ROOT / ".importlinter", tmp / "headless" / ".importlinter")
    return tmp


def env_for(tree: Path) -> dict[str, str]:
    path = os.pathsep.join(str(p) for p in (tree / "headless" / "src", tree / "headless", tree / "layered"))
    keep = {k: v for k, v in os.environ.items() if not k.startswith(("LAP_", "HAI_"))}
    return {**keep, "PYTHONPATH": path, "LAP_RUNS_DIR": str(tree / "traces"),
            "LAP_KNOWLEDGE_INDEX": str(tree / "layered" / "var" / "knowledge_index.json")}


def probe(tree: Path, *args: str) -> dict:
    out = subprocess.run([sys.executable, "-m", "experiments.change_scope.probe", *args], cwd=tree / "headless",
                         env=env_for(tree), capture_output=True, text=True, timeout=600)
    if out.returncode:
        return {"error": out.stderr[-1500:]}
    return json.loads(out.stdout.strip().splitlines()[-1])


def governance_copies(tree: Path) -> dict[str, int]:
    """How many independently maintained approval rules exist: one per baseline app, one per platform policy rule."""
    baseline = 0
    for f in (tree / "headless" / "baseline" / "channel_coupled").glob("*_assistant.py"):
        tree_ = ast.parse(f.read_text())
        baseline += sum(isinstance(n, ast.FunctionDef) and n.name == "approval_role" for n in ast.walk(tree_))
    rules = yaml.safe_load((tree / "layered" / "config" / "policies.yaml").read_text())["rules"]
    headless_channels = sum(1 for f in (tree / "headless" / "src" / "headless_ai_platform" / "channels").glob("*.py")
                            if "approval_role" in f.read_text() or "approver_role" in f.read_text())
    return {"baseline_approval_rules": baseline,
            "platform_approval_rules": sum(1 for r in rules if r.get("approver_role")),
            "headless_channel_approval_rules": headless_channels}


def apply(tree: Path, patch: Path) -> dict:
    check = subprocess.run(["patch", "-p1", "--dry-run", "-i", str(patch)], cwd=tree, capture_output=True, text=True)
    if check.returncode:
        return {"applies": False, "error": check.stdout + check.stderr}
    subprocess.run(["patch", "-p1", "-s", "-i", str(patch)], cwd=tree, check=True)
    files = numstat(patch)["files"]
    py = [str(tree / f) for f in files if f.endswith(".py")]
    compiled = subprocess.run([sys.executable, "-m", "py_compile", *py], capture_output=True).returncode == 0 if py else True
    modules = []
    for f in files:
        if f.endswith(".py"):
            rel = f.removeprefix("headless/src/").removeprefix("headless/").removeprefix("layered/")
            modules.append(rel[:-3].replace("/", "."))
    imported = subprocess.run([sys.executable, "-c", "; ".join(f"import {m}" for m in modules) or "pass"],
                              cwd=tree / "headless", env=env_for(tree), capture_output=True, text=True)
    return {"applies": True, "compiles": compiled, "imports": imported.returncode == 0,
            "import_error": imported.stderr[-400:] if imported.returncode else None}


def lint(tree: Path) -> bool:
    exe = Path(sys.executable).parent / "lint-imports"
    return subprocess.run([str(exe)], cwd=tree / "headless", env=env_for(tree), capture_output=True).returncode == 0


def measure() -> dict:
    spec = yaml.safe_load((HERE / "changes.yaml").read_text())
    core = spec["core"]
    results = []
    with tempfile.TemporaryDirectory(prefix="hai-scope-") as tmp:
        before = governance_copies(scratch(Path(tmp) / "before"))
    for change in spec["changes"]:
        row = {"id": change["id"], "title": change["title"], "controlled": bool(change.get("controlled"))}
        for side in ("baseline", "headless"):
            if side not in change:
                continue
            c = change[side]
            patch = HERE / "patches" / c["patch"]
            stat = numstat(patch)
            kinds: dict[str, int] = {}
            for f in stat["files"]:
                kinds[classify(f, core)] = kinds.get(classify(f, core), 0) + 1
            with tempfile.TemporaryDirectory(prefix="hai-scope-") as tmp:
                tree = scratch(Path(tmp))
                verified = apply(tree, patch)
                facts: dict = {}
                if verified.get("applies"):
                    facts["governance_copies"] = governance_copies(tree)
                    if side == "headless":
                        verified["contracts_kept"] = lint(tree)
                        channels = ["slack", "web", "cli", "rest"] + (["teams"] if change["id"] == "add-channel" else [])
                        facts["runtime"] = probe(tree, "headless", ",".join(channels))
                    else:
                        facts["runtime"] = {"approval_role": probe(tree, "baseline")}
            row[side] = {"patch": c["patch"], "files": len(stat["files"]), "added": stat["added"],
                         "removed": stat["removed"], "file_list": stat["files"], "kinds": kinds,
                         "core_files": kinds.get("core", 0), "concerns": c["concerns"], "notes": c["notes"],
                         **verified, **facts}
        results.append(row)
    return {"governance_copies_before": before, "changes": results,
            "note": "Illustrative, hand-written patches; not a benchmark. Concern labels are a human reading."}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(ROOT / "runs" / "change-scope.json"))
    args = p.parse_args()
    data = measure()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(data, indent=2))
    for r in data["changes"]:
        for side in ("baseline", "headless"):
            if side in r:
                s = r[side]
                print(f"{r['id']:<20} {side:<9} files={s['files']} +{s['added']}/-{s['removed']} core={s['core_files']} "
                      f"concerns={len(s['concerns'])} applies={s.get('applies')} imports={s.get('imports')} "
                      f"contracts={s.get('contracts_kept', '-')} runtime={json.dumps(s.get('runtime'))[:160]}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
