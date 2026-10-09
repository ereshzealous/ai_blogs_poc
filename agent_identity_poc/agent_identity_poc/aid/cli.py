"""aid: the T1 command line.

    aid demo                         the payment-service rollback, with every identity in the chain printed
    aid experiments [--run-id ID]    the seven experiments -> runs/<ID>/ (refuses if a frozen file changed)
    aid freeze --note "…"            freeze the declared checks, config and criteria code -> proof/FREEZE.json
"""

from __future__ import annotations

import argparse
import json


def demo() -> None:
    from aid.story import story

    s = story()
    t = s["token"]
    print("1. 14:02  Datadog monitor fires: payment-service error rate 14% (production); nobody is typing")
    print(f"2. token exchange: sub={t['sub']} on_behalf_of={t['on_behalf_of']} act={t['act']} cnf={t['cnf']}")
    print(f"   scopes={t['scopes']}  (no deploy:rollback: it never travels in a token)")
    for r in s["reads"]:
        print(f"   {r['capability']:16s} {r['effect']:9s} as {r['tool_principal'] or '-'}")
    print(f"3. 14:09  rollbackDeployment -> {s['rollback_request']['effect']} ({s['rollback_request']['reason']})")
    print(f"   sre.maya tries to approve: {s['approval_attempts']['sre.maya']}")
    print(f"   ic.dev approves the exact call: {s['approval_attempts']['ic.dev']}")
    print(f"4. rollback {s['rollback']['effect']}; Kubernetes saw {s['rollback']['tool_principal']}")
    print(f"5. Kubernetes' own audit log: {json.dumps(s['kubernetes_entry'])}")
    print("6. the platform's audit record: " + json.dumps(s["platform_record"], indent=1).replace("\n", "\n   "))
    print(f"   chain intact: {s['chain_intact']}; physical rollbacks: {s['physical_rollbacks']}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="aid")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    e = sub.add_parser("experiments")
    e.add_argument("--run-id", default="2026-10-03-recorded")
    fz = sub.add_parser("freeze")
    fz.add_argument("--note", required=True)
    a = ap.parse_args()
    if a.cmd == "demo":
        demo()
    elif a.cmd == "freeze":
        from aid.freeze import freeze
        print("frozen:", freeze(a.note))
    else:
        from aid.experiments import run
        out = run(a.run_id)
        print((out / "summary.md").read_text())


if __name__ == "__main__":
    main()
