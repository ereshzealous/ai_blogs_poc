"""The only module that imports F2 (layered_agent_poc). S1 reuses F2's model gateway (with its traffic recorder and
replay), its session and workflow stores, its SQLite helper and its tracing; it does not copy or modify them."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_platform.context.session import SessionStore
from agent_platform.models.gateway import ModelGateway
from agent_platform.orchestration.store import WorkflowStore
from agent_platform.storage import connect
from agent_platform.telemetry.tracing import set_attrs, setup, span

__all__ = ["connect", "span", "set_attrs", "setup_tracing", "make_gateway", "session_store", "workflow_store", "workflow_facts"]


def setup_tracing(run_dir: Path) -> None:
    setup(run_dir, service_name="memory-context-state-poc")


def make_gateway(db_path: Path, *, model: str, embedding_model: str, seed: int, url: str = "http://localhost:11434") -> ModelGateway:
    """One route, no fallback (a silent model switch would change the experiment). Temperature 0, the given seed."""
    return ModelGateway(url=url, routes={"reasoning": {"model": model}, "embeddings": {"model": embedding_model}},
                        profiles={model: {"think": "low", "options": {"temperature": 0, "seed": seed, "num_ctx": 32768}}},
                        db_path=db_path, workflow_budget=10_000_000)


def session_store(db_path: Path) -> SessionStore:
    return SessionStore(db_path)


def workflow_store(db_path: Path) -> WorkflowStore:
    return WorkflowStore(db_path)


def workflow_facts(store: WorkflowStore, workflow_id: str, note: str) -> dict[str, Any]:
    """Workflow state for the prompt: a keyed lookup in the workflow store. Never a similarity search."""
    wf = store.get(workflow_id)
    if wf is None:
        raise KeyError(workflow_id)
    return {"id": wf["id"], "incident_id": wf["incident_id"], "status": wf["status"], "current_step": wf["current_step"], "note": note}
