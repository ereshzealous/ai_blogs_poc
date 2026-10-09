"""Development smoke run: scenarios x arms into var/smoke/, one summary line each (not evidence)."""
import json
import shutil
import sys
from pathlib import Path

from recovery.common import scenarios
from recovery.harness import run_one

sc = {s["id"]: s for s in scenarios()}
base = Path("var/smoke")
ids = sys.argv[1].split(",")
arms = sys.argv[2].split(",") if len(sys.argv) > 2 else ["A0", "A1", "A2"]
for sid in ids:
    for arm in arms:
        shutil.rmtree(base / sid / arm, ignore_errors=True)
        r = run_one(base / sid / arm, sc[sid], arm)
        led = json.load(open(base / sid / arm / "world/ledger.json"))
        evs = [json.loads(l) for l in open(base / sid / arm / "events.jsonl")]
        ans = [e for e in evs if e["kind"] == "answer"][-1]
        dec = [(e["failure_class"], e["certainty"], e["action"]) for e in evs if e["kind"] == "decision"]
        open_t = sum(t["status"] == "OPEN" for t in led["tickets"])
        print(sid, arm, [x["exit"] for x in r["exits"]], "cr", len(led["credits"]), "tk", open_t, "nt", len(led["notifications"]),
              ans.get("status"), ans.get("claims"), dec, [x["stderr_tail"] for x in r["exits"] if x["stderr_tail"]])
