"""Blindness and boundaries, checked on the source: only the evaluator reads ground truth; architectures never touch
the world directly (only through the gateway); the coordinator's module never calls the gateway."""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "coord"


def test_only_evaluator_reads_groundtruth():
    # freeze.py hashes the labels file's bytes for FROZEN.sha256; it is post-hoc tooling, never part of a run
    offenders = [p.name for p in SRC.glob("*.py") if "groundtruth" in p.read_text() and p.name not in ("evaluate.py", "freeze.py")]
    assert offenders == []


def test_architectures_reach_systems_only_through_the_gateway():
    for name in ("arch_a.py", "arch_b.py", "arch_c.py", "specialists.py", "prompts.py"):
        text = (SRC / name).read_text()
        assert "World(" not in text and "coord.world import World" not in text, name
        assert "mcp_servers" not in text and "McpPool" not in text, name


def test_coordinator_holds_no_tool_path():
    text = (SRC / "arch_c.py").read_text()
    assert "gateway.call" not in text and "GatewayTools" not in text
