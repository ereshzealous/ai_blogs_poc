"""The platform facade and composition root. Channels call this and nothing else.

    async with PlatformService.open() as svc:
        view = await svc.start_investigation(StartInvestigation(...))
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from agent_platform.actions.audit import AuditLog
from agent_platform.actions.gateway import ActionGateway
from agent_platform.actions.idempotency import IdempotencyStore
from agent_platform.actions.mcp_pool import McpPool
from agent_platform.actions.policy import PolicyEngine
from agent_platform.actions.registry import CapabilityRegistry
from agent_platform.agents.incident_agents import DiagnosisAgent, RemediationAgent, SummaryAgent
from agent_platform.agents.runtime import AgentRuntime
from agent_platform.config import Settings, load_settings
from agent_platform.context.assembler import ContextAssembler
from agent_platform.context.session import SessionStore
from agent_platform.contracts import ApprovalDecision, StartInvestigation
from agent_platform.evals.checks import evaluate_run
from agent_platform.identity.principals import Forbidden, resolve_user
from agent_platform.knowledge.retrieval import KnowledgeBase
from agent_platform.memory.store import MemoryStore
from agent_platform.models.gateway import ModelGateway
from agent_platform.orchestration.store import WorkflowStore
from agent_platform.orchestration.workflow import WorkflowBusy, WorkflowDeps, WorkflowEngine
from agent_platform.telemetry import tracing

__all__ = ["PlatformService", "Forbidden", "WorkflowBusy", "StartInvestigation", "ApprovalDecision"]


class PlatformService:
    def __init__(self, settings: Settings, engine: WorkflowEngine, models: ModelGateway, pool: McpPool,
                 audit: AuditLog, store: WorkflowStore):
        self.settings = settings
        self.engine = engine
        self.models = models
        self.pool = pool
        self.audit = audit
        self.store = store

    @classmethod
    @asynccontextmanager
    async def open(cls, settings: Settings | None = None) -> AsyncIterator[PlatformService]:
        s = settings or load_settings()
        tracing.setup(s.runs_dir)
        db = s.platform_db
        registry = CapabilityRegistry()
        pool = McpPool(s.enterprise_db)
        audit = AuditLog(db)
        gateway = ActionGateway(registry, PolicyEngine(registry), pool, IdempotencyStore(db), audit)
        mcfg = s.section("models")
        models = ModelGateway(url=s.ollama_url, routes=s.model_routes, profiles=s.model_profiles, db_path=db,
                              timeout_s=mcfg.get("request_timeout_s", 240),
                              workflow_budget=mcfg.get("budgets", {}).get("workflow_tokens", 150_000))
        sessions, memory = SessionStore(db), MemoryStore(db)
        memory.seed()
        knowledge = KnowledgeBase(s.knowledge_dir, s.knowledge_index, models)
        assembler = ContextAssembler(sessions, memory, knowledge)
        runtime = AgentRuntime(models)
        store = WorkflowStore(db)
        deps = WorkflowDeps(store=store, actions=gateway, sessions=sessions, memory=memory,
                            diagnosis=DiagnosisAgent(runtime, assembler), remediation=RemediationAgent(runtime, assembler),
                            summary=SummaryAgent(runtime, assembler), tokens_used=models.tokens_used,
                            settings=s.section("orchestration"))
        await pool.start()
        try:
            yield cls(s, WorkflowEngine(deps), models, pool, audit, store)
        finally:
            await pool.close()
            await models.close()

    # ---------------------------------------------------------------- commands
    async def start_investigation(self, cmd: StartInvestigation, *, run_until: str | None = None) -> dict[str, Any]:
        resolve_user(cmd.user_id)
        return await self.engine.start(incident_id=cmd.incident_id, request=cmd.request, user_id=cmd.user_id,
                                       channel=cmd.channel, session_id=cmd.session_id, run_until=run_until)

    def submit(self, cmd: StartInvestigation) -> tuple[str, Any]:
        """Create the workflow now and return (workflow_id, coroutine that runs it) for background execution."""
        resolve_user(cmd.user_id)
        wf_id, state = self.engine.prepare(incident_id=cmd.incident_id, request=cmd.request, user_id=cmd.user_id,
                                           channel=cmd.channel, session_id=cmd.session_id)
        return wf_id, self.engine.run_new(wf_id, state)

    def check_approver(self, cmd: ApprovalDecision) -> None:
        """Fail fast (403 / 409) before scheduling a decision in the background."""
        approval = self.store.open_approval(cmd.workflow_id)
        if approval is None or approval["status"] != "PENDING":
            raise ValueError(f"{cmd.workflow_id} has no pending approval")
        from agent_platform.identity.principals import require_role
        require_role(resolve_user(cmd.approver_id), approval["required_role"])

    async def decide_approval(self, cmd: ApprovalDecision) -> dict[str, Any]:
        return await self.engine.decide(cmd.workflow_id, cmd.approver_id, cmd.approve, cmd.comment)

    async def resume(self, workflow_id: str) -> dict[str, Any]:
        return await self.engine.resume(workflow_id)

    async def recover(self) -> list[dict[str, Any]]:
        return await self.engine.recover()

    # ---------------------------------------------------------------- queries
    def workflow(self, workflow_id: str) -> dict[str, Any]:
        return self.engine.view(workflow_id)

    def workflows(self, status: str | None = None) -> list[dict[str, Any]]:
        return [self.engine.view(w["id"]) for w in self.store.list(status)]

    def events(self, workflow_id: str) -> list[dict[str, Any]]:
        return self.store.events(workflow_id)

    def audit_log(self, workflow_id: str) -> list[dict[str, Any]]:
        return self.audit.list(workflow_id)

    def trace(self, workflow_id: str) -> list[dict[str, Any]]:
        wf = self.store.get(workflow_id)
        return tracing.read_trace(self.settings.runs_dir, wf["trace_id"]) if wf and wf["trace_id"] else []

    def evaluate(self, workflow_id: str, backend_rollbacks: int | None = None) -> dict[str, Any]:
        return evaluate_run(self.workflow(workflow_id), self.events(workflow_id), self.audit_log(workflow_id), backend_rollbacks)

    def model_usage(self, workflow_id: str) -> list[dict[str, Any]]:
        return self.models.usage(workflow_id)

    def workflow_record(self, workflow_id: str) -> dict[str, Any]:
        """Everything recorded about one workflow, for reports: view, events, audit, model usage, trace, evals and
        the investigation and proposals kept in the latest checkpoint."""
        state = (self.store.latest_checkpoint(workflow_id) or {}).get("state", {})
        return {"view": self.workflow(workflow_id), "events": self.events(workflow_id), "audit": self.audit_log(workflow_id),
                "usage": self.model_usage(workflow_id), "trace": self.trace(workflow_id), "eval": self.evaluate(workflow_id),
                "investigation": state.get("investigation"), "proposals": state.get("proposals")}
