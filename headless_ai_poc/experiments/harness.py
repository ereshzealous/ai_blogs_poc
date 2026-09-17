"""Shared set-up for tests and experiments: fresh state and a source of model answers."""

from __future__ import annotations

import os
from pathlib import Path

from agent_platform.config import ROOT as LAYERED_ROOT

DEMO_TAPE = LAYERED_ROOT / "traffic" / "recordings" / "demo-gpt-oss_20b"


def reset_enterprise(db: Path) -> None:
    from mock_enterprise.world import World

    World(db).reset()


def replay_tape(directory: Path, workflows: int, source: Path = DEMO_TAPE) -> Path:
    """Part 2's recorded model answers for one INC-4917 workflow, repeated for `workflows` sequential workflows."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "chat.jsonl").write_text((source / "chat.jsonl").read_text(encoding="utf-8") * workflows, encoding="utf-8")
    (directory / "embed.jsonl").write_text((source / "embed.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    return directory


def prepare_env(base: Path, *, replay_workflows: int | None = None, record_to: Path | None = None,
                replay_from: Path | None = None) -> dict[str, str]:
    """Fresh databases under `base`; model answers replayed, recorded, or (neither given) live from Ollama."""
    base.mkdir(parents=True, exist_ok=True)
    env = {"LAP_PLATFORM_DB": str(base / "platform.db"), "LAP_ENTERPRISE_DB": str(base / "enterprise.db"),
           "HAI_HEADLESS_DB": str(base / "headless.db")}
    reset_enterprise(base / "enterprise.db")
    if replay_from is not None:
        env["LAP_MODEL_TRAFFIC"] = f"replay:{replay_from}"
    elif replay_workflows:
        env["LAP_MODEL_TRAFFIC"] = f"replay:{replay_tape(base / 'tape', replay_workflows)}"
    elif record_to is not None:
        env["LAP_MODEL_TRAFFIC"] = f"record:{record_to}"
    else:
        os.environ.pop("LAP_MODEL_TRAFFIC", None)
    return env
