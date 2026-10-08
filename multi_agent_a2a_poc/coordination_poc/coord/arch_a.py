"""Architecture A: one agent.

One reasoning component holds the whole context and every capability (all reads and every eligible write).  It decides
what to look at, what the cause is and whether to change production; it triggers the write itself through the same
gateway, policy and approval as every other architecture.  No handoffs, no process boundaries.
"""

from __future__ import annotations

from coord import prompts
from coord.agent_loop import AgentSpec, run_agent
from coord.contracts import IncidentReport
from coord.gateway import CallContext, GatewayTools
from coord.runtime import ArchResult, WorkflowCtx
from coord.util import load_config

ALL_TOOLS = list(load_config("capabilities.yaml")["capabilities"])
CLAIM_CHECK = ("The platform's ledger shows no production change executed in this workflow. If a change is needed, execute it now "
               "with the write tool; otherwise set decision to no_action or escalate.")


def _executed(ctx: WorkflowCtx) -> bool:
    return any(c["kind"] == "write" and c["outcome"] == "ok" for c in ctx.session.store.calls(ctx.workflow_id))


async def run(ctx: WorkflowCtx) -> ArchResult:
    s = ctx.session
    token = s.tokens.exchange(ctx.root, target="gateway")
    tools = GatewayTools(s.gateway, token, ALL_TOOLS, CallContext(ctx.workflow_id, "agent.incident-solo", ctx.environment))
    spec = AgentSpec("agent.incident-solo", prompts.SOLO, max_turns=int(ctx.limits["agents"]["solo_max_turns"]))
    user = prompts.incident_brief(ctx.envelope, ctx.incident_id) + f"\nIncident id for get_incident: {ctx.incident_id}"
    async def ledger_check(r) -> str | None:
        """Same claim-vs-ledger check as C's coordinator gets: once, from the ledger, never from prose."""
        if r.decision == "remediate" and not _executed(ctx):
            s.store.step(ctx.workflow_id, "agent.incident-solo", "claim_check", "code", claimed=r.decision)
            return CLAIM_CHECK
        return None

    report, stats = await run_agent(spec, user, s.model, tools, IncidentReport, workflow_id=ctx.workflow_id, guard=ledger_check)
    assert isinstance(report, IncidentReport)
    s.store.step(ctx.workflow_id, "agent.incident-solo", "final_report", "model", decision=report.decision,
                 category=report.root_cause.category, action=report.action_taken.model_dump() if report.action_taken else None, stats=stats)
    rc = report.root_cause
    hyps = [{"id": "h1", "statement": rc.summary, "evidence": rc.evidence, "confidence": rc.confidence}]
    hyps += [{"id": f"h{i + 2}", "statement": a.summary, "evidence": [], "confidence": "low"} for i, a in enumerate(report.alternatives)]
    return ArchResult(category=rc.category, affected_service=rc.affected_service, summary=rc.summary, decision=report.decision,
                      hypotheses=hyps, claimed_action=report.action_taken.model_dump() if report.action_taken else None,
                      claimed_executed=bool(report.action_taken) if report.decision == "remediate" else None,
                      details={"stats": stats})
