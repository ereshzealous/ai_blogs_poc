"""The headless capability `investigate_incident`: one contract in, one view out, whatever the implementation.

    InvocationEnvelope -> [ A | B | C ] -> ExecutionView

The runtime owns workflow truth and termination for every architecture: it creates the workflow row, mints the
execution identity, sets the budget and deadline, catches every termination reason, and derives the outcome from the
ledgers (gateway calls + world health), never from what a component says it did.  A disagreement between what an
architecture claims and what the ledger shows is recorded as a state conflict.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from coord.agent_loop import AgentFailed
from coord.contracts import Assessment, ExecutionView, Hypothesis, InvocationEnvelope
from coord.gateway import Gateway, McpPool
from coord.identity import Token, TokenService
from coord.models import BudgetExceeded, DeadlineExceeded, ModelGateway, Provider
from coord.store import Store
from coord.telemetry import annotate, current_ids, setup, span
from coord.util import load_config
from coord.world import World

ACTOR = {"A": "agent.incident-solo", "B": "workflow.incident", "C": "agent.coordinator"}


class Terminated(RuntimeError):
    """A termination decided by the component that owns it.  May carry the partial result reached so far."""

    def __init__(self, reason: str, detail: str = "", result: "ArchResult | None" = None):
        super().__init__(f"{reason}: {detail}")
        self.reason, self.detail, self.result = reason, detail, result


@dataclass
class ArchResult:
    category: str | None
    affected_service: str | None
    summary: str
    decision: str                      # remediate | no_action | escalate
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    claimed_action: dict[str, Any] | None = None
    claimed_executed: bool | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    home: Path
    store: Store
    world: World
    tokens: TokenService
    mcp: McpPool
    gateway: Gateway
    model: ModelGateway
    limits: dict[str, Any]
    extras: dict[str, Any] = field(default_factory=dict)

    async def close(self) -> None:
        for x in self.extras.values():
            close = getattr(x, "close", None)
            if close:
                await close()
        await self.model.close()
        await self.mcp.close()


async def open_session(home: Path, *, provider: Provider | None = None, service: str = "c1-host") -> Session:
    home.mkdir(parents=True, exist_ok=True)
    setup(home / "traces", service)
    store = Store(home / "platform.db")
    world_db = str(home / "world.db")
    mcp = McpPool(world_db)
    await mcp.start()
    tokens = TokenService()
    return Session(home=home, store=store, world=World(world_db), tokens=tokens, mcp=mcp,
                   gateway=Gateway(store, mcp, tokens, world_db), model=ModelGateway(store, provider), limits=load_config("limits.yaml"))


@dataclass
class WorkflowCtx:
    session: Session
    workflow_id: str
    arch: str
    envelope: dict[str, Any]
    incident_id: str
    service: str
    environment: str
    root: Token
    limits: dict[str, Any]


def envelope_for(fixture_spec: dict[str, Any], correlation: str) -> InvocationEnvelope:
    inc = fixture_spec["incident"]
    return InvocationEnvelope(event_id=f"evt-{inc['id']}", source=f"monitoring/{inc['reporter']}", channel="event",
                              intent="investigate_incident",
                              subject={"service": inc["service"], "environment": inc["environment"],
                                       "signal": {"incident_id": inc["id"], "alert": inc["title"], "severity": inc["severity"]}},
                              fingerprint=f"{inc['service']}:{inc['id']}", invoker="svc.incident-console", on_behalf_of="alice",
                              correlation_id=correlation, question="Investigate this incident and respond.")


async def invoke(session: Session, envelope: InvocationEnvelope, *, arch: str, workflow_id: str, run_id: str, fixture_id: str,
                 repeat: int, seed: int, overrides: dict[str, Any] | None = None) -> ExecutionView:
    from coord import arch_a, arch_b, arch_c  # local import: architectures depend on the runtime, not the reverse

    impl = {"A": arch_a.run, "B": arch_b.run, "C": arch_c.run}[arch]
    limits = _merge(session.limits, overrides or {})
    env = envelope.model_dump()
    subj = env["subject"]
    max_tokens = int(limits["workflow"]["max_total_tokens"]) if limits["workflow"].get("max_total_tokens") else 0
    started = time.time()
    with span("capability.invoke", **{"c1.workflow_id": workflow_id, "c1.arch": arch, "c1.fixture": fixture_id, "c1.repeat": repeat,
                                      "c1.intent": env["intent"]}):
        trace_id, _ = current_ids()
        session.store.create_workflow(workflow_id=workflow_id, run_id=run_id, arch=arch, fixture_id=fixture_id, repeat=repeat, seed=seed,
                                      incident_id=subj["signal"]["incident_id"], service=subj["service"], environment=subj["environment"],
                                      status="RUNNING", started=started, deadline=started + float(limits["workflow"]["deadline_s"]),
                                      max_tokens=max_tokens, idempotency=limits.get("idempotency", "workflow"), trace_id=trace_id,
                                      config=limits)
        root = session.tokens.issue_root(subject=env["on_behalf_of"] or env["invoker"], invoker=env["invoker"], actor=ACTOR[arch], wf=workflow_id)
        session.store.step(workflow_id, "runtime", "identity", "code", chain=root.chain(), scopes=root.scope)
        ctx = WorkflowCtx(session, workflow_id, arch, env, subj["signal"]["incident_id"], subj["service"], subj["environment"], root, limits)
        result: ArchResult | None = None
        termination, error = "COMPLETED", None
        try:
            result = await impl(ctx)
        except Terminated as t:
            termination, error, result = t.reason, t.detail, t.result
        except BudgetExceeded as exc:
            termination, error = "BUDGET_EXCEEDED", str(exc)
        except DeadlineExceeded as exc:
            termination, error = "TIMEOUT", str(exc)
        except AgentFailed as exc:
            termination, error = "FAILED", str(exc)
        except Exception as exc:  # noqa: BLE001 - any other failure is a FAILED workflow, recorded with its type
            termination, error = "FAILED", f"{type(exc).__name__}: {exc}"[:500]
        view, outcome, conflicts = _conclude(ctx, result, termination)
        annotate(**{"c1.outcome": outcome, "c1.termination": termination})
    session.store.update_workflow(workflow_id, status=view.status, termination=termination, outcome=outcome, ended=time.time(),
                                  result={"result": result.__dict__ if result else None, "error": error, "state_conflicts": conflicts},
                                  view=view.model_dump())
    return view


def _conclude(ctx: WorkflowCtx, result: ArchResult | None, termination: str) -> tuple[ExecutionView, str, list[str]]:
    s = ctx.session
    calls = s.store.calls(ctx.workflow_id)
    writes = [c for c in calls if c["kind"] == "write" and c["outcome"] == "ok"]
    healthy = s.world.healthy(ctx.service)
    if writes:
        outcome = "RESOLVED" if healthy else "UNRESOLVED"
    elif result and result.decision == "escalate":
        outcome = "ESCALATED"
    elif result and result.decision == "no_action":
        outcome = "NO_ACTION"
    elif result and result.decision == "remediate":
        outcome = "NOT_EXECUTED"
    else:
        outcome = "NONE"
    conflicts = []
    if result:
        if result.decision in ("no_action", "escalate") and writes:
            conflicts.append(f"claimed {result.decision} but {len(writes)} write(s) executed")
        if result.claimed_executed and not writes:
            conflicts.append("claimed a write was executed; the ledger has none")
        if result.claimed_action and not writes and result.decision == "remediate":
            conflicts.append("claimed remediation without an executed write")
    status = {"RESOLVED": "COMPLETED", "NO_ACTION": "COMPLETED", "ESCALATED": "ESCALATED"}.get(outcome, "FAILED")
    assessment = None
    if result and result.category:
        hyps = result.hypotheses or [{"id": "h1", "statement": result.summary, "evidence": [], "confidence": "medium"}]
        assessment = Assessment(service=ctx.service, environment=ctx.environment, summary=result.summary,
                                hypotheses=[Hypothesis(**h) for h in hyps], leading=hyps[0]["id"],
                                recommendation={"decision": result.decision, "category": result.category, "affected_service": result.affected_service})
    action = None
    if writes:
        w = writes[-1]
        action = {"capability": w["capability"], "args": w["args"], "approval_id": w["approval_id"], "actor_chain": w["actor_chain"]}
    view = ExecutionView(execution_id=ctx.workflow_id, correlation_id=ctx.envelope["correlation_id"], intent=ctx.envelope["intent"],
                         status=status, step="done", invoker=ctx.envelope["invoker"], channel=ctx.envelope["channel"], assessment=assessment,
                         incident_id=ctx.incident_id, approval={"approval_id": action["approval_id"]} if action else None, action=action,
                         verdict={"outcome": outcome, "termination": termination, "healthy": healthy, "writes": len(writes),
                                  "category": result.category if result else None})
    return view, outcome, conflicts


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out
