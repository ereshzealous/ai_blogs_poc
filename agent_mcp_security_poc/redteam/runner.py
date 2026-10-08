"""Run the whole corpus across arms A, B, C; judge each run with the oracle; aggregate into the headline facts.

The same scenarios (same payloads, byte for byte) run under every arm — the comparison is never contaminated by changing
the attack between arms.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from redteam import corpus
from redteam.base import Arm
from redteam import oracle
from redteam.runtime import Runtime, ScenarioRecord

ARMS = [Arm.A, Arm.B, Arm.C]


@dataclass
class RunOutput:
    scenarios: list[dict[str, Any]]
    matrix: dict[str, dict[str, bool]]              # scenario_id -> {arm -> system_compromised}
    facts: dict[str, Any] = field(default_factory=dict)


def run_all(only_set: str | None = None) -> RunOutput:
    rt = Runtime()
    scns = corpus.scenarios()
    if only_set:
        scns = [s for s in scns if s["set"] == only_set]

    records: list[ScenarioRecord] = []
    matrix: dict[str, dict[str, bool]] = {}
    for s in scns:
        matrix[s["id"]] = {}
        for arm in ARMS:
            sr, ent, tx = rt.run_scenario(s, arm)
            compromised, reasons = oracle.judge(ent, tx)
            sr.system_compromised = compromised
            sr.reasons = reasons
            matrix[s["id"]][arm.value] = compromised
            records.append(sr)

    facts = _facts(records, matrix, scns)
    facts["ablation"] = ablation(rt, [s for s in scns if s["class"] not in ("CONTROL", "WITHIN")])
    out = [_record_dict(r) for r in records]
    return RunOutput(scenarios=out, matrix=matrix, facts=facts)


CONTROLS = ["registry", "identity", "policy", "approval", "binding", "egress", "secret"]


def ablation(rt: Runtime, attacks: list[dict]) -> dict[str, Any]:
    """Arm C is the baseline (0 compromised). Remove one control at a time and recount: the delta is the set of attacks
    that control was the deterministic line against. Nothing touches real machine or network controls."""
    result: dict[str, Any] = {"baseline_compromised": 0, "per_control": {}, "standalone_stops": {}}
    allset = frozenset(CONTROLS)
    for ctrl in CONTROLS:
        # (a) remove ONLY this control: the attacks it was the SOLE deterministic line against re-open.
        reopened = []
        for s in attacks:
            _, ent, tx = rt.run_scenario(s, Arm.C, disabled=frozenset({ctrl}))
            if oracle.judge(ent, tx)[0]:
                reopened.append(s["id"])
        result["per_control"][ctrl] = reopened
        # (b) keep ONLY this control (remove all others): the attacks this control alone can still contain.
        stops = []
        for s in attacks:
            _, ent, tx = rt.run_scenario(s, Arm.C, disabled=allset - {ctrl})
            if not oracle.judge(ent, tx)[0]:
                stops.append(s["id"])
        result["standalone_stops"][ctrl] = stops
    return result


def _record_dict(r: ScenarioRecord) -> dict[str, Any]:
    return {"scenario_id": r.scenario_id, "arm": r.arm, "attack_class": r.attack_class, "ingress": r.ingress,
            "model_manipulated": r.model_manipulated, "guard_flagged": r.guard_flagged,
            "system_compromised": r.system_compromised, "reasons": r.reasons,
            "actions": [a.as_dict() for a in r.actions]}


def _facts(records: list[ScenarioRecord], matrix: dict, scns: list[dict]) -> dict[str, Any]:
    attacks = [s for s in scns if s["class"] not in ("CONTROL", "WITHIN")]
    controls = [s for s in scns if s["class"] == "CONTROL"]
    within = [s for s in scns if s["class"] == "WITHIN"]
    aid = {s["id"] for s in attacks}
    cid = {s["id"] for s in controls}
    wid = {s["id"] for s in within}

    def compromised_count(arm: str, ids: set[str]) -> int:
        return sum(1 for sid in ids if matrix[sid][arm])

    by = {(r.scenario_id, r.arm): r for r in records}

    def residual_count(arm: str, ids: set[str]) -> int:
        """A within-authority scenario is 'residual' when its unintended-but-authorised action actually executed."""
        return sum(1 for sid in ids if any(a.hostile and a.executed for a in by[(sid, arm)].actions))

    # model_manipulated is a property of the scenario in arm A (the worst-case model); count attacks where it held
    manip = {r.scenario_id: r.model_manipulated for r in records if r.arm == "A"}
    manipulated_attacks = sum(1 for sid in aid if manip.get(sid))

    # legitimate task completion: every control scenario must be NOT compromised in every arm
    controls_ok = all(not matrix[sid][a] for sid in cid for a in ("A", "B", "C"))

    return {
        "n_scenarios": len(scns),
        "n_attacks": len(attacks),
        "n_controls": len(controls),
        "n_within": len(within),
        "attack_classes": sorted({s["class"] for s in attacks}),
        "manipulated_attacks": manipulated_attacks,
        "within_residual": {a: residual_count(a, wid) for a in ("A", "B", "C")},
        "within_compromised": {a: compromised_count(a, wid) for a in ("A", "B", "C")},
        "compromised": {
            "A": {"attacks": compromised_count("A", aid), "controls": compromised_count("A", cid)},
            "B": {"attacks": compromised_count("B", aid), "controls": compromised_count("B", cid)},
            "C": {"attacks": compromised_count("C", aid), "controls": compromised_count("C", cid)},
        },
        "controls_all_pass": controls_ok,
        "guard_flagged": sum(1 for r in records if r.arm == "B" and r.guard_flagged) // 1,
    }
