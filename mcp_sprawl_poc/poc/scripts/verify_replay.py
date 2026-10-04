"""Replay recorded rows WITHOUT the model and verify they reproduce the recorded outcome.

    uv run python scripts/verify_replay.py ../experiment/raw/blind-main --out ../experiment/recorded-run/replay-check \
        --cases BL-C03-1 BL-C07-1 BL-C08-1 BL-C10-1 BL-C14-2 --sizes 500 --arms A B C

The recorded model responses are fed back in order (RecordedChat).  Everything downstream of the
model — real MCP server processes, retrieval, binding, provenance, policy, approval, gateway,
simulated systems, ledger, scoring — runs again for real.  A row reproduces if its ledger
effects, declared outcome and correctness match the recorded row.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def effects_key(effects):
    return sorted((e["server"], e["tool"], e["environment"], e["effect_type"], e["entity_id"], e["amount"],
                   json.dumps({k: v for k, v in (e.get("payload") or {}).items() if k not in ("refund_id", "credit_id", "rma_id", "replacement_order_id")}, sort_keys=True))
                  for e in effects)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cases", nargs="+", required=True)
    ap.add_argument("--sizes", nargs="+", default=["500"])
    ap.add_argument("--arms", nargs="+", default=["A", "B", "C"])
    ns = ap.parse_args()
    src, out = Path(ns.source).resolve(), Path(ns.out).resolve()
    cmd = [sys.executable, "-m", "sprawl_poc.bench.runner", "--split", "blind", "--replay", str(src), "--out", str(out),
           "--sizes", *ns.sizes, "--arms", *ns.arms, "--cases", *ns.cases]
    subprocess.run(cmd, cwd=HERE, check=True)
    original = {json.loads(l)["row_id"]: json.loads(l) for l in (src / "rows.jsonl").read_text().splitlines() if l.strip()}
    report = []
    for line in (out / "rows.jsonl").read_text().splitlines():
        r = json.loads(line)
        o = original[r["row_id"]]
        same = {
            "effects": effects_key(r["effects"]) == effects_key(o["effects"]),
            "declared_outcome": r["declared_outcome"] == o["declared_outcome"],
            "correct": (r.get("score") or {}).get("correct") == (o.get("score") or {}).get("correct"),
        }
        report.append({"row_id": r["row_id"], "reproduced": all(same.values()), **same,
                       "replay_request_mismatches": r.get("replay_request_mismatches")})
    ok = sum(x["reproduced"] for x in report)
    (out / "replay-verification.json").write_text(json.dumps({"reproduced": ok, "rows": len(report), "detail": report}, indent=2))
    print(f"replay reproduced {ok}/{len(report)} rows")
    for x in report:
        print(("OK  " if x["reproduced"] else "DIFF"), x["row_id"], "request-hash mismatches:", x["replay_request_mismatches"])


if __name__ == "__main__":
    main()
