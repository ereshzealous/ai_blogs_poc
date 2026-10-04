"""The runtime SDK: the enforcement points agents run behind. Agents see only `ctx.call(...)` and `ctx.model(...)`.

At every enforcement point the runtime:
  1 syncs with the control plane (cheap: compare the distributed pointer with the cached version; fetch and verify
    a new signed bundle only when it changed), or falls back to its last-known-good bundle per the failure policy;
  2 asks the decision function (pdp.py) using the bundle's desired state, never its own;
  3 enforces the answer: execute, hold for approval, or deny; mints a short-lived credential only for an execution;
  4 writes a hash-chained audit event that names the config version, its source (live or last-known-good) and the rule.

A run follows a rollout track (stable or canary, chosen by a deterministic hash of the run id) and picks up a new
version on that track at the next enforcement point. That is how a suspension reaches a run already in flight.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

from acp.common import append_chained, code_sha256, digest, read_json, write_json
from acp.runtime import pdp
from acp.runtime.services import ApprovalService, BadSignature, CredentialBroker, Distribution, SpendMeter, Unreachable
from acp.systems import ModelGateway, SystemRefused, Systems

AGENT_MODULES = {"incident-agent": "acp.agents.incident_agent", "support-agent": "acp.agents.support_agent", "finance-agent": "acp.agents.finance_agent"}


def bucket(run_id: str) -> int:
    return int(digest(run_id)[:8], 16) % 100


@dataclass
class Outcome:
    """What an agent gets back. Agents treat it as data; they do not interpret policy."""

    status: str  # executed | pending_approval | denied
    value: dict | None = None
    reason: str | None = None
    approval_id: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "executed"


@dataclass
class RunState:
    run_id: str
    agent: str
    tick: int
    tool_calls: int = 0
    cost: float = 0.0
    versions: list = field(default_factory=list)
    calls: list = field(default_factory=list)


class Runtime:
    def __init__(
        self,
        state: Path,
        instance: str,
        workload: str = "spiffe://acp.example/ns/agents/sa/agent-runtime",
        agents: dict | None = None,
        agents_dir: Path | None = None,
        backend=None,
    ):
        """`agents`, `agents_dir` and `backend` are set only in live mode (acp/live/): LLM-planned agents and a real model
        behind the gateway. The enforcement below is the same code either way."""
        self.state, self.instance, self.workload = Path(state), instance, workload
        self.home = self.state / "runtime" / instance
        self.dist = Distribution(self.state, instance)
        self.broker, self.approvals, self.spend = CredentialBroker(self.state), ApprovalService(self.state), SpendMeter(self.state)
        self.systems, self.models = Systems(self.state), ModelGateway(self.state, backend)
        self.agents = {name: importlib.import_module(mod) for name, mod in (agents or AGENT_MODULES).items()}
        self.agents_dir = agents_dir
        self.loaded_code_sha256 = self.code_sha256()
        self.sync_error: str | None = None
        self.checkpoint = None  # set by the worker to pause mid-run for an interleaved control-plane change

    def code_sha256(self) -> str:
        return code_sha256(self.agents_dir) if self.agents_dir else code_sha256()

    # ---- config: sync, cache, last-known-good ------------------------------------------------------------------------
    def cache(self) -> dict | None:
        return read_json(self.home / "cache.json")

    def is_mutation(self, tool: str) -> bool:
        """Read or mutation, from the cached registry. An unknown tool is treated as a mutation (the stricter class)."""
        meta = ((self.cache() or {}).get("bundle") or {}).get("desired_state", {}).get("tools", {}).get(tool)
        return True if meta is None else meta["mutation"]

    def audit(self, **rec) -> None:
        append_chained(self.home / "audit.jsonl", {"instance": self.instance, **rec})

    def sync(self, tick: int, run_id: str) -> tuple[dict | None, str]:
        """Return (bundle, source). source: live | last_known_good | none. Never raises."""
        cache = self.cache()
        self.sync_error = None
        try:
            ptr = self.dist.pointer()
            can = ptr.get("canary")
            want = can["version"] if can and bucket(run_id) < can["percent"] else ptr["stable"]
            if not cache or cache["version"] != want:
                b = self.dist.bundle(want)
                prev = cache["version"] if cache else None
                cache = {"version": want, "bundle": b, "synced_tick": tick}
                self.audit(
                    tick=tick,
                    event="config.applied",
                    run_id=run_id,
                    config_version=want,
                    previous_version=prev,
                    track="canary" if can and want == can["version"] else "stable",
                )
            else:
                cache["synced_tick"] = tick
            write_json(self.home / "cache.json", cache)
            return cache["bundle"], "live"
        except Unreachable as e:
            self.sync_error = "CONTROL_PLANE_UNREACHABLE"
            self.audit(tick=tick, event="config.unreachable", run_id=run_id, error=str(e), cached_version=cache["version"] if cache else None)
        except BadSignature as e:
            self.sync_error = "BUNDLE_REJECTED"
            self.audit(tick=tick, event="config.rejected", run_id=run_id, error=str(e), cached_version=cache["version"] if cache else None)
        return (cache["bundle"], "last_known_good") if cache else (None, "none")

    def policy(self, tick: int, run_id: str, mutation: bool) -> tuple[dict | None, str, str | None, pdp.Decision | None]:
        """(desired_state, version, source, fail_decision). A fail_decision means: do not proceed, whatever policy says."""
        bundle, source = self.sync(tick, run_id)
        if bundle is None:
            return None, None, source, pdp.Decision(pdp.DENY, "NO_POLICY_AVAILABLE", "failure_policy")
        s, v = bundle["desired_state"], bundle["version"]
        if source == "live":
            return s, v, source, None
        fp = s["failure_policy"]
        stale = tick - self.cache()["synced_tick"]
        if stale > fp["max_staleness_ticks"]:
            return s, v, source, pdp.Decision(pdp.DENY, "POLICY_STALE", "failure_policy.max_staleness_ticks")
        if mutation and fp["unreachable"]["mutation"] == "fail_closed":
            return s, v, source, pdp.Decision(pdp.DENY, self.sync_error, "failure_policy.unreachable.mutation")
        return s, v, source, None

    # ---- running agents ----------------------------------------------------------------------------------------------
    def run(self, agent: str, task: dict, run_id: str, tick: int) -> dict:
        rs = RunState(run_id=run_id, agent=agent, tick=tick)
        self.audit(tick=tick, event="run.requested", run_id=run_id, agent=agent, task=task)
        s, v, src, fail = self.policy(tick, run_id, mutation=False)
        if fail is None:
            d = pdp.decide_start(s, agent, self.workload, self.spend.today(agent))
        else:
            d = fail
        self.audit(tick=tick, event="run.decision", run_id=run_id, agent=agent, config_version=v, config_source=src, decision=d.to())
        if d.effect != pdp.ALLOW:
            return {"run_id": run_id, "agent": agent, "status": "denied", "reason": d.reason, "config_version": v, "calls": [], "result": None}
        ctx = Context(self, rs)
        result = self.agents[agent].run(task, ctx)
        self.audit(tick=rs.tick, event="run.finished", run_id=run_id, agent=agent, tool_calls=rs.tool_calls, cost=round(rs.cost, 4))
        return {
            "run_id": run_id,
            "agent": agent,
            "status": "finished",
            "config_version": v,
            "versions": rs.versions,
            "calls": rs.calls,
            "result": result,
            "tool_calls": rs.tool_calls,
            "cost": round(rs.cost, 4),
        }

    def execute(self, s: dict, agent: str, tool: str, args: dict, tick: int) -> Outcome:
        meta = s["tools"][tool]
        try:
            cred = self.broker.issue(agent, tool, meta["credential"], tick)
        except Unreachable:
            return Outcome("denied", reason="CREDENTIAL_UNAVAILABLE")
        try:
            value = self.systems.call(meta["server"], tool, args, agent, cred, tick)
        except SystemRefused as e:
            return Outcome("denied", reason=f"SYSTEM_REFUSED: {e}")
        return Outcome("executed", value=value, reason=cred["id"])

    def resume(self, approval_id: str, tick: int) -> dict:
        """Execute a held action once its approval is granted, re-checking current policy first. Never twice."""
        a = self.approvals.get(approval_id)
        p = a["pending"]
        agent, tool, args, run_id = p["agent"], p["action"]["tool"], p["action"]["args"], p["run_id"]
        s, v, src, fail = self.policy(tick, run_id, mutation=True)
        d = fail or pdp.decide_tool(s, agent, self.workload, tool, args, tool_calls_so_far=0)
        if a["status"] != "approved" or a["executed"]:
            why = "ALREADY_EXECUTED" if a["executed"] else f"APPROVAL_{a['status'].upper()}"
            self.audit(tick=tick, event="resume.refused", run_id=run_id, agent=agent, approval_id=approval_id, reason=why, config_version=v)
            return {"approval_id": approval_id, "executed": False, "reason": why, "config_version": v}
        if d.effect not in (pdp.ALLOW, pdp.APPROVAL):
            self.audit(
                tick=tick, event="resume.refused", run_id=run_id, agent=agent, approval_id=approval_id, reason=d.reason, config_version=v, decision=d.to()
            )
            return {"approval_id": approval_id, "executed": False, "reason": d.reason, "config_version": v}
        out = self.execute(s, agent, tool, args, tick)
        if out.ok:
            self.approvals.mark_executed(approval_id)
        self.audit(
            tick=tick,
            event="action.executed" if out.ok else "action.failed",
            run_id=run_id,
            agent=agent,
            action=tool,
            args=args,
            approval_id=approval_id,
            config_version=v,
            config_source=src,
            executed=out.ok,
            credential=out.reason if out.ok else None,
            decision=d.to(),
            reason=None if out.ok else out.reason,
        )
        return {"approval_id": approval_id, "executed": out.ok, "reason": out.reason if not out.ok else "APPROVED_AND_EXECUTED", "config_version": v}

    def status(self, tick: int) -> dict:
        """The observed state this instance reports back: which version it runs, from where, and how fresh."""
        c = self.cache()
        return {
            "instance": self.instance,
            "config_version": c["version"] if c else None,
            "synced_tick": c["synced_tick"] if c else None,
            "tick": tick,
            "agents": sorted(self.agents),
            "code_sha256": self.code_sha256(),
            "loaded_code_sha256": self.loaded_code_sha256,
        }


class Context:
    """The only surface an agent sees. It carries no policy; each call goes through the enforcement points above."""

    def __init__(self, rt: Runtime, rs: RunState):
        self.rt, self.rs = rt, rs

    def _next_tick(self) -> int:
        self.rs.tick += 1
        return self.rs.tick

    def _record(self, kind: str, name: str, v: str | None, out: Outcome) -> Outcome:
        if v and v not in self.rs.versions:
            self.rs.versions.append(v)
        self.rs.calls.append(
            {
                "kind": kind,
                "name": name,
                "config_version": v,
                "status": out.status,
                "reason": out.reason if out.status != "executed" else None,
                "approval_id": out.approval_id,
            }
        )
        if kind == "tool" and self.rt.checkpoint:
            self.rt.checkpoint(self.rs)
        return out

    def call(self, tool: str, **args) -> Outcome:
        rt, rs = self.rt, self.rs
        tick = self._next_tick()
        s, v, src, fail = rt.policy(tick, rs.run_id, mutation=rt.is_mutation(tool))
        d = fail or pdp.decide_tool(s, rs.agent, rt.workload, tool, args, rs.tool_calls)
        base = dict(tick=tick, run_id=rs.run_id, agent=rs.agent, action=tool, args=args, config_version=v, config_source=src, decision=d.to())
        if d.effect == pdp.DENY:
            rt.audit(event="action.denied", executed=False, **base)
            return self._record("tool", tool, v, Outcome("denied", reason=d.reason))
        rs.tool_calls += 1
        if d.effect == pdp.APPROVAL:
            ap = s["approvals"][tool]
            a = rt.approvals.request(
                {"agent": rs.agent, "run_id": rs.run_id, "config_version": v, "action": {"tool": tool, "args": args}},
                ap["approvers"],
                tick + ap["expires_in_ticks"],
                tick,
            )
            rt.audit(event="approval.requested", executed=False, approval_id=a["id"], eligible=ap["approvers"], **base)
            return self._record("tool", tool, v, Outcome("pending_approval", reason=d.reason, approval_id=a["id"]))
        out = rt.execute(s, rs.agent, tool, args, tick)
        mutation = s["tools"][tool]["mutation"]
        ev = ("action.executed" if mutation else "tool.executed") if out.ok else "action.failed"
        rt.audit(event=ev, executed=out.ok, credential=out.reason if out.ok else None, failure=None if out.ok else out.reason, **base)
        return self._record("tool", tool, v, out if not out.ok else Outcome("executed", value=out.value))

    def tools(self) -> list[dict]:
        """MCP discovery: every tool the servers offer. Seeing a tool is not permission to call it."""
        return self.rt.systems.catalog()

    def model(self, purpose: str, data: list | None = None, data_class: str = "internal", tools: list | None = None) -> Outcome:
        """A model call through the gateway. With `tools`, the model may propose the next tool call (live agents); the
        proposal comes back as data in `value["tool_call"]` and is enforced like any other call when the agent makes it."""
        rt, rs = self.rt, self.rs
        tick = self._next_tick()
        prompt = purpose + " " + " ".join(str(x) for x in (data or []))
        s, v, src, fail = rt.policy(tick, rs.run_id, mutation=False)
        est = lambda meta: round(rt.models.tokens(prompt) / 1000 * meta["usd_per_1k_tokens"], 4)
        if fail:
            d, m = fail, None
        else:
            d, m = pdp.decide_model(s, rs.agent, rt.workload, data_class, est, rs.cost)
        base = dict(tick=tick, run_id=rs.run_id, agent=rs.agent, purpose=purpose, data_class=data_class, config_version=v, config_source=src, decision=d.to())
        if d.effect != pdp.ALLOW:
            rt.audit(event="model.denied", model=None, **base)
            return self._record("model", "model", v, Outcome("denied", reason=d.reason))
        request = {"purpose": purpose, "data": data or [], "tools": tools}
        r = rt.models.complete(m, s["models"]["catalog"][m], prompt, rs.agent, data_class, tick, request)
        rs.cost += r["usd"]
        rt.spend.add(rs.agent, r["usd"])
        extra = {"proposed": r.get("tool_call")} if tools is not None else {}
        rt.audit(event="model.called", model=m, tokens=r["tokens"], usd=r["usd"], **extra, **base)
        out = Outcome("executed", value=r)
        self._record("model", m, v, out)
        return out
