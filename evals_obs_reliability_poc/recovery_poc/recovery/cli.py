"""recovery: the POC's command line.

    recovery demo                         the flagship (S09) through the naive and the classified runtime, explained
    recovery scenario S16 --arm A2        any scenario through any runtime, explained (--mutant X1, --model-change scripted-v2)
    recovery explain <run-dir> S09 A2     explain a recorded run from its files (no execution)
    recovery prereg-check                 the frozen files are unchanged
    recovery record --run-id <id> [--live]
    recovery aggregate --run-id <id>
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .common import POC, prereg_check, read_json, read_jsonl, scenarios, tools
from .evals import CHECKS, TITLE, evaluate
from .harness import run_one

NAMES = {"A0": "naive (catch -> retry)", "A1": "idempotent-retry", "A2": "classified (evidence -> certainty -> matrix)"}
TOOLS = tools()


def explain(d: Path, sc: dict, arm: str, out=print) -> dict:
    e = evaluate(d, sc, arm)
    ev = read_jsonl(d / "events.jsonl")
    led = read_json(d / "world" / "ledger.json")
    rid = next((x for x in ev if x["kind"] == "worker.start"), {})
    out(f"\nRUN  {sc['id']} · {sc['title']}\n     runtime {arm}: {NAMES[arm]}   trace {rid.get('trace_id', '?')[:16]}")
    out("")
    n = 0

    def line(tag, text):
        nonlocal n
        n += 1
        out(f"[{n:>2}] {tag:<17} {text}")

    for x in ev:
        k = x["kind"]
        if k == "worker.start" and x.get("resumed"):
            line("WORKER", f"{x['worker']} resumed at step '{x['step']}' (same trace)" if arm != "A0" else f"{x['worker']} restarted at '{x['step']}' (new trace)")
        elif k == "retrieval":
            line("RETRIEVAL", ", ".join(f"{d['id']} ({d['score']})" for d in x["documents"]))
        elif k == "model.call":
            u = x.get("usage") or {}
            line("MODEL_CALL", f"{x['model']} · {u.get('input_tokens', '?')} in / {u.get('output_tokens', '?')} out tokens")
        elif k == "model.proposal":
            a = x["arguments"]
            line("MODEL", f"{x['tool']} {a.get('charge_id', '')} {a.get('amount', '')}".strip())
        elif k == "gate.validate":
            line("VALIDATE", "OK" if x["ok"] else f"REJECTED · {x['failure_class']}: {x['detail']}")
        elif k == "policy.decision":
            line("AUTHORIZATION", f"{x['effect']} {x['decision_id']} ({x['policy_version']}{', rule ' + x['rule'] if x['rule'] else ''})")
        elif k == "tool.dispatch":
            line("TOOL_REQUEST", f"{x['tool']} SENT · op {x['operation_id']} · attempt {x['attempt_id']} · key {x['idempotency_key'] or 'none'}")
        elif k == "crash.injected":
            line("CRASH", f"SIGKILL {x['step']} {x['tool']}")
        elif k == "tool.read":
            line("TOOL_READ", f"{x['tool']} OK ({x['charges']} charges)")
        elif k == "failure" and x.get("failure_class") in ("RECONCILED", "DUPLICATE_EFFECT", "RECONCILE_FAILED"):
            out(f"     Reconciled {x['failure_class']} · certainty {x['execution_certainty']}  ({x['certainty_rule']}: {x['certainty_basis']})")
        elif k == "failure" and "failure_class" in x:
            out(f"\n     Failure classification ({x['step']})")
            out(f"       class      {x['failure_class']}   layer: {x['layer']}")
            if x.get("request_sent") is None and x.get("evidence"):
                out("       evidence   journal: " + " ".join(f"{k}={v}" for k, v in x["evidence"].items()))
            elif x.get("request_sent") is not None:
                out(f"       evidence   request_sent={x.get('request_sent')} response_received={x.get('response_received')} "
                    f"transport={x.get('transport')} status={x.get('http_status')}")
            out(f"       certainty  {x['execution_certainty']}  ({x['certainty_rule']}: {x['certainty_basis']})")
            if x.get("side_effect") == "EXTERNAL_WRITE" and x["step"] in ("credit", "ticket", "notify"):
                t = TOOLS[{"credit": "issue_credit", "ticket": "create_ticket", "notify": "send_notification"}[x["step"]]]
                out(f"       contract   effect {t['effect']} · idempotency {t['idempotency']} · status query {t['status_query']} · undo {t['compensation']}")
        elif k == "failure":
            line("FAILURE", f"{x['step']}: failed=true · {x['error']}  (attempt {x['attempt']})")
        elif k == "decision":
            out(f"     Recovery   {x['action']}  (rule {x['rule']}: {x['why']})\n")
        elif k == "reconcile":
            line("RECONCILE", f"ask the system of record about {x['operation_id']} -> {x['result']} {x['certainty']} (found {x['found']})")
        elif k == "compensate":
            line("COMPENSATE", f"void {x['voided']}")
        elif k == "answer":
            out(f"\n     Final      {x['status']} · " + " · ".join(f"{s} {c}" for s, c in x["claims"].items()))
    eff = e["effects"]
    out(f"     Ledgers    credits {eff['credits_total']} · open tickets {eff['tickets']} · notifications {eff['notifications']}"
        f"   (oracle: {sc['effects']})")
    out("\n     Eval checks")
    for c in CHECKS:
        r = e["checks"][c]
        if r["result"] != "NA":
            out(f"       {c:<4} {r['result']:<4} {TITLE[c]}{'  -> ' + r['detail'] if r['result'] == 'FAIL' else ''}")
    return e


def run_and_explain(sid: str, arm: str, mutant=None, model_change=None, live: bool = False) -> dict:
    sc = {s["id"]: s for s in scenarios()}[sid]
    d = POC / "var" / "demo" / sid / (arm + (f"-{mutant}" if mutant else "") + (f"-{model_change}" if model_change else "") + ("-live" if live else ""))
    shutil.rmtree(d, ignore_errors=True)
    run_one(d, sc, arm, mutant=mutant, model_change=model_change, live="record" if live else None)
    if live:
        print(f"model answers taped to {d.relative_to(POC)}/model-tape.jsonl")
    return explain(d, sc, arm)


def main() -> None:
    ap = argparse.ArgumentParser(prog="recovery")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    s = sub.add_parser("scenario")
    s.add_argument("id")
    s.add_argument("--arm", default="A2")
    s.add_argument("--mutant")
    s.add_argument("--model-change")
    s.add_argument("--live", action="store_true", help="a real model decides (Ollama: qwen3:8b, fallback llama3.1)")
    x = sub.add_parser("explain")
    x.add_argument("run_dir")
    x.add_argument("id")
    x.add_argument("arm")
    sub.add_parser("prereg-check")
    sub.add_parser("list")
    o, rest = ap.parse_known_args()
    if o.cmd == "demo":
        print("THE FLAGSHIP: the credit commits, the response is lost, the agent sees a timeout.")
        a0 = run_and_explain("S09", "A0")
        a2 = run_and_explain("S09", "A2")
        print(f"\nSame fault. Naive runtime: {a0['effects']['credits_total']} credits. Classified runtime: {a2['effects']['credits_total']} credit.")
    elif o.cmd == "scenario":
        run_and_explain(o.id, o.arm, o.mutant, o.model_change, o.live)
    elif o.cmd == "explain":
        sc = {s["id"]: s for s in scenarios()}[o.id]
        base = Path(o.run_dir)
        explain(base / "scenarios" / o.id / o.arm if (base / "scenarios").exists() else base, sc, o.arm)
    elif o.cmd == "list":
        for s in scenarios():
            print(f"{s['id']}  {s['layer']:<34} {s['title']}")
    elif o.cmd == "prereg-check":
        p = prereg_check()
        print("preregistration unchanged since the freeze" if not p else "CHANGED:\n  " + "\n  ".join(p))
        sys.exit(1 if p else 0)


if __name__ == "__main__":
    main()
