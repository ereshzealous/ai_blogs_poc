"""Quick console view of a run's rows (not a publication surface).

    python -m coord.report <run-id>
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict

from coord.util import ROOT

CONJ = ["rc_ok", "evidence_ok", "remediation_ok", "prohibited_ok", "approval_ok", "outcome_ok"]


def main(argv: list[str] | None = None) -> None:
    run_id = (argv or sys.argv[1:])[0]
    rows = [json.loads(line) for line in (ROOT / "runs" / run_id / "rows.jsonl").read_text().splitlines()]
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        e, m = r["eval"], r["metrics"]
        by[r["arch"]].append(r)
        fails = [k for k in CONJ if not e[k]]
        print(f"{r['fixture']:3} {r['arch']} r{r['repeat']} {'ok  ' if e['success'] else 'FAIL'} {e['outcome']:13} {str(e['category']):22} "
              f"{m['termination']:15} {m['latency_ms'] / 1000:6.0f}s tok={m['tokens_total']:6} llm={m['llm_calls']:3} tools={m['tool_calls']:3} "
              f"dup={m['duplicate_tool_calls']:2} hand={m['handoffs']:2} {fails}")
    print()
    for arch, rs in sorted(by.items()):
        n = len(rs)
        ok = sum(r["eval"]["success"] for r in rs)
        lat = sorted(r["metrics"]["latency_ms"] for r in rs)
        tok = sorted(r["metrics"]["tokens_total"] for r in rs)
        print(f"{arch}: success {ok}/{n}  median latency {lat[n // 2] / 1000:.0f}s  median tokens {tok[n // 2]}")


if __name__ == "__main__":
    main()
