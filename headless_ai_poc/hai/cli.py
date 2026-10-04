"""hai: the F3 command line.

    hai demo                         one monitoring event, end to end, printed step by step
    hai experiments [--run-id ID]    the seven experiments -> runs/<ID>/
    hai verify [ID] [--check]        EVIDENCE VERIFICATION of a recorded run (default: runs/PUBLISHED); exit 1 unless VERIFIED
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path


def demo() -> None:
    from hai import payloads as P
    from hai.experiments import Lab
    from hai.heads import render

    base = Path(tempfile.mkdtemp(prefix="hai-demo-"))
    lab = Lab(base, "demo")
    print("1. Datadog-style monitor fires: payment-service error rate 14% (production)")
    r = lab.send("event", "tok-monitoring", P.monitor_alert())
    v = lab.rt.view(r.execution_id)
    print(f"   ingress: 202 Accepted -> {r.execution_id}; worker ran it to {v.status}")
    ident = lab.rt._load(v.execution_id)["state"]["identity"]
    print(f"2. execution identity: invoker={ident['invoker']} agent={ident['agent']} workload={ident['workload']}")
    print(f"   scopes={ident['scopes']}  (no deploy:rollback: invocation is not authorization)")
    print("3. what the chat head shows an engineer who asks now:")
    tok, m = P.chat_message()
    print("   " + render.chat(lab.send("chat", tok, m)).replace("\n", "\n   "))
    ok, why, fin = lab.approve(v, who="sre.maya")
    print(f"4. sre.maya tries to approve: {why}")
    ok, why, fin = lab.approve(v, who="ic.dev")
    print(f"5. ic.dev approves the exact call: {why}; status {fin.status}; action {fin.action['output']}")
    print("6. audit, from the audit chain alone:")
    print("   " + json.dumps(lab.rt.audit.answer(v.execution_id)["which_approval"]))
    print(f"   chain intact: {lab.rt.audit.verify()[0]}; physical rollbacks in the deploy system: {lab.effects('deploy.rollback')}")
    shutil.rmtree(base, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(prog="hai")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    e = sub.add_parser("experiments")
    e.add_argument("--run-id", default=None, help="default: the run named in runs/PUBLISHED")
    v = sub.add_parser("verify")
    v.add_argument("run_id", nargs="?")
    v.add_argument("--check", action="store_true", help="read-only: do not write runs/verification/")
    a = ap.parse_args()
    if a.cmd == "demo":
        demo()
    elif a.cmd == "verify":
        from hai.verify import verify
        raise SystemExit(0 if verify(a.run_id, write=not a.check) else 1)
    else:
        from hai.experiments import run
        from hai.verify import published
        out = run(a.run_id or published())
        print((out / "summary.md").read_text())


if __name__ == "__main__":
    main()
