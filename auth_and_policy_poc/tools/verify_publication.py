"""Publication check: both editions print the recorded run's values, and none of the wording the standardization retired.

    python3 tools/verify_publication.py        prints each check; exit 1 if any fails

It reads the recorded run (authz_poc/runs/2026-09-29-recorded/) and the two Markdown sources, never the other way round:
every expected value below is computed from an artifact, not typed. Run `python3 -m authz.verify` first (in authz_poc/)
so that verification.json and tests.json are current.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "authz_poc" / "runs" / "2026-09-29-recorded"
FULL = (ROOT / "authorization-and-policy-for-ai-agents.md").read_text()
MEDIUM = (ROOT / "medium" / "authorization-and-policy-for-ai-agents-medium.md").read_text()
BOTH = {"full": FULL, "medium": MEDIUM}

log = [json.loads(line) for line in (RUN / "decisions.jsonl").read_text().splitlines()]
facts = json.loads((RUN / "facts.json").read_text())
timeline = json.loads((RUN / "timeline.json").read_text())
sweep = json.loads((RUN / "sweep.json").read_text())
invariants = json.loads((RUN / "invariants.json").read_text())
verification = json.loads((RUN / "verification.json").read_text())
transcript = (RUN / "transcript.txt").read_text().splitlines()

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))


def json_blocks(text: str) -> list[dict]:
    out = []
    for block in re.findall(r"```json\n(.*?)\n```", text, re.S):
        try:
            out.append(json.loads(block))
        except json.JSONDecodeError:
            pass
    return out


def same_where_shown(shown, actual) -> bool:
    """A published excerpt matches the record, except where it says it is abridged ("...": "(abridged)")."""
    if isinstance(shown, dict):
        if not isinstance(actual, dict):
            return False
        return all(k == "..." or (k in actual and same_where_shown(v, actual[k])) for k, v in shown.items())
    return shown == actual


decisions = [r["record"] for r in log if r["kind"] == "policy.decision"]
first_pass = [d for d in decisions if not d["recheck_of"]]
prod_rb = [d for d in first_pass if d["action"] == "kubernetes.rollbackDeployment" and d["resource"] == "deployment/payment-service"
           and d["environment"] == "production"]
approval = next(r["record"] for r in log if r["kind"] == "approval.requested")
granted = next(r for r in log if r["kind"] == "approval.granted")
executed = [r for r in log if r["kind"] == "tool.executed"]
final = executed[-1]

# -- values both editions print -------------------------------------------------------------------------------------
for ed, text in BOTH.items():
    check(f"{ed}: evidence {prod_rb[0]['attributes']['evidence_score']} → {prod_rb[1]['attributes']['evidence_score']}",
          str(prod_rb[0]["attributes"]["evidence_score"]) in text and str(prod_rb[1]["attributes"]["evidence_score"]) in text)
    check(f"{ed}: approval at {granted['time'][11:19]}", granted["time"][11:19] in text)
    check(f"{ed}: executed at {final['time'][11:19]}, rolled back to {final['record']['output']['rolled_back_to']}",
          final["time"][11:19] in text and final["record"]["output"]["rolled_back_to"] in text)
    check(f"{ed}: no retired wording", not re.search(r"five different answers|REQUIRE_APPROVAL|agent_confidence|"
                                                     r"27 of 27|48 checks|record_tests|typed from memory", text),
          "found: " + ", ".join(sorted(set(re.findall(r"five different answers|REQUIRE_APPROVAL|agent_confidence|27 of 27|"
                                                      r"48 checks|record_tests|typed from memory", text)))))
    check(f"{ed}: figure provenance wording", "Every decision, identifier, timestamp and measured value" in text)

# -- the full edition ----------------------------------------------------------------------------------------------
check("full: policy version", facts["policy_version"] in FULL)
check("full: request fingerprint", prod_rb[1]["request_fingerprint"] in FULL)
check("full: approval id and expiry", approval["approval_id"] in FULL and approval["expires_at"][11:19] in FULL)
by = facts["decisions_by_type"]
check("full: decision totals", f"{by['ALLOW']} ALLOW · {by['ALLOW_WITH_CONSTRAINTS']} ALLOW_WITH_CONSTRAINTS · "
                               f"{by['ALLOW_WITH_APPROVAL']} ALLOW_WITH_APPROVAL · {by['DENY']} DENY" in FULL)
sd = facts["sweep_decisions"]
check("full: sweep totals", f"{sd['ALLOW']} ALLOW, {sd['ALLOW_WITH_APPROVAL']} ALLOW_WITH_APPROVAL, {sd['DENY']} DENY" in FULL)
missing = [s["reason"] for s in sweep if s["reason"] not in FULL]
check("full: every sweep reason, verbatim", not missing, "; ".join(missing))
missing = [t["reason"] for t in timeline if t["reason"] not in FULL]
check("full: every decision-table reason, verbatim", not missing, "; ".join(missing))
excerpt = [line for line in transcript if line.startswith(("14:07:30", "14:07:45", "14:08:50", "14:09:02"))]
check("full: approval log lines, verbatim from transcript.txt", all(line in FULL for line in excerpt))
blocks = json_blocks(FULL)
by_seq = {r["seq"]: r for r in log}
receipts = [b for b in blocks if isinstance(b, dict) and "seq" in b]
check("full: receipt JSON blocks match the log", receipts and all(same_where_shown(b, by_seq[b["seq"]]) for b in receipts),
      ", ".join(str(b["seq"]) for b in receipts))
summary = verification["summary"]
shown = [b for b in blocks if isinstance(b, dict) and b.get("run") == summary["run"]]
check("full: authz.verify output matches verification.json", shown and shown[0] == summary)
ids = [i["id"] for i in invariants]
check("full: all 14 invariant ids", len(ids) == 14 and all(i in FULL for i in ids))
check("full: invariant names", all(i["name"] in FULL for i in invariants))

# -- the Medium edition --------------------------------------------------------------------------------------------
all_pass = summary["ok"] and summary["invariants"]["passed"] == summary["invariants"]["total"] == 14
check("medium: '14 named production authorization invariants' only if all 14 pass",
      ("14 named production authorization invariants" in MEDIUM) <= all_pass)
check("medium: approval refused for the requester", "self" in MEDIUM.lower() or "its own approval" in MEDIUM.lower())

# -- the run itself ------------------------------------------------------------------------------------------------
check("run: verification summary ok", summary["ok"], json.dumps({k: summary[k] for k in ("replay", "audit_chain", "deterministic")}))

width = max(len(n) for n, _, _ in results)
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail if not ok else ''}".rstrip())
failed = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} publication checks pass")
sys.exit(1 if failed else 0)
