"""Architecture C: a coordinator agent delegating to independent agents over A2A.

The coordinator (an LLM in the host) decides every next step: which agent, with what objective and inputs, whether a
remediation may execute, and when to finish.  It holds no tool authority.  Each delegation is an A2A task to an agent
in its own OS process, carrying a token minted for that agent whose scopes are narrowed to the delegation (a proposal
gets read scopes; an authorized execution gets the one write scope of the proposal it executes).

Termination ownership stays with the runtime, not the agents: a hop limit (max_handoffs), a cycle check (an identical
delegation with no new artifact from any other step since is refused), a retry limit per delegation, and the system-level token budget and
deadline enforced on every model call in every process.  Returned artifacts are validated against their schema and
their evidence references checked against the gateway ledger before the coordinator sees them.
"""

from __future__ import annotations

import json
import time
from typing import Any, Protocol

from pydantic import ValidationError

from coord import prompts
from coord.a2a_link import DelegationError, DelegationOutcome
from coord.contracts import ARTIFACT_MODELS, Category, CoordinatorFinish
from coord.identity import Token
from coord.runtime import ArchResult, Terminated, WorkflowCtx
from coord.specialists import AGENTS, SpecialistEnv, run_specialist
from coord.telemetry import span
from coord.util import canon, digest, load_config
from coord.world import WRITE_TOOLS

CAPS = load_config("capabilities.yaml")["capabilities"]
READ_SCOPES = ["read:incident", "read:telemetry", "read:deploy", "read:change"]
PROPOSE_SCOPES = ["read:incident", "read:telemetry", "read:deploy", "read:change"]
ALL_WRITE_SCOPES = sorted({CAPS[t]["scope"] for t in WRITE_TOOLS})
CATEGORIES = list(Category.__args__)  # type: ignore[attr-defined]
CLAIM_CHECK = ("The platform's ledger shows no production change executed in this workflow. To execute, delegate to remediation "
               "with authorize_execution=true and input_artifact_ids of the approved proposal; otherwise finish escalated or no_action.")

DELEGATE = {"type": "function", "function": {
    "name": "delegate", "description": "Delegate one task to an independent agent and wait for its artifact.",
    "parameters": {"type": "object", "required": ["agent", "objective"], "properties": {
        "agent": {"type": "string", "enum": list(AGENTS)},
        "objective": {"type": "string", "description": "What the agent should achieve"},
        "input_artifact_ids": {"type": "array", "items": {"type": "string"}, "description": "Artifacts the agent should receive"},
        "authorize_execution": {"type": "boolean", "description": "remediation only: grant write authority to execute the referenced proposal"}}}}}
FINISH = {"type": "function", "function": {
    "name": "finish", "description": "End the response.",
    "parameters": {"type": "object", "required": ["outcome", "root_cause_category", "affected_service", "summary"], "properties": {
        "outcome": {"type": "string", "enum": ["remediated", "no_action", "escalated"]},
        "root_cause_category": {"type": "string", "enum": CATEGORIES},
        "affected_service": {"type": "string"}, "summary": {"type": "string"}}}}}


class Delegator(Protocol):
    async def delegate(self, agent: str, payload: dict[str, Any], token: str, *, timeout_s: float, message_id: str) -> DelegationOutcome: ...
    async def recover(self, agent: str, task_id: str | None) -> dict[str, Any]: ...


class A2ADelegator:
    """Over the wire: the real A2A boundary, with the supervisor restarting a dead agent before a retry."""

    def __init__(self, link: Any, supervisor: Any):
        self.link, self.supervisor = link, supervisor

    async def delegate(self, agent: str, payload: dict[str, Any], token: str, *, timeout_s: float, message_id: str) -> DelegationOutcome:
        return await self.link.delegate(agent, payload, token, timeout_s=timeout_s, message_id=message_id)

    async def recover(self, agent: str, task_id: str | None) -> dict[str, Any]:
        info = await self.supervisor.ensure(agent)
        if task_id:
            info["get_task_after_recovery"] = await self.link.get_task(agent, task_id)
        return info


class InProcessDelegator:
    """The same agent code called as a function in the host process: no protocol, no process, no wire (E7, tests)."""

    def __init__(self, env: SpecialistEnv):
        self.env = env

    async def delegate(self, agent: str, payload: dict[str, Any], token: str, *, timeout_s: float, message_id: str) -> DelegationOutcome:
        t0 = time.perf_counter()
        tok = self.env.tokens.decode(token, audience=AGENTS[agent]["principal"])
        out = await run_specialist(self.env, payload, tok)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        out["server_ms"] = ms
        return DelegationOutcome(out, task_id="", context_id="", state="IN_PROCESS", client_ms=ms, req_bytes=len(canon(payload)),
                                 resp_bytes=len(canon(out)))

    async def recover(self, agent: str, task_id: str | None) -> dict[str, Any]:
        return {"restarted": False}


class Coordinator:
    def __init__(self, ctx: WorkflowCtx, delegator: Delegator):
        self.ctx, self.s, self.delegator = ctx, ctx.session, delegator
        lim = ctx.limits["multi_agent_c"]
        self.ablation = bool(ctx.limits.get("ablation"))
        caps = ctx.limits["ablation_e8"]
        self.max_handoffs = int(caps["safety_cap_handoffs"]) if self.ablation else int(lim["max_handoffs"])
        self.cycle_check = (not self.ablation) and bool(lim["cycle_check"])
        self.max_retries = int(lim["max_retries"])
        self.timeout_s = float(lim["delegation_timeout_s"])
        self.execute_without_proposal = str(lim.get("execute_without_proposal", "deny"))
        self.max_turns = int(caps["safety_cap_handoffs"]) + 6 if self.ablation else int(ctx.limits["agents"]["coordinator_max_turns"])
        self.handoffs = 0
        self.cycle_blocks = 0
        self.artifacts: dict[str, dict[str, Any]] = {}
        self.seen: dict[str, int] = {}
        self.executed_claims = 0
        self.claim_checked = False

    def step(self, kind: str, decided_by: str = "code", **detail: Any) -> None:
        self.s.store.step(self.ctx.workflow_id, "agent.coordinator", kind, decided_by, **detail)

    def executed(self) -> bool:
        return any(c["kind"] == "write" and c["outcome"] == "ok" for c in self.s.store.calls(self.ctx.workflow_id))

    def scopes_for(self, agent: str, authorize: bool, inputs: list[dict[str, Any]]) -> list[str]:
        """Read scopes, plus at most the ONE write scope of the proposal the execution is handed.

        Fail closed: without a proposal there is no write scope.  The blind run (2026-10-08) ran with a fail-open
        fallback to every eligible write scope (DEVIATIONS D3); `execute_without_proposal: all_writes` reproduces that
        behaviour for replaying runs recorded before the fix, and nothing else."""
        if agent != "remediation":
            return READ_SCOPES
        if not authorize:
            return PROPOSE_SCOPES
        for a in reversed(inputs):
            if a["kind"] == "remediation_proposal" and (a["body"].get("action") or {}).get("tool") in CAPS:
                return PROPOSE_SCOPES + [CAPS[a["body"]["action"]["tool"]]["scope"]]
        return PROPOSE_SCOPES + ALL_WRITE_SCOPES if self.execute_without_proposal == "all_writes" else PROPOSE_SCOPES

    def has_proposal(self, ids: list[str]) -> bool:
        return any(self.artifacts[i]["kind"] == "remediation_proposal" and (self.artifacts[i]["body"].get("action") or {}).get("tool") in CAPS
                   for i in ids)

    async def delegate(self, args: dict[str, Any]) -> dict[str, Any]:
        agent = args.get("agent")
        if agent not in AGENTS:
            return {"error": f"unknown agent {agent}; agents: {', '.join(AGENTS)}"}
        authorize = bool(args.get("authorize_execution")) and agent == "remediation"
        ids = [i for i in (args.get("input_artifact_ids") or []) if i in self.artifacts]
        if authorize and self.execute_without_proposal == "deny" and not self.has_proposal(ids):
            self.step("execute_refused", reason="authorize_execution without a remediation_proposal input", inputs=ids)
            return {"error": "REFUSED: authorize_execution requires the approved remediation_proposal artifact in input_artifact_ids. "
                             "No write authority was delegated and no agent was called."}
        if self.handoffs >= self.max_handoffs:
            self.step("terminate", reason="SAFETY_CAP" if self.ablation else "MAX_HANDOFFS", handoffs=self.handoffs)
            raise Terminated("SAFETY_CAP" if self.ablation else "MAX_HANDOFFS", f"{self.handoffs} handoffs")
        key = canon([agent, authorize, sorted(ids)])
        others = sum(1 for a in self.artifacts.values() if a.get("key") != key)   # new information from any OTHER step
        if self.cycle_check and self.seen.get(key) == others:
            self.cycle_blocks += 1
            self.step("cycle_blocked", agent=agent, inputs=ids, blocks=self.cycle_blocks)
            if self.cycle_blocks >= 2:
                raise Terminated("LOOP_DETECTED", f"repeated identical delegation to {agent}")
            return {"error": "BLOCKED: an identical delegation was already made and no new artifact has appeared since. Choose a different step or finish."}
        self.seen[key] = others
        self.handoffs += 1
        delegation_id = f"{self.ctx.workflow_id}-d{self.handoffs}"
        inputs = [dict(artifact_id=i, **{k: self.artifacts[i][k] for k in ("kind", "producer", "body")}) for i in ids]
        requested = self.scopes_for(agent, authorize, inputs)
        objective = str(args.get("objective") or "")
        payload = {"workflow_id": self.ctx.workflow_id, "delegation_id": delegation_id, "agent": agent, "objective": objective,
                   "authorize_execution": authorize, "inputs": inputs,
                   "incident": {"id": self.ctx.incident_id, "service": self.ctx.service, "environment": self.ctx.environment,
                                "alert": self.ctx.envelope["subject"]["signal"].get("alert", "")}}
        self.step("delegate", "model", agent=agent, authorize=authorize, inputs=ids, objective_digest=digest(objective, 12),
                  payload_bytes=len(canon(payload).encode()))
        last = "no attempt"
        for attempt in range(1 + self.max_retries):
            wf = self.s.store.workflow(self.ctx.workflow_id) or {}
            remaining = float(wf.get("deadline") or time.time() + self.timeout_s) - time.time()
            if remaining <= 0:
                raise Terminated("TIMEOUT", "workflow deadline passed before delegation")
            token: Token = self.s.tokens.exchange(self.ctx.root, target=AGENTS[agent]["principal"], requested=requested, dlg=delegation_id)
            started = time.time()
            self.s.store.execute("INSERT INTO delegations (delegation_id, attempt, workflow_id, seq, agent, mode, objective_digest, inputs, state, started, scopes, token_chain) "
                                 "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                 (delegation_id, attempt, self.ctx.workflow_id, self.handoffs, agent, "execute" if authorize else "default",
                                  digest(objective, 12), canon(ids), "DISPATCHED", started, canon(token.scope), token.chain()))
            try:
                with span("delegation", **{"c1.workflow_id": self.ctx.workflow_id, "c1.delegation_id": delegation_id, "c1.agent": agent,
                                           "c1.attempt": attempt, "c1.scopes": ",".join(token.scope)}):
                    out = await self.delegator.delegate(agent, payload, self.s.tokens.encode(token), timeout_s=min(self.timeout_s, remaining),
                                                        message_id=delegation_id)
            except DelegationError as e:
                self.s.store.execute("UPDATE delegations SET state=?, ended=?, error=?, a2a_task_id=?, a2a_state=? WHERE delegation_id=? AND attempt=?",
                                     (e.kind.upper(), time.time(), e.detail[:300], e.task_id, ",".join(e.states), delegation_id, attempt))
                last = f"{e.kind}: {e.detail}"
                if e.kind in ("transport", "timeout") and attempt < self.max_retries:
                    info = await self.delegator.recover(agent, e.task_id)
                    self.step("delegation_retry", agent=agent, delegation_id=delegation_id, failed_attempt=attempt, failure=e.kind,
                              old_task_id=e.task_id, **info)
                    continue
                return {"error": f"{agent} delegation {e.kind}: {e.detail}"[:400]}
            kind = out.out.get("kind", "")
            model = ARTIFACT_MODELS.get(kind)
            try:
                body = model.model_validate(out.out.get("body")) if model else None
            except ValidationError as exc:
                body = None
                last = f"invalid artifact: {exc.errors()[:2]}"
            if body is None:
                self.s.store.execute("UPDATE delegations SET state='INVALID_ARTIFACT', ended=?, error=? WHERE delegation_id=? AND attempt=?",
                                     (time.time(), last[:300], delegation_id, attempt))
                return {"error": f"{agent} returned an artifact that failed validation"}
            refs = _refs(body.model_dump())
            known = {r["evidence_ref"] for r in self.s.store.rows("SELECT evidence_ref FROM gateway_calls WHERE workflow_id=? AND evidence_ref IS NOT NULL",
                                                                   (self.ctx.workflow_id,))}
            unsupported = sorted(r for r in refs if r not in known)
            artifact_id = f"art-{len(self.artifacts) + 1}"
            self.artifacts[artifact_id] = {"kind": kind, "producer": agent, "body": body.model_dump(), "key": key}
            self.s.store.put_artifact(artifact_id, self.ctx.workflow_id, AGENTS[agent]["principal"], kind, body.model_dump(), delegation_id)
            self.s.store.execute("UPDATE delegations SET state='COMPLETED', ended=?, client_ms=?, server_ms=?, req_bytes=?, resp_bytes=?, "
                                 "a2a_task_id=?, a2a_context_id=?, a2a_state=?, artifact_id=? WHERE delegation_id=? AND attempt=?",
                                 (time.time(), out.client_ms, out.out.get("server_ms"), out.req_bytes, out.resp_bytes, out.task_id, out.context_id,
                                  ",".join(out.states) or out.state, artifact_id, delegation_id, attempt))
            self.step("artifact", agent=agent, artifact_kind=kind, artifact_id=artifact_id, cited=len(refs), unsupported_refs=unsupported)
            if kind == "remediation_result" and body.model_dump().get("executed"):
                self.executed_claims += 1
            return {"artifact_id": artifact_id, "agent": agent, "kind": kind, "body": body.model_dump(),
                    **({"provenance_warning": f"cites unknown evidence refs {unsupported}"} if unsupported else {})}
        return {"error": f"{agent} unavailable after {1 + self.max_retries} attempts ({last})"}

    async def run(self) -> ArchResult:
        msgs: list[dict[str, Any]] = [{"role": "system", "content": prompts.COORDINATOR},
                                      {"role": "user", "content": prompts.incident_brief(self.ctx.envelope, self.ctx.incident_id)}]
        kw = dict(component="agent.coordinator", role="coordination", workflow_id=self.ctx.workflow_id)
        for _ in range(self.max_turns):
            reply = await self.s.model.generate(msgs, tools=[DELEGATE, FINISH], **kw)
            msgs.append({"role": "assistant", "content": reply.content,
                         **({"tool_calls": [{"function": {"name": c["name"], "arguments": c["arguments"]}} for c in reply.tool_calls]}
                            if reply.tool_calls else {})})
            if not reply.tool_calls:
                self.step("nudge", why="coordinator answered without calling delegate or finish")
                msgs.append({"role": "user", "content": "Call delegate or finish."})
                continue
            for call in reply.tool_calls:
                if call["name"] == "finish":
                    try:
                        fin = CoordinatorFinish.model_validate(call["arguments"])
                    except ValidationError as exc:
                        msgs.append({"role": "tool", "tool_name": "finish", "content": json.dumps({"error": str(exc.errors()[:2])})})
                        continue
                    if fin.outcome == "remediated" and not self.claim_checked and not self.executed():
                        self.claim_checked = True
                        self.step("claim_check", claimed=fin.outcome)
                        msgs.append({"role": "tool", "tool_name": "finish", "content": json.dumps({"error": CLAIM_CHECK})})
                        continue
                    return self.result(fin)
                if call["name"] == "delegate":
                    res = await self.delegate(call["arguments"] or {})
                else:
                    res = {"error": f"unknown tool {call['name']}"}
                # sort_keys: artifacts arrive as protobuf Struct (map order not preserved), and replay keys on exact prompts
                msgs.append({"role": "tool", "tool_name": call["name"], "content": json.dumps(res, separators=(",", ":"), default=str, sort_keys=True)})
        self.step("coordinator_turns_exhausted", turns=self.max_turns)
        schema = CoordinatorFinish.model_json_schema()
        msgs.append({"role": "user", "content": "You are out of turns. Finish now: one JSON object matching this schema.\n" + json.dumps(schema)})
        reply = await self.s.model.generate(msgs, schema=schema, **kw)
        try:
            return self.result(CoordinatorFinish.model_validate_json(reply.content))
        except ValidationError as exc:
            raise Terminated("FAILED", f"coordinator could not finish: {exc.errors()[:1]}") from None

    def result(self, fin: CoordinatorFinish) -> ArchResult:
        decision = {"remediated": "remediate", "no_action": "no_action", "escalated": "escalate"}[fin.outcome]
        self.step("finish", "model", outcome=fin.outcome, category=fin.root_cause_category, handoffs=self.handoffs)
        hyps = []
        for a in reversed(list(self.artifacts.values())):
            if a["kind"] == "diagnosis":
                rc = a["body"]["root_cause"]
                hyps = [{"id": "h1", "statement": rc["summary"], "evidence": rc.get("evidence", []), "confidence": rc["confidence"]}]
                break
        if not hyps:
            hyps = [{"id": "h1", "statement": fin.summary, "evidence": [], "confidence": "medium"}]
        else:
            hyps[0]["statement"] = fin.summary or hyps[0]["statement"]
        action = None
        for a in reversed(list(self.artifacts.values())):
            if a["kind"] in ("remediation_result", "remediation_proposal") and a["body"].get("action"):
                action = a["body"]["action"]
                break
        return ArchResult(category=fin.root_cause_category, affected_service=fin.affected_service, summary=fin.summary, decision=decision,
                          hypotheses=hyps, claimed_action=action, claimed_executed=bool(self.executed_claims) or None,
                          details={"handoffs": self.handoffs, "cycle_blocks": self.cycle_blocks, "artifacts": len(self.artifacts)})


def _refs(obj: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            found |= _refs(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _refs(v)
    elif isinstance(obj, str) and obj.startswith("ev-") and obj[3:].isdigit():
        found.add(obj)
    return found


async def run(ctx: WorkflowCtx) -> ArchResult:
    delegator = ctx.session.extras.get("delegator")
    if delegator is None:
        raise RuntimeError("architecture C needs a delegator in session.extras (A2A link + supervisor, or in-process)")
    return await Coordinator(ctx, delegator).run()

