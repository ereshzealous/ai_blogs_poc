"""Compare two proof runs: which recorded values reproduce, and which are expected to differ.

    uv run python compare_runs.py evidence/runs/<A> evidence/runs/<B> [OUT]    -> OUT (default <B>/replay-comparison.json)

Compared: every check's verdict (passed) and recorded actual value; the content-derived ids and digests of R1 and R3.
Expected to differ (listed, not compared): OpenTelemetry trace ids, timestamps, pids, wall-clock times.
"""
import json
import sys
from pathlib import Path

a, b = (json.loads((Path(p) / "results.json").read_text()) for p in sys.argv[1:3])
ca = {c["id"]: c for e in a["experiments"] for c in e["checks"]} | {c["id"]: c for c in a["cross_checks"]}
cb = {c["id"]: c for e in b["experiments"] for c in e["checks"]} | {c["id"]: c for c in b["cross_checks"]}
volatile = {"X.canary", "X.keys", "X.chains"}   # compare outcome only: their detail counts files, which is stable, but keep it strict below
diff = [k for k in sorted(set(ca) | set(cb)) if (ca.get(k, {}).get("passed"), json.dumps(ca.get(k, {}).get("actual"), sort_keys=True, default=str))
        != (cb.get(k, {}).get("passed"), json.dumps(cb.get(k, {}).get("actual"), sort_keys=True, default=str))]
fa = {e["id"]: e["facts"] for e in a["experiments"]}
fb = {e["id"]: e["facts"] for e in b["experiments"]}
ids = [("R1", k) for k in ("workflow_id", "digest", "approval_id", "decision_id", "jti", "idempotency_key", "rollback_id", "policy_version", "bundle_version")] + \
      [("R3", "approved_digest"), ("R3", "tampered_digest")]
same_ids = {f"{e}.{k}": fa[e][k] == fb[e][k] for e, k in ids}
out = {"run_a": a["run_id"], "run_b": b["run_id"], "checks_compared": len(set(ca) | set(cb)), "checks_identical": len(set(ca) | set(cb)) - len(diff),
       "checks_different": diff, "ids_compared": len(same_ids), "ids_identical": sum(same_ids.values()), "ids": same_ids,
       "expected_to_differ": ["OpenTelemetry trace and span ids", "timestamps", "process ids", "wall-clock durations"]}
(Path(sys.argv[3]) if len(sys.argv) > 3 else Path(sys.argv[2]) / "replay-comparison.json").write_text(json.dumps(out, indent=1))
print(json.dumps({k: v for k, v in out.items() if k != "ids"}, indent=1))
sys.exit(0 if not diff and all(same_ids.values()) else 1)
