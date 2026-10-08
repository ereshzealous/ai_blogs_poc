"""`redteam <command>`: the one command surface.

    redteam demo         the legitimate task plus one contained attack, narrated
    redteam scenarios    the whole corpus across arms A/B/C, as a table (no evidence written)
    redteam matrix       the model-manipulated vs system-compromised headline table
"""
from __future__ import annotations

import sys

from redteam.base import Arm
from redteam.runner import run_all
from redteam.runtime import Runtime
from redteam import corpus, oracle


def _table(out) -> None:
    w = max(len(s) for s in out.matrix) + 2
    print(f"\n{'scenario':<{w}}{'class':<9}{'manip':<7}{'A':<6}{'B':<6}{'C':<6}")
    print("-" * (w + 34))
    by_id = {r["scenario_id"]: r for r in out.scenarios if r["arm"] == "A"}
    for sid, arms in out.matrix.items():
        r = by_id[sid]
        manip = "YES" if r["model_manipulated"] else "–"
        def cell(v: bool) -> str:
            return "COMPROMISED" if v else "contained"
        print(f"{sid:<{w}}{r['attack_class']:<9}{manip:<7}"
              f"{cell(arms['A']):<6}  {cell(arms['B']):<6}  {cell(arms['C']):<6}")


def cmd_scenarios() -> None:
    out = run_all()
    # compact A/B/C compromise flags per scenario
    w = max(len(s) for s in out.matrix) + 2
    print(f"\n{'scenario':<{w}}{'class':<9}{'manip':<7}{'A':<13}{'B':<13}{'C':<13}")
    print("-" * (w + 55))
    by_id = {r["scenario_id"]: r for r in out.scenarios if r["arm"] == "A"}
    for sid, arms in out.matrix.items():
        r = by_id[sid]
        manip = "YES" if r["model_manipulated"] else "–"
        f = lambda v: "COMPROMISED" if v else "contained"
        print(f"{sid:<{w}}{r['attack_class']:<9}{manip:<7}{f(arms['A']):<13}{f(arms['B']):<13}{f(arms['C']):<13}")
    fa = out.facts
    print(f"\nattacks: {fa['n_attacks']}  controls: {fa['n_controls']}  "
          f"model-manipulated attacks: {fa['manipulated_attacks']}")
    print(f"system compromised  —  A: {fa['compromised']['A']['attacks']}/{fa['n_attacks']}   "
          f"B: {fa['compromised']['B']['attacks']}/{fa['n_attacks']}   "
          f"C: {fa['compromised']['C']['attacks']}/{fa['n_attacks']}")
    print(f"controls all pass (legit task + escalation worked in every arm): {fa['controls_all_pass']}")


def cmd_matrix() -> None:
    _table(run_all())


def cmd_ablation() -> None:
    ab = run_all().facts["ablation"]
    print("\nArm C with one control removed at a time (baseline: 0 attacks compromised):\n")
    print(f"{'control':<16}{'sole line for':<16}{'alone contains':<16}")
    print("-" * 70)
    for ctrl in ab["per_control"]:
        sole = ab["per_control"][ctrl]
        alone = ab["standalone_stops"][ctrl]
        print(f"{ctrl:<16}{len(sole):<16}{len(alone):<16}")
    print("\nsole line = attack re-opens when ONLY this control is removed (overlap elsewhere = 0)")
    print("alone contains = attacks still contained when this is the ONLY control left")


def cmd_demo() -> None:
    rt = Runtime()
    scns = {s["id"]: s for s in corpus.scenarios()}
    for sid in ("OK-1", "EXFIL-1"):
        s = scns[sid]
        print(f"\n=== {sid}: {s['title']} ({s['class']}) ===")
        for arm in (Arm.A, Arm.C):
            sr, ent, tx = rt.run_scenario(s, arm)
            comp, reasons = oracle.judge(ent, tx)
            print(f"  arm {arm.value}: model_manipulated={sr.model_manipulated}  "
                  f"system_compromised={comp}")
            for a in sr.actions:
                if a.hostile or a.final != 'executed':
                    print(f"     - {a.tool:<28} {a.final}")
            for r in reasons:
                print(f"       ! {r}")


def cmd_freeze() -> None:
    from redteam import freeze
    note = sys.argv[2] if len(sys.argv) > 2 else "freeze before the recorded run"
    p = freeze.freeze(note)
    print(f"frozen -> {p}")


def cmd_proof() -> None:
    from redteam import proofpack
    rid = sys.argv[2] if len(sys.argv) > 2 else "2026-10-07-recorded"
    d = proofpack.record(rid)
    print(f"recorded -> {d}")
    print((d / "summary.md").read_text())


def cmd_verify() -> int:
    from redteam import proofpack
    rid = sys.argv[2] if len(sys.argv) > 2 else None
    return 0 if proofpack.verify(rid) else 1


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scenarios"
    if cmd == "verify":
        return cmd_verify()
    {"scenarios": cmd_scenarios, "matrix": cmd_matrix, "demo": cmd_demo, "ablation": cmd_ablation,
     "freeze": cmd_freeze, "proof": cmd_proof}.get(cmd, cmd_scenarios)()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
