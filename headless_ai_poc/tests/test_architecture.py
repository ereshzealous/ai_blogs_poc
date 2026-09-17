"""Structural quality gates: who may import what, and what channel code may not contain."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "headless_ai_platform"
CHANNEL_FILES = sorted((PKG / "channels").glob("*.py")) + [PKG / "static" / "console.js"]
# Things only the platform may own: policy rules, role names, model names, prompts, workflow step order.
OWNED_BY_PLATFORM = [r"incident-commander", r"REQUIRE_APPROVAL", r"P4-", r"gpt-oss|qwen3|ollama", r"You are an?\b",
                     r"system_prompt", r"rollback_release", r"production"]


def test_import_contracts_hold():
    lint = subprocess.run([str(Path(sys.executable).parent / "lint-imports")], cwd=ROOT, capture_output=True, text=True)
    assert lint.returncode == 0, lint.stdout[-2000:]
    assert "5 kept, 0 broken" in lint.stdout


def test_channel_code_holds_no_policy_prompt_model_or_workflow_rules():
    hits = []
    for f in CHANNEL_FILES:
        text = f.read_text(encoding="utf-8")
        hits += [f"{f.name}: {p}" for p in OWNED_BY_PLATFORM if re.search(p, text)]
    assert hits == []


def test_only_the_platform_adapter_imports_part_2():
    importers = set()
    for f in PKG.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            if any(n.split(".")[0] in {"agent_platform", "mock_enterprise", "traffic"} for n in names):
                importers.add(str(f.relative_to(PKG)))
                assert all(n in {"agent_platform.service", "agent_platform.contracts", "agent_platform.identity.principals"}
                           for n in names if n.startswith("agent_platform")), (f, names)
    assert importers == {"platform/layered.py"}


def test_part_2_is_used_as_installed_not_copied():
    assert not (ROOT / "src" / "agent_platform").exists() and not (ROOT / "agent_platform").exists()
    import agent_platform

    part2 = Path(agent_platform.__file__).resolve().parents[1]
    assert (part2 / "config" / "policies.yaml").exists() and part2 != ROOT
