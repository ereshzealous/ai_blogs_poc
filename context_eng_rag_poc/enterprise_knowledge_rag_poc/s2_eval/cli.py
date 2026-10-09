"""The reader's command line.

    uv run python -m s2_eval.cli demo                 # INC-4917, naive vs governed, re-executed from the published tape (no model)
    uv run python -m s2_eval.cli explain H-K12        # one recorded case: candidates, gate decisions, packet, answers
    uv run python -m s2_eval.cli ask --as ananya.iyer --env production "question"   # live (Ollama) or --scripted
"""

from __future__ import annotations

import argparse
import json
import textwrap

from knowledge_rag.capability import KnowledgeCapability
from knowledge_rag.contracts import KnowledgeRequest
from knowledge_rag.generate import ModelClient
from knowledge_rag.pipeline import GOVERNED, NAIVE, run
from knowledge_rag.util import ROOT, config
from s2_eval.common import load_cases, request, retriever, world

RUNS = ROOT / "runs"


def published() -> str:
    return (RUNS / "PUBLISHED").read_text().strip()


def show(res: dict, label: str) -> None:
    print(f"\n── {label} " + "─" * (100 - len(label)))
    print(f"context: {len(res['packed']['entries'])} units, {res['context_tokens_est']} estimated tokens")
    for e in res["packed"]["entries"]:
        print(f"   {e['eid']:4} {e['unit_id']:52} {e.get('role') or '':14}{' (cut)' if e['truncated'] else ''}")
    ex = [c for c in res["candidates"] if c["decision"] == "excluded"]
    if ex:
        print(f"excluded by the gates: {len(ex)}")
        for c in ex[:12]:
            print(f"   {c['unit_id']:52} {c['gate']:13} {c['reason'][:70]}")
    a = res.get("final_answer") or {}
    ra = a.get("recommended_action", {})
    print(f"answer: {a.get('status')} · action {ra.get('action')} · target {ra.get('target') or '—'} · approval {'required' if ra.get('approval_required') else 'not stated'}")
    for line in textwrap.wrap(a.get("summary", ""), 100):
        print("   " + line)
    for n in res.get("binding_notes", []):
        print(f"   binding: {n[:110]}")


def demo(args) -> None:
    run_id = published()
    w = world()
    retr = retriever(RUNS / run_id / "tape" / "query_embeddings.jsonl", "replay")
    model = ModelClient(config("models.yaml")["primary"], "replay", RUNS / run_id / "tape" / "model.jsonl")
    case = next(c for c in load_cases("heldout") if c["case_id"] == "H-K9")
    print(f"INC-4917 · {case['question']}\nasked by {case['principal']} · re-executed from the tape of run {run_id} (no model)")
    seed = config("models.yaml")["primary"]["seeds"][0]
    for ctl, label in ((NAIVE, "NAIVE · vector top 8, cut at the budget"), (GOVERNED, "GOVERNED · recheck, gates, packet, verifier")):
        res = run(request(case, w), ctl, retr, w, model, seed)
        show(res, label)


def explain(args) -> None:
    run_id = published()
    for line in (RUNS / run_id / "d.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["case_id"] == args.case and r["seed"] == args.seed:
            show(r, f"{r['arm'].upper()} · {args.case} · seed {args.seed} · run {run_id}")
            print(f"   score: correct={r['score']['final']['correct']} facts={r['score']['final']['facts']} leaks={r['score']['final']['leaks']}")


def ask(args) -> None:
    w = world()
    from pathlib import Path
    tape = Path(args.tape) if args.tape else RUNS / "ask" / "tape"
    retr = retriever(tape / "query_embeddings.jsonl", "record")
    model = ModelClient(config("models.yaml")["primary"], "scripted" if args.scripted else "live", tape / "model.jsonl")
    cap = KnowledgeCapability(w, retr, model)
    view = cap.answer(KnowledgeRequest(request_id="cli-1", channel="api", invoker=args.principal, environment=args.env,
                                       question=args.question, budget_tokens=config("retrieval.yaml")["budget"]["tokens"], correlation_id="cli"))
    print(json.dumps(view, indent=1, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser(prog="s2_eval.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    e = sub.add_parser("explain")
    e.add_argument("case")
    e.add_argument("--seed", type=int, default=config("models.yaml")["primary"]["seeds"][0])
    a = sub.add_parser("ask")
    a.add_argument("question")
    a.add_argument("--as", dest="principal", default="ananya.iyer")
    a.add_argument("--env", default="production", choices=["production", "staging"])
    a.add_argument("--scripted", action="store_true")
    a.add_argument("--tape", default="")
    args = ap.parse_args()
    {"demo": demo, "explain": explain, "ask": ask}[args.cmd](args)


if __name__ == "__main__":
    main()
