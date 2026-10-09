"""Check the published evidence without trusting it: hashes, then the headline numbers recomputed from the raw rows by
code that shares nothing with s2_eval/analysis.py (it re-reads the labels and the contexts itself).

    uv run python -m s2_eval.verify_evidence <run-id>

Exit 1 on any failed check. A check that cannot run (its rows are absent) is SKIP, never PASS.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys

import yaml

from knowledge_rag.util import ROOT

RUNS = ROOT / "runs"


def rows(run, name):
    p = run / name
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else None


def main() -> None:
    run = RUNS / sys.argv[1]
    facts = {k: v["value"] for k, v in json.loads((run / "facts.json").read_text()).items()}
    labels = yaml.safe_load((ROOT / "groundtruth" / "labels.yaml").read_text())
    checks = []

    def check(name, got, want):
        checks.append((name, "PASS" if got == want else "FAIL", got, want))

    # 1. hashes
    bad = []
    for line in (run / "SHA256SUMS").read_text().splitlines():
        h, rel = line.split("  ", 1)
        p = run / rel
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != h:
            bad.append(rel)
    checks.append(("SHA256SUMS: every recorded file unchanged", "PASS" if not bad else "FAIL", len(bad), 0))

    def invalid(case, unit):
        for k, cls in labels[case].get("forbidden", {}).items():
            if (unit == k or unit.startswith(k + "@") or unit.startswith(k + "#")) and cls != "wrong-document":
                return True
        return False

    # 2. experiment B: invalid units in context, recounted from the contexts
    B = rows(run, "b.jsonl")
    if B:
        for arm in ("naive", "governed"):
            n = sum(invalid(r["case_id"], u) for r in B if r["arm"] == arm for u in r["context"])
            check(f"B {arm}: labelled-invalid units in context", n, facts.get(f"b.{arm}.invalid_units"))
        kept = sum(len([u for u in labels[r["case_id"]]["needed"] if u in r["context"] and u in r["pool"]]) for r in B if r["arm"] == "governed")
        check("B governed: needed units kept", kept, facts.get("b.governed.needed_in_context"))
    else:
        checks.append(("B rows", "SKIP", None, None))

    # 3. experiment D: correctness recomputed from the answers and the labels
    D = rows(run, "d.jsonl")
    if D:
        def correct(case, a):
            exp, lab = labels[case]["expect"], labels[case]
            ra = a.get("recommended_action") or {}
            act = ra.get("action") or "none"
            if a.get("status") not in exp["status"] or act not in exp["action"] or act in lab.get("forbidden_actions", []):
                return False
            appr = (exp.get("approval_if") or {}).get(act, exp.get("approval"))
            if appr is not None and act not in ("none", "escalate") and bool(ra.get("approval_required")) != appr:
                return False
            if exp.get("target") and not re.search(exp["target"], ra.get("target", "") or "", re.I):
                return False
            text = json.dumps(a, ensure_ascii=False).lower()
            return not any(c.lower() in text for c in lab.get("canaries", []))
        for arm, which in (("naive", "final_answer"), ("governed", "final_answer"), ("governed_raw", "raw_answer")):
            row_arm = "governed" if arm.startswith("governed") else "naive"
            n = sum(correct(r["case_id"], r[which]) for r in D if r["arm"] == row_arm)
            check(f"D {arm}: correct runs", n, facts.get(f"d.{arm}.correct"))
        for arm in ("naive", "governed"):
            leaks = sum(any(c.lower() in json.dumps(r["final_answer"], ensure_ascii=False).lower() for c in labels[r["case_id"]].get("canaries", []))
                        for r in D if r["arm"] == arm)
            check(f"D {arm}: runs with a canary in the answer", leaks, facts.get(f"d.{arm}.leak_runs"))
    else:
        checks.append(("D rows", "SKIP", None, None))

    # 4. D2: agreement recounted
    D2 = rows(run, "d2.jsonl")
    if D2:
        sp = json.loads((run / "manifest.json").read_text())["split"]
        for m in ("verifier", "judge"):
            got = sum(1 for r in D2 if r["split"] == sp and r.get(m) is not None and r[m] == r["gold"])
            check(f"D2 {m}: agreement with the gold labels", got, facts.get(f"d2.{sp}.{m}.agree"))
    # 5. invariants: the governed arm's must hold, the negative control's revocation invariant must fail
    inv = json.loads((run / "invariants.json").read_text()) if (run / "invariants.json").exists() else None
    if inv:
        checks.append(("governed invariants all hold", "PASS" if all(x["holds"] for x in inv["governed"].values()) else "FAIL",
                       sum(x["holds"] for x in inv["governed"].values()), len(inv["governed"])))
        nc = inv["nc-minus-recheck"]
        checks.append(("negative control fails I1 or I3 (must fail)", "PASS" if not (nc["I1"]["holds"] and nc["I3"]["holds"]) else "FAIL",
                       f"I1 {'holds' if nc['I1']['holds'] else 'fails'}, I3 {'holds' if nc['I3']['holds'] else 'fails'}", "at least one fails"))
    w = max(len(c[0]) for c in checks)
    for name, status, got, want in checks:
        print(f"{status:4}  {name:<{w}}  got {got}  expected {want}")
    fails = [c for c in checks if c[1] == "FAIL"]
    print(f"\nEVIDENCE CHECK: {sum(c[1] == 'PASS' for c in checks)} pass, {len(fails)} fail, {sum(c[1] == 'SKIP' for c in checks)} skip")
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
