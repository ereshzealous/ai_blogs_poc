"""Development: run A2 mutants over chosen scenarios into var/mutants/ and show which checks fail (not evidence)."""
import shutil
import sys
from pathlib import Path

from recovery.common import scenarios
from recovery.evals import CHECKS, evaluate
from recovery.harness import run_one

sc = {s["id"]: s for s in scenarios()}
muts = sys.argv[1].split(",")
ids = sys.argv[2].split(",") if len(sys.argv) > 2 else sorted(sc)
for m in muts:
    caught = {}
    for sid in ids:
        d = Path("var/mutants") / m / sid
        shutil.rmtree(d, ignore_errors=True)
        run_one(d, sc[sid], "A2", mutant=m)
        e = evaluate(d, sc[sid], "A2")
        f = [c for c in CHECKS if e["checks"][c]["result"] == "FAIL"]
        if f:
            caught[sid] = f
    print(m, len(caught), "scenarios fail:", caught)
