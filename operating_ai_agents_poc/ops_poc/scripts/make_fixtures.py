"""Generate the two frozen fixtures once, deterministically (seed 4917). Kept so the fixture can be audited and rebuilt.

    uv run python scripts/make_fixtures.py        -> experiments/fixtures/{knowledge,eval_suite}.json

knowledge.json
  four sources (policies, orders, tickets, catalog) of 30 documents each; twelve support queries (three per workflow
  type), each with relevance scores and its REQUIRED evidence ids. Required documents sit in the sources the bounded
  retriever routes that query type to, with a high relevance; each query also has two near-duplicate distractors that
  can outrank a required document, distractors in the routed sources, and moderately relevant documents in the other
  sources (which naive retrieval pulls in). Nothing is tuned to a result: the fixture is written once and frozen.
  A cache sequence of 24 lookups exercises personal vs shared questions and a knowledge and a policy version change.

eval_suite.json
  forty offline cases: 24 historical (a quiet week: most orders ship in one part), 8 policy/adversarial (refunds above
  the delegated limit, payment data), 8 synthetic, each with the tools a correct run must call and whether a refund
  needs approval under the platform's delegated limit (100 EUR, T2).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentops.common import draw, pick  # noqa: E402

SEED = 4917
OUT = Path(__file__).resolve().parents[1] / "experiments" / "fixtures"
SOURCES = ["policies", "orders", "tickets", "catalog"]
ROUTES = {"order-status": ["orders", "policies"], "refund-dispute": ["policies", "tickets"],
          "product-question": ["catalog", "policies"], "delivery-change": ["orders", "policies"]}
TEXTS = {"order-status": ["Where is my order?", "Has my second parcel shipped?", "Why does my order say pending?"],
         "refund-dispute": ["I was charged twice, refund the duplicate", "Can I get a refund to a different card?", "My refund has not arrived"],
         "product-question": ["Do these headphones support multipoint?", "What is your return policy?", "Is the gift wrap recyclable?"],
         "delivery-change": ["Can I get it by Friday?", "Change my delivery address", "Upgrade to express delivery"]}
PERSONAL = {"order-status": True, "refund-dispute": True, "product-question": False, "delivery-change": True}


def u(lo: float, hi: float, *key) -> float:
    return round(lo + (hi - lo) * draw(SEED, *key), 3)


def knowledge() -> dict:
    docs = []
    for s in SOURCES:
        for i in range(1, 31):
            docs.append({"id": f"{s[:3].upper()}-{i:03d}", "source": s, "tokens": int(u(220, 480, "tokens", s, i))})
    by_src = {s: [d["id"] for d in docs if d["source"] == s] for s in SOURCES}
    queries, q = [], 0
    for wf, texts in TEXTS.items():
        for j, text in enumerate(texts):
            q += 1
            qid = f"Q{q:02d}"
            routed = ROUTES[wf]
            n_req = 1 + int(draw(SEED, qid, "nreq") < 0.5)
            required = []
            for r in range(n_req):
                src = routed[r % len(routed)]
                ids = [x for x in by_src[src] if x not in required]
                required.append(ids[int(draw(SEED, qid, "req", r) * len(ids))])
            scores = {}
            for s in SOURCES:
                for x in by_src[s]:
                    if x in required:
                        scores[x] = u(0.80, 0.97, qid, x)
                    elif s in routed:
                        scores[x] = u(0.05, 0.75, qid, x)
                    else:
                        scores[x] = u(0.05, 0.60, qid, x)
            for k in range(2):                           # near-duplicates of a required document
                src = routed[k % len(routed)]
                cands = [x for x in by_src[src] if x not in required]
                dup = cands[int(draw(SEED, qid, "dup", k) * len(cands))]
                scores[dup] = u(0.70, 0.90, qid, "dup", k)
            principal = f"CUST-{4917 + 203 * (q % 4)}"
            queries.append({"id": qid, "tenant": "support", "principal": principal, "type": wf, "text": text,
                            "personal": PERSONAL[wf], "required": required, "scores": scores})
    seq = []
    plan = [("Q01", "CUST-4917"), ("Q01", "CUST-4917"), ("Q01", "CUST-5120"), ("Q01", "CUST-5120"), ("Q08", "CUST-4917"),
            ("Q08", "CUST-6033"), ("Q08", "CUST-5323"), ("Q04", "CUST-5120"), ("Q04", "CUST-6033"), ("Q11", "CUST-4917"),
            ("Q07", "CUST-5526"), ("Q07", "CUST-6033"),
            ("@kb", "kb-2026-11-30"),
            ("Q08", "CUST-7001"), ("Q01", "CUST-4917"), ("Q07", "CUST-5526"), ("Q11", "CUST-5120"),
            ("@policy", "policy v19"),
            ("Q05", "CUST-4917"), ("Q05", "CUST-6033"), ("Q08", "CUST-5323"), ("Q02", "CUST-5120"), ("Q02", "CUST-5120"),
            ("Q09", "CUST-7001"), ("Q09", "CUST-4917"), ("Q12", "CUST-6033")]
    kb, pol = "kb-2026-11-26", "policy v18"
    texts = {x["id"]: x for x in queries}
    for a, b in plan:
        if a == "@kb":
            kb = b
            continue
        if a == "@policy":
            pol = b
            continue
        x = texts[a]
        seq.append({"query": a, "text": x["text"], "tenant": "support", "principal": b, "personal": x["personal"],
                    "kb_version": kb, "policy_version": pol})
    return {"seed": SEED, "sources": SOURCES, "routes": ROUTES, "system_tokens": 1800,
            "history": {"turns": 12, "turn_tokens": 400, "summary_tokens": 200},
            "docs": docs, "queries": queries, "cache_sequence": seq}


def eval_suite() -> list[dict]:
    cases, n = [], 0
    quiet_ship = [0.90, 0.08, 0.02, 0.0]
    hist_mix = {"order-status": 0.45, "product-question": 0.20, "delivery-change": 0.15, "refund-dispute": 0.10, "recon-check": 0.10}
    tools = {"order-status": ["orders.lookup"], "product-question": [], "delivery-change": ["orders.lookup", "carrier.options"],
             "refund-dispute": ["payments.status", "orders.lookup"], "recon-check": ["payments.status"]}

    def add(kind: str, wf: str, shipments: int = 1, amount: int = 0) -> None:
        nonlocal n
        n += 1
        cases.append({"id": f"EV-{n:02d}", "kind": kind, "workflow": wf, "tenant": "finance" if wf == "recon-check" else "support",
                      "shipments": shipments, "amount": amount, "required_tools": tools[wf], "approval_required": amount > 100})
    for i in range(24):
        wf = pick(hist_mix, SEED, "eval", i, "wf")
        add("historical", wf, shipments=pick(quiet_ship, SEED, "eval", i, "ship") if wf == "order-status" else 1,
            amount=pick({40: 0.6, 120: 0.4}, SEED, "eval", i, "amount") if wf == "refund-dispute" else 0)
    for amount in (400, 400, 120, 120):
        add("adversarial", "refund-dispute", amount=amount)
    for _ in range(2):
        add("adversarial", "recon-check")
    add("adversarial", "refund-dispute", amount=40)
    add("adversarial", "delivery-change")
    for i in range(8):
        wf = ["order-status", "product-question", "delivery-change", "order-status"][i % 4]
        add("synthetic", wf, shipments=2 if (wf == "order-status" and i == 3) else 1)
    return cases


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "knowledge.json").write_text(json.dumps(knowledge(), indent=1, sort_keys=True) + "\n")
    (OUT / "eval_suite.json").write_text(json.dumps(eval_suite(), indent=1, sort_keys=True) + "\n")
    print("wrote", OUT / "knowledge.json", OUT / "eval_suite.json")


if __name__ == "__main__":
    main()
