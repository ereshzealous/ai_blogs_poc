"""One-screen summaries that ./sprawl prints after a step.

    python scripts/summarize.py run DIR       rows, correct, unsafe proposals and executions per cell of a live run
    python scripts/summarize.py replay DIR    did every replayed row reproduce? (exit 1 if not)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from doctor import FAIL, OK, ROOT, WARN  # noqa: E402


def run(out: Path) -> int:
    rows = [json.loads(l) for l in (out / "rows.jsonl").read_text().splitlines() if l.strip()]
    cells: dict[str, list] = {}
    for r in rows:
        cells.setdefault(f"{r['arm_key']}@{r['estate_size']}", []).append(r)
    print(f"\n  {'cell':<8}{'rows':>6}{'correct':>10}{'unsafe prop.':>14}{'unsafe exec.':>14}")
    for k in sorted(cells):
        rs = cells[k]
        s = lambda key: sum(bool((r.get("score") or {}).get(key)) for r in rs)  # noqa: E731
        print(f"  {k:<8}{len(rs):>6}{s('correct'):>10}{s('unsafe_proposal'):>14}{s('unsafe_execution'):>14}")
    return 0


def replay(out: Path) -> int:
    ver = out / "replay-verification.json"
    if not ver.exists():
        return 1
    v = json.loads(ver.read_text())
    mism = sum(d.get("replay_request_mismatches") or 0 for d in v.get("detail", []))
    good = v["reproduced"] == v["rows"]  # the SEMANTIC replay contract: request-hash key order may differ, outcomes may not
    where = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"  {OK if good else FAIL} {v['reproduced']}/{v['rows']} rows reproduced (effects, declared outcome, verdict); "
          f"{mism} request mismatches  ->  {where}")
    if mism:
        print(f"  {WARN} request-hash mismatches are reported, not failed: recorded tool arguments replay with sorted keys "
              "(experiment/recorded-run/replay-r2/README.md); the run comparison classifies them as volatile")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit({"run": run, "replay": replay}[sys.argv[1]](Path(sys.argv[2]).resolve()))
