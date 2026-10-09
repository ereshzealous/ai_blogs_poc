"""hitl: the T3 command line.

    hitl demo                    the incident end to end, printed step by step
    hitl scenarios [H5c …]       the protocol scenarios under arms A, B, C, printed (no evidence written)
    hitl suite                   the 30 conformance tests of arm C (no evidence written)
    hitl freeze --note …         freeze the preregistration, checks, config and fixtures (proof/FREEZE.json)
    hitl proof [--run-id ID]     H1–H9 × A/B/C + conformance + API round trip -> evidence/runs/<ID>/ (pae-proof/v1)
    hitl verify [ID]             PROOF VERIFICATION of a run (default: the published run)
    hitl promote ID --reason …   make ID the published run (refuses unless it verifies)
    hitl serve [--port 8787]     the HTTP API and the approval inbox
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

RUN = "2026-10-03-protocol"


def demo() -> None:
    from hitl.contracts import DecisionRequest
    from hitl.platform import Platform
    from hitl.suite import EVENT

    P = Platform(Path(tempfile.mkdtemp(prefix="hitl-demo-")))
    r = P.receive("tok-monitor", dict(EVENT))
    pid = r["proposals"][0]["proposal_id"]
    p = P.approvals.get(pid)["proposal"]
    print(f"1. monitor event → {r['correlation_id']}: evidence read, analysed, incident {r['incident']} opened (all automatic)")
    print(f"2. proposal {pid}: {p.capability}({p.target.service}, {p.target.environment}, {p.arguments}) risk={p.risk}")
    print(f"   policy {p.policy.policy_id} v{p.policy.version}: {p.policy.decision} ({p.policy.rule}); digest {p.action_digest[:16]}…")
    print(f"3. gate before approval: {P.execute_proposal(pid).code}")
    for who in ("tok-agent", "tok-dana", "tok-reggie"):
        P.clock.advance(30)
        try:
            P.approvals.decide(pid, who, DecisionRequest(decision="approve", action_digest=p.action_digest))
        except Exception as e:  # noqa: BLE001
            print(f"4. {who[4:]} tries to approve: {e}")
    P.clock.advance(60)
    d = P.approvals.decide(pid, "tok-alice", DecisionRequest(decision="approve", action_digest=p.action_digest, reason="v4.18.0 correlation reviewed"))
    print(f"5. alice approves the exact digest → {d.approval_id}")
    r = P.execute_proposal(pid)
    print(f"6. resume: revalidated {sum(c['ok'] for c in r.checks)}/{len(r.checks)} checks → {r.code}")
    print(f"7. replay of the same approval: {P.execute_proposal(pid).code}")
    print(f"8. rollbacks in the deployment system: {P.ent.effect_count('rollback')}; audit chain intact: {P.audit.verify()[0]}")
    print("   the 37-minute story under all three approval protocols: uv run hitl scenarios H5c")


def scenarios(only: list[str]) -> int:
    from hitl.scenarios import run_all
    outs = run_all(Path(tempfile.mkdtemp(prefix="hitl-scen-")), only=only or None)
    for (sid, arm), o in outs.items():
        m = o.metrics
        print(f"{sid} {arm}  {(m.get('final_code') or o.error or ''):<26} writes={m.get('writes')} unauthorized={m.get('unauthorized_executions')} "
              f"ineligible={m.get('ineligible_approver_acceptances')} reapproval={m.get('reapproval_requests')}")
    return 0 if all(o.error is None for o in outs.values()) else 1


def suite() -> int:
    from hitl.suite import run_suite
    outs = run_suite(Path(tempfile.mkdtemp(prefix="hitl-suite-")))
    for o in outs:
        bad = [k for k, v in o.assertions.items() if not v["held"]]
        print(f"{o.id}  {'PASS' if o.passed else 'FAIL'}  {o.name}" + (f"   failed: {bad or o.error}" if not o.passed else ""))
    n = sum(o.passed for o in outs)
    print(f"\n{n}/{len(outs)} conformance tests passed")
    return 0 if n == len(outs) else 1


def main() -> None:
    ap = argparse.ArgumentParser(prog="hitl")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    sub.add_parser("suite")
    sc = sub.add_parser("scenarios")
    sc.add_argument("only", nargs="*")
    fz = sub.add_parser("freeze")
    fz.add_argument("--note", required=True)
    pr = sub.add_parser("proof")
    pr.add_argument("--run-id", default=RUN)
    v = sub.add_parser("verify")
    v.add_argument("run_id", nargs="?")
    pm = sub.add_parser("promote")
    pm.add_argument("run_id")
    pm.add_argument("--reason", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8787)
    a = ap.parse_args()
    if a.cmd == "demo":
        demo()
    elif a.cmd == "suite":
        raise SystemExit(suite())
    elif a.cmd == "scenarios":
        raise SystemExit(scenarios(a.only))
    elif a.cmd == "freeze":
        from hitl.freeze import freeze
        print("frozen:", freeze(a.note))
    elif a.cmd == "proof":
        from hitl.proofpack import build
        run = build(a.run_id)
        print((run / "summary.md").read_text())
    elif a.cmd == "verify":
        from hitl.verify import verify
        r = verify(a.run_id)
        print(r.text())
        raise SystemExit(0 if r.verified else 1)
    elif a.cmd == "promote":
        from hitl.proofpack import promote
        print("published:", promote(a.run_id, a.reason))
    elif a.cmd == "serve":
        from hitl.api import serve
        serve(a.port)


if __name__ == "__main__":
    main()
