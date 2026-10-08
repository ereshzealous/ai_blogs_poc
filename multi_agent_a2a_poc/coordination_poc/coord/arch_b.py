"""Architecture B: a deterministic workflow with agents only where reasoning is needed.

The workflow owns sequencing, evidence collection, retries, checks, policy, approval, execution and termination.
Agents (diagnosis, remediation planning, conditional review) have no tools and no authority: they receive evidence and
return structured judgements.  The evidence recipe is generic -- the same seven reads of the alerting service for every
incident, keyed only on the incident's own service and environment -- and anything beyond it must be requested by the
diagnosis agent as a bounded evidence_request, which the workflow executes as ordinary read calls.
"""

from __future__ import annotations

import json
from typing import Any

from coord import prompts
from coord.agent_loop import AgentSpec, run_agent
from coord.contracts import Diagnosis, EvidenceRequest, RemediationProposal, ReviewVerdict
from coord.gateway import CallContext, Denied, GatewayError
from coord.runtime import ArchResult, Terminated, WorkflowCtx
from coord.util import load_config
from coord.world import READ_TOOLS

ELIGIBLE_LIST = load_config("capabilities.yaml")["eligible_writes"]
ELIGIBLE = set(ELIGIBLE_LIST)


def baseline_recipe(incident_id: str, service: str, environment: str) -> list[tuple[str, dict[str, Any]]]:
    """Generic: identical for every incident, parameterised only by the alerting service and environment."""
    return [("get_incident", {"incident_id": incident_id}),
            ("list_deployments", {"service": service, "environment": environment}),
            ("get_change_history", {"service": service, "environment": environment}),
            ("get_dependencies", {"service": service}),
            ("search_logs", {"service": service, "environment": environment, "query": "error warn"}),
            ("query_metrics", {"service": service, "environment": environment, "metric": "latency_p95_ms"}),
            ("query_metrics", {"service": service, "environment": environment, "metric": "error_rate_pct"}),
            ("get_runbook", {"service": service})]


class Workflow:
    def __init__(self, ctx: WorkflowCtx):
        self.ctx, self.s = ctx, ctx.session
        self.token = self.s.tokens.exchange(ctx.root, target="gateway")
        self.call_ctx = CallContext(ctx.workflow_id, "workflow.incident", ctx.environment)
        self.evidence: list[dict[str, Any]] = []
        self.handoffs = 0
        lim = ctx.limits["workflow_b"]
        self.max_requests, self.evidence_rounds, self.review_rounds = int(lim["max_evidence_requests"]), int(lim["evidence_rounds"]), int(lim["review_rounds"])
        self.turns = int(ctx.limits["agents"]["workflow_agent_max_turns"])

    def step(self, kind: str, decided_by: str = "code", **detail: Any) -> None:
        self.s.store.step(self.ctx.workflow_id, "workflow.incident", kind, decided_by, **detail)

    async def read(self, tool: str, args: dict[str, Any]) -> None:
        try:
            out = await self.s.gateway.call(self.token, tool, args, self.call_ctx)
            self.evidence.append({"evidence_ref": out["evidence_ref"], "tool": tool, "args": args, "result": out["result"]})
        except GatewayError as exc:
            self.evidence.append({"tool": tool, "args": args, "error": str(exc)})

    async def agent(self, name: str, instructions: str, output: type, payload: dict[str, Any]) -> Any:
        self.handoffs += 1
        user = prompts.incident_brief(self.ctx.envelope, self.ctx.incident_id) + "\n\n" + json.dumps(payload, separators=(",", ":"), default=str)
        self.step("handoff", to=name, payload_bytes=len(user.encode()))
        result, stats = await run_agent(AgentSpec(name, instructions, max_turns=self.turns), user, self.s.model, None, output,
                                        workflow_id=self.ctx.workflow_id)
        self.step("agent_result", "model", agent=name, result=result.model_dump(), stats=stats)
        return result

    async def fetch_requests(self, reqs: list[EvidenceRequest], why: str) -> int:
        n = 0
        for r in reqs[: self.max_requests]:
            if r.tool not in READ_TOOLS:
                self.step("evidence_request_refused", tool=r.tool, why="not a read tool")
                continue
            await self.read(r.tool, r.args)
            n += 1
        self.step("evidence_round", why=why, requested=len(reqs), fetched=n)
        return n

    async def diagnose(self) -> Diagnosis:
        reads = self.s.gateway.catalog(list(READ_TOOLS))
        d = await self.agent("b.diagnosis", prompts.B_DIAGNOSIS, Diagnosis, {"evidence": self.evidence, "read_tools_you_may_request": reads})
        rounds = 0
        while d.evidence_request and rounds < self.evidence_rounds:
            rounds += 1
            await self.fetch_requests(d.evidence_request, "diagnosis asked for more evidence")
            d = await self.agent("b.diagnosis", prompts.B_DIAGNOSIS, Diagnosis, {"evidence": self.evidence, "read_tools_you_may_request": reads})
        refs = {e.get("evidence_ref") for e in self.evidence}
        unsupported = [r for r in d.root_cause.evidence if r not in refs]
        self.step("check_citations", cited=len(d.root_cause.evidence), unsupported=unsupported)
        return d


async def run(ctx: WorkflowCtx) -> ArchResult:
    wf = Workflow(ctx)
    for tool, args in baseline_recipe(ctx.incident_id, ctx.service, ctx.environment):
        await wf.read(tool, args)
    wf.step("baseline_evidence", items=len(wf.evidence))

    review_round = 0
    while True:
        d = await wf.diagnose()
        result = ArchResult(category=d.root_cause.category, affected_service=d.root_cause.affected_service, summary=d.root_cause.summary,
                            decision=d.recommendation,
                            hypotheses=[{"id": "h1", "statement": d.root_cause.summary, "evidence": d.root_cause.evidence, "confidence": d.root_cause.confidence}]
                            + [{"id": f"h{i + 2}", "statement": a.summary, "evidence": [], "confidence": "low"} for i, a in enumerate(d.alternatives)],
                            details={"handoffs": wf.handoffs})
        if d.recommendation != "remediate":
            wf.step("branch", outcome=d.recommendation, why="diagnosis did not recommend a change")
            return result
        affected = d.root_cause.affected_service or ctx.service
        if affected != ctx.service and not any(e["tool"] == "get_runbook" and e["args"].get("service") == affected for e in wf.evidence):
            await wf.read("get_runbook", {"service": affected})
        catalog = ctx.session.gateway.catalog(ELIGIBLE_LIST)
        plan_input: dict[str, Any] = {"evidence": wf.evidence, "diagnosis": d.model_dump(), "write_tools": catalog}
        for check_round in range(2):
            p = await wf.agent("b.remediation", prompts.B_REMEDIATION, RemediationProposal, plan_input)
            if p.decision != "remediate" or p.action is None:
                break
            a = p.action
            problems = ctx.session.gateway.missing_args(a.tool, a.args) if a.tool in ELIGIBLE else [f"{a.tool} is not an eligible write"]
            if a.args.get("environment") != ctx.environment:
                problems.append("proposal does not target the incident's environment")
            wf.step("check_proposal", tool=a.tool, args=a.args, problems=problems, round=check_round)
            if not problems:
                break
            plan_input = dict(plan_input, previous_proposal=p.model_dump(), problems_found_by_the_workflow=problems)
        else:
            wf.step("branch", outcome="escalate", why="proposal failed the workflow's checks twice")
            result.decision = "escalate"
            return result
        if p.decision != "remediate" or p.action is None:
            wf.step("branch", outcome=p.decision, why="remediation planner did not propose a change")
            result.decision = p.decision if p.decision != "remediate" else "escalate"
            return result
        a = p.action
        needs_review = d.root_cause.confidence != "high" or bool(d.alternatives)
        wf.step("review_rule", needs_review=needs_review, confidence=d.root_cause.confidence, alternatives=len(d.alternatives))
        if needs_review:
            v = await wf.agent("b.review", prompts.B_REVIEW, ReviewVerdict, {"evidence": wf.evidence, "diagnosis": d.model_dump(), "proposal": p.model_dump(),
                                                                              "read_tools_you_may_request": wf.s.gateway.catalog(list(READ_TOOLS))})
            if v.verdict == "reject":
                review_round += 1
                wf.step("review_rejected", round=review_round, reasons=v.reasons)
                if review_round >= wf.review_rounds:
                    wf.step("branch", outcome="escalate", why="review rejected twice: reconciliation policy escalates")
                    result.decision = "escalate"
                    return result
                if v.evidence_request:
                    await wf.fetch_requests(v.evidence_request, "review asked for more evidence")
                continue
        wf.step("execute", tool=a.tool, args=a.args)
        try:
            await ctx.session.gateway.call(wf.token, a.tool, a.args, wf.call_ctx)
        except Denied as exc:
            wf.step("execute_denied", error=str(exc))
            raise Terminated("POLICY_BLOCKED", str(exc), result) from None
        except GatewayError as exc:
            wf.step("execute_failed", error=str(exc))
            raise Terminated("FAILED", str(exc), result) from None
        result.claimed_action = {"tool": a.tool, "args": a.args}
        result.claimed_executed = True
        result.details["handoffs"] = wf.handoffs
        return result
