"""D1 · the drift probe: the same incidents, two agent configurations, and the mix of actions the model proposes.

    python -m lineage.drift record --run-id <run>      live model, tape under runs/<run>/drift/tape
    python -m lineage.drift replay --run-id <run>      from that tape, no model

Ten incident variants (config/drift.toml), each asked once under incident-agent-prod@8 and once under @9.  Every proposal is
also evaluated by the policy engine, to show the point of the section: each proposal can be individually permitted while
the distribution of proposals moves.  This is a small probe (twenty calls), not a drift detector; its output is a
distribution, reported as counts, not a significance claim.
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from collections import Counter

from . import model, policy
from .common import CONFIG, POC


def variants() -> list[dict]:
    return tomllib.loads((CONFIG / "drift.toml").read_text())["variant"]


def text(v: dict) -> str:
    return "\n".join([f"Time: {v['time']} UTC.",
                      f"Incident {v['id']} ({v['severity']}, open): {v['service']} alert from {v['source']}.",
                      f"Production deployment of {v['service']}: running {v['version']}; release history {', '.join(v['history'])}.",
                      f"Error rate now: {v['error_rate']} (before: {v['error_rate_before']}).",
                      f"Logs: {v['logs']}", f"Recent changes: {v['changes']}", f"Staging: {v['staging']}"])


def main() -> None:
    a = sys.argv[1:]
    mode = a[0]
    rid = a[a.index("--run-id") + 1]
    out_dir = POC / "runs" / rid / "drift"
    out_dir.mkdir(parents=True, exist_ok=True)
    os.environ["LINEAGE_TAPE"] = f"{mode}:{out_dir / 'tape'}"
    rows = []
    for ref in ("incident-agent-prod@8", "incident-agent-prod@9"):
        cfg = model.config(ref)
        for v in variants():
            out = model.propose(cfg, text(v), caller=f"drift-{ref}-{v['id']}", agent={"id": "incident-agent-prod"})
            p = out["proposal"]
            pe = policy.evaluate("prod-rollback@42", {**p, "environment": "production"}, {"agent": "incident-agent-prod", "severity": v["severity"]}, f"drift-{v['id']}")
            rows.append({"config": ref, "variant": v["id"], "kind": v["kind"], "capability": p["capability"], "to_version": p["to_version"],
                         "policy_decision": pe["decision"] if p["capability"] == "deployment.rollback" else "not a rollback (outside prod-rollback)",
                         "rationale": p["rationale"][:200]})
            print(ref, v["id"], p["capability"], p["to_version"], flush=True)
    dist = {ref: dict(Counter(r["capability"] for r in rows if r["config"] == ref)) for ref in ("incident-agent-prod@8", "incident-agent-prod@9")}
    changed = sum(1 for v in variants() if len({r["capability"] for r in rows if r["variant"] == v["id"]}) > 1)
    denied = sum(1 for r in rows if r["policy_decision"] == "DENY")
    report = {"variants": len(variants()), "calls": len(rows), "distribution": dist, "variants_whose_action_changed": changed,
              "rollback_proposals_denied_by_policy": denied, "rows": rows}
    (out_dir / "drift.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main()
