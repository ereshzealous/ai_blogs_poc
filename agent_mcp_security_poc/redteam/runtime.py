"""The agent runtime: the loop that turns the model's proposed actions into mock side effects, through the gates. One
`run_scenario` call produces one evidence record per proposed action, for one arm.

The path, per proposed action:
    registry.resolve  ->  identity (delegation active / peer claim)  ->  policy.decide  ->  approval (if required)
    ->  gateway.execute (argument binding, egress, secrets, data labels)  ->  mock enterprise side effect

Arm A skips every deterministic gate and executes the model's output directly (the vulnerable toy).
Arm B runs the classifier over the untrusted content first; if it flags, the whole turn is blocked; if it misses, the
turn proceeds exactly as in arm A (the classifier is in front of an unrestricted path).
Arm C runs the full gate chain.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from redteam.approvals import ApprovalService
from redteam.base import Arm, Decision, GateEvent, ProposedAction, action_digest
from redteam.enterprise import Enterprise
from redteam.gateway import Gateway
from redteam.guard import Guard
from redteam.identity import Identity
from redteam import model as model_mod
from redteam.policy import PolicyEngine
from redteam.registry import Registry
from redteam.transport import InMemoryTransport

DELEGATION = "dlg-case-20871"


@dataclass
class ActionRecord:
    """The structured evidence for one proposed action (threat-model.md §9)."""
    scenario_id: str
    arm: str
    attack_class: str
    ingress: str
    tool: str
    args: dict[str, Any]
    hostile: bool
    model_manipulated: bool
    events: list[dict[str, Any]] = field(default_factory=list)
    final: str = ""                 # "executed" | "blocked" | "quarantined" | "denied" | "require_approval"
    destination: str | None = None
    labels: tuple[str, ...] = ()
    executed: bool = False
    last_result: Any = None        # the tool's returned value, for tool-output chaining (not serialized)

    def as_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k != "last_result"}
        d["labels"] = list(self.labels)
        return d


@dataclass
class ScenarioRecord:
    scenario_id: str
    arm: str
    attack_class: str
    ingress: str
    model_manipulated: bool
    guard_flagged: bool
    actions: list[ActionRecord]
    # filled by the oracle:
    system_compromised: bool | None = None
    reasons: list[str] = field(default_factory=list)


class Runtime:
    def __init__(self) -> None:
        self.identity = Identity()
        self.registry = Registry()
        self.policy = PolicyEngine()
        self.guard = Guard()
        self._disabled: frozenset[str] = frozenset()

    def run_scenario(self, scenario: dict, arm: Arm,
                     disabled: frozenset[str] = frozenset()) -> tuple[ScenarioRecord, Enterprise, InMemoryTransport]:
        """`disabled` names arm-C controls to turn off for an ablation: registry, identity, policy, approval,
        binding, egress, secret. Removing a control shows which attacks it was the line against."""
        ent = Enterprise()
        tx = InMemoryTransport()
        gateway = Gateway(ent, tx)
        self._disabled = disabled
        approvals = ApprovalService(self.identity.principals)
        ctx = self.identity.context_for_case(DELEGATION)

        # Grant the one legitimate approval that the control scenario OK-2 needs (an eligible supervisor, real record).
        if scenario.get("approve_as"):
            for step in scenario.get("escalation", []) or []:
                approvals.grant("APR-REAL-1", action_digest(step["tool"], step["args"]), scenario["approve_as"])

        # Arm B: classifier over the untrusted content, before the model sees it.
        content = scenario.get("payload", "") or ""
        guard_flagged = False
        content_visible = True
        if arm is Arm.B:
            guard_flagged = self.guard.flags(content)
            if guard_flagged:
                content_visible = False   # the guard stripped the hostile content: model proposes only the task

        mp = model_mod.plan(scenario, content_visible=content_visible)
        records: list[ActionRecord] = []
        last_result: Any = None
        for pa in mp.actions:
            # substitute {{RESULT:-1}} with the ACTUAL output of the previous executed step (tool-output chaining)
            args = {k: (last_result if v == "{{RESULT:-1}}" else v) for k, v in pa.args.items()}
            pa = ProposedAction(pa.tool, args, source=pa.source, hostile=pa.hostile)
            rec = self._run_action(pa, arm, ctx, scenario, gateway, approvals)
            records.append(rec)
            last_result = rec.last_result if rec.executed else last_result

        sr = ScenarioRecord(scenario_id=scenario["id"], arm=arm.value, attack_class=scenario["class"],
                            ingress=scenario["ingress"], model_manipulated=mp.manipulated,
                            guard_flagged=guard_flagged, actions=records)
        return sr, ent, tx

    def _run_action(self, pa: ProposedAction, arm: Arm, ctx, scenario, gateway: Gateway,
                    approvals: ApprovalService) -> ActionRecord:
        rec = ActionRecord(scenario["id"], arm.value, scenario["class"], scenario["ingress"],
                           pa.tool, pa.args, pa.hostile, scenario.get("hijack") not in (None, []))

        # ---- Arm A: the vulnerable toy. No gate. Execute whatever the model said. --------------------------------
        if arm is Arm.A:
            ex = gateway.execute(pa.tool, pa.args, ctx, Arm.A, labels=())
            rec.events.append(GateEvent("runtime", Decision.ALLOW, "toy executes model output directly").as_dict())
            rec.events.append(ex.event.as_dict())
            rec.executed = ex.executed
            rec.final = "executed" if ex.executed else "blocked"
            rec.destination, rec.labels = ex.destination, ex.labels
            rec.last_result = ex.result
            return rec

        # ---- Arm B: if the guard did not strip content, behave like A on whatever the model proposed. -------------
        if arm is Arm.B:
            ex = gateway.execute(pa.tool, pa.args, ctx, Arm.A, labels=())   # same unrestricted path as A
            rec.events.append(GateEvent("guard", Decision.ALLOW, "classifier did not block this turn").as_dict())
            rec.events.append(ex.event.as_dict())
            rec.executed = ex.executed
            rec.final = "executed" if ex.executed else "blocked"
            rec.destination, rec.labels = ex.destination, ex.labels
            rec.last_result = ex.result
            return rec

        # ---- Arm C: the full deterministic chain. Each gate may be ablated via self._disabled. -------------------
        off = self._disabled
        # 1. peer-claimed authority (only for peer scenarios): text is not a token.
        if "identity" not in off and scenario["ingress"] == "peer" and pa.hostile:
            claimed = "dlg-forged" if "delegation=" in scenario.get("payload", "") else None
            ev = self.identity.verify_peer_claim(claimed)
            rec.events.append(ev.as_dict())
            if ev.decision is Decision.DENY:
                rec.final = "denied"
                return rec

        # 2. registry resolution (+ MCP metadata trust)
        if "registry" not in off:
            server_hash = "changed" if ("CHANGED" in scenario.get("payload", "") and pa.tool.startswith("kestrel")) else None
            res = self.registry.resolve(pa.tool, Arm.C, server_metadata_hash=server_hash)
            rec.events.append(res.event.as_dict())
            if not res.resolved:
                rec.final = "quarantined" if res.event.decision is Decision.QUARANTINE else "denied"
                return rec

        # 3. identity: delegation still active
        if "identity" not in off and not self.identity.verify_delegation_active(ctx):
            rec.events.append(GateEvent("identity", Decision.DENY, "delegation not active").as_dict())
            rec.final = "denied"
            return rec

        # 4. policy
        if "policy" not in off:
            pev = self.policy.decide(pa.tool, pa.args, ctx, self.identity.principals)
            rec.events.append(pev.as_dict())
            if pev.decision is Decision.DENY:
                rec.final = "denied"
                return rec
            if pev.decision is Decision.REQUIRE_APPROVAL and "approval" not in off:
                chain = {ctx.human, ctx.agent, ctx.runtime}
                aev = approvals.check(pa.digest, self.policy.approval["required_role"], chain)
                rec.events.append(aev.as_dict())
                if aev.decision is not Decision.ALLOW:
                    rec.final = "require_approval" if aev.decision is Decision.REQUIRE_APPROVAL else "denied"
                    return rec

        # 5. gateway: argument binding, egress, secrets, labels
        ex = gateway.execute(pa.tool, pa.args, ctx, Arm.C, labels=(), disabled=off)
        rec.events.append(ex.event.as_dict())
        rec.executed = ex.executed
        rec.destination, rec.labels = ex.destination, ex.labels
        rec.last_result = ex.result
        rec.final = "executed" if ex.executed else "blocked"
        return rec
