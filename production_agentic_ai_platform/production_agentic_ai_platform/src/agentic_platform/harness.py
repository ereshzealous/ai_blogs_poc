"""Experiment harness: an isolated directory per experiment (own world, own platform state, own copy of the control plane,
own evidence), and the out-of-band actors a proof needs (the human approver, the control-plane operator, a raw MCP client
that bypasses the platform)."""

from __future__ import annotations

import json
import secrets
import shutil
from pathlib import Path

from agentic_platform import control_plane as cpm
from agentic_platform.approval import ApprovalService
from agentic_platform.store import Store
from simulated_systems.world import SEED, World

ROOT = Path(__file__).resolve().parents[2]


def new_keys() -> dict[str, str]:
    return {k: secrets.token_hex(24) for k in ("control_plane", "capability", "approval", "attestor")}


def prepare(exp_dir: Path, keys: dict[str, str], *, inject: bool = False) -> Path:
    exp_dir = Path(exp_dir)
    if exp_dir.exists():
        shutil.rmtree(exp_dir)
    exp_dir.mkdir(parents=True)
    cp = exp_dir / "control-plane"
    shutil.copytree(ROOT / "config", cp)
    cpm.publish(cp, keys["control_plane"].encode())
    World.reset(exp_dir / "world.db", inject=inject)
    Store.reset(exp_dir / "platform.db", SEED)
    (exp_dir / ".keys.json").write_text(json.dumps(keys))
    return cp


def approver(exp_dir: Path, keys: dict[str, str]) -> ApprovalService:
    b = cpm.load(Path(exp_dir) / "control-plane", keys["control_plane"].encode())
    return ApprovalService(Store(Path(exp_dir) / "platform.db"), keys["approval"].encode(), b.policy, b.doc["identity"]["users"])
