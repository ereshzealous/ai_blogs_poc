"""PlatformService: the facade every experience calls, and the composition root that wires the layers together.

This is the only module that constructs implementations of more than one layer.  An experience (CLI, chat, API) gets
a PlatformService and speaks the contracts in contracts.py; it never sees a model, a tool or a database.
"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from layered_platform.config import load
from layered_platform.context.assembler import ContextAssembler
from layered_platform.context.knowledge import KnowledgeBase
from layered_platform.contracts import ApprovalDecision, StartRequest, WorkflowView
from layered_platform.memory.store import MemoryStore
from layered_platform.models.gateway import ModelGateway
from layered_platform.orchestration.incident_workflow import FIRST_STEP, IncidentWorkflow
from layered_platform.policy.approvals import Approvals
from layered_platform.policy.engine import PolicyEngine
from layered_platform.policy.identity import Directory
from layered_platform.runtime.checkpoints import CheckpointStore
from layered_platform.runtime.executor import DurableExecutor
from layered_platform.storage.db import connect
from layered_platform.telemetry import tracing
from layered_platform.tools.gateway import ActionGateway
from layered_platform.tools.mcp_client import McpClientPool
from layered_platform.tools.registry import Registry


class PlatformService:
    def __init__(self, workdir: Path, world_db: str):
        self.workdir = workdir
        workdir.mkdir(parents=True, exist_ok=True)
        tracing.setup(workdir / "traces")
        self.db = connect(workdir / "platform.db")
        ctx_cfg = load("context.yaml")
        self.directory = Directory()
        self.registry = Registry()
        self.approvals = Approvals(self.db, self.directory)
        self.mcp = McpClientPool(self.registry.servers(), world_db)
        self.gateway = ActionGateway(self.db, self.registry, PolicyEngine(), self.approvals, self.mcp)
        self.models = ModelGateway(self.db)
        self.memory = MemoryStore(self.db, ctx_cfg["memory"]["seed"], ctx_cfg["memory"]["ttl_days"])
        self.context = ContextAssembler(KnowledgeBase(ctx_cfg["knowledge"]["runbooks_dir"]), self.memory,
                                        ctx_cfg["knowledge"]["top_k"], ctx_cfg["context_budget_chars"])
        self.store = CheckpointStore(self.db)
        self.workflow = IncidentWorkflow(self.gateway, self.models, self.context, self.approvals)
        self.executor = DurableExecutor(self.store)

    @classmethod
    @asynccontextmanager
    async def open(cls, workdir: str | Path, world_db: str | None = None) -> AsyncIterator[PlatformService]:
        svc = cls(Path(workdir), world_db or os.environ.get("F2_WORLD_DB", "world.db"))
        await svc.mcp.start()
        try:
            yield svc
        finally:
            await svc.mcp.close()
            await svc.models.close()

    # ---- commands ---------------------------------------------------------------------------------------------------
    async def start(self, req: StartRequest) -> WorkflowView:
        existing = self.store.find_by_request(req.request_id)
        if existing:  # the same request submitted twice resumes the same workflow
            return await self._run(existing)
        wf = "wf-" + uuid.uuid5(uuid.NAMESPACE_URL, req.request_id).hex[:12]
        with tracing.span("request", **{"f2.request_id": req.request_id, "f2.workflow_id": wf, "f2.channel": req.channel}):
            trace_id, span_id = tracing.current_ids()
            self.store.create(wf, req.request_id, req.incident_id, req.requested_by, req.channel, FIRST_STEP,
                              {"incident_id": req.incident_id, "requested_by": req.requested_by, "instructions": req.instructions,
                               "request_id": req.request_id}, trace_id, span_id)
        return await self._run(wf)

    async def approve(self, d: ApprovalDecision) -> WorkflowView:
        rec = self.store.load(d.workflow_id)
        if rec["status"] != "WAITING_APPROVAL":
            return self.view(d.workflow_id)
        with tracing.continue_trace(rec["trace_id"], rec["root_span_id"]):
            with tracing.span("approval.decide", **{"f2.workflow_id": d.workflow_id, "f2.principal": d.decided_by, "f2.approve": d.approve}):
                apr = self.workflow.decide(d.workflow_id, rec["state"], d.decided_by, d.approve, d.reason)
                self.store.event(d.workflow_id, "approval.decided", "execute", apr)
                self._transition_after_decision(d.workflow_id, rec["state"], apr)
        return await self._run(d.workflow_id)

    def _transition_after_decision(self, wf: str, state: dict[str, Any], apr: dict[str, Any]) -> None:
        if apr["status"] == "APPROVED":
            self.store.checkpoint(wf, "approval", "execute", "RUNNING", {**state, "approval": apr})
        elif apr["status"] == "REJECTED":
            self.store.checkpoint(wf, "approval", "record", "RUNNING", {**state, "approval": apr, "outcome": "rejected"})

    async def resume(self, workflow_id: str) -> WorkflowView:
        return await self._run(workflow_id)

    async def recover(self) -> list[WorkflowView]:
        """Resume every RUNNING workflow whose worker died, and finish approval transitions a crash interrupted."""
        for row in self.db.execute("SELECT id, state FROM workflows WHERE status='WAITING_APPROVAL'").fetchall():
            apr = self.approvals.pending(row["id"])
            rec = self.store.load(row["id"])
            aid = (rec["state"].get("approval") or {}).get("id")
            done = self.approvals.get(aid) if aid else None
            if not apr and done and done["status"] in ("APPROVED", "REJECTED"):
                self._transition_after_decision(row["id"], rec["state"], {"id": done["id"], "status": done["status"],
                                                                          "decided_by": done["decided_by"], "required_role": done["required_role"]})
        return [await self._run(wf) for wf in self.store.resumable()]

    async def _run(self, wf: str) -> WorkflowView:
        await self.executor.run(wf, self.workflow.steps())
        return self.view(wf)

    # ---- queries ----------------------------------------------------------------------------------------------------
    def view(self, wf: str) -> WorkflowView:
        rec = self.store.load(wf)
        s = rec["state"]
        return WorkflowView(workflow_id=wf, request_id=rec["request_id"], incident_id=rec["incident_id"], status=rec["status"], step=rec["step"],
                            diagnosis=s.get("diagnosis"), proposal=s.get("proposal"), policy=s.get("policy"), approval=s.get("approval"),
                            action=s.get("action"), verification=s.get("verification"), report=s.get("report"))

    def workflows(self) -> list[WorkflowView]:
        return [self.view(r["id"]) for r in self.db.execute("SELECT id FROM workflows ORDER BY created").fetchall()]
