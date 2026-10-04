"""The proof pack's fact registry (pae-proof/v1): every fact a check in proof/experiments.toml compares, with its source.

    collect(run_id) -> (Facts, data)

Everything is read from the recorded run, never typed:

  the run's own facts.json          every scenario measure (p2.request_hash_before, p9.outage.stale_run, …)
  each scenario's assertions        <prefix>.assertions_passed / _total, from scenario.json → checks
  raw evidence, recomputed here     hash chains, bundle signatures, credentials in bundles, request hashes,
                                    runtime processes and agent code hashes, from the state the scenarios left behind
  the replay record                 evidence/runs/<run>/replay.json (tools/verify_run.py --record)

Run with the POC's environment (it imports acp): uv run --project control_plane_poc python tools/proof_pack.py …
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "control_plane_poc"
sys.path.insert(0, str(ROOT / "vendor" / "kit5"))
from evidence_kit.facts import Facts  # noqa: E402  (5.2.0, vendor/kit5)

from acp.common import canon, digest, read_json, read_jsonl, sha256, verify_chain, verify_signature  # noqa: E402
from acp.facts import prefix  # noqa: E402


def collect(run_id: str) -> tuple[Facts, dict]:
    run = POC / "runs" / run_id
    base = f"control_plane_poc/runs/{run_id}"
    F = Facts()
    for k, f in read_json(run / "facts.json").items():
        F.add(k, f["value"], source=f["source"])

    scenarios = [read_json(p / "scenario.json") for p in sorted((run / "scenarios").iterdir())]
    for s in scenarios:
        p, src = prefix(s["id"]), f"{base}/scenarios/{s['id']}/scenario.json → checks"
        F.add(f"{p}.assertions_passed", sum(c["passed"] for c in s["checks"]), source=src, derivation="assertions that held")
        F.add(f"{p}.assertions_total", len(s["checks"]), source=src)

    # ---- recomputed from the raw state -------------------------------------------------------------------------------
    audits = sorted(run.glob("scenarios/*/state/runtime/*/audit.jsonl"))
    src = f"{base}/scenarios/*/state/runtime/*/audit.jsonl"
    F.add("raw.audit_chains", len(audits), source=src)
    F.add("raw.audit_chains_verified", sum(verify_chain(p) for p in audits), source=src, derivation="every row's prev and hash recomputed")
    logs = sorted(run.glob("scenarios/*/state/controlplane/changelog.jsonl"))
    src = f"{base}/scenarios/*/state/controlplane/changelog.jsonl"
    F.add("raw.changelogs", len(logs), source=src)
    F.add("raw.changelogs_verified", sum(verify_chain(p) for p in logs), source=src, derivation="every row's prev and hash recomputed")
    bundles = sorted(run.glob("scenarios/*/state/controlplane/bundles/v*.json"))
    src = f"{base}/scenarios/*/state/controlplane/bundles/v*.json"
    F.add("raw.bundles", len(bundles), source=src)
    F.add(
        "raw.bundles_signature_valid",
        sum(verify_signature(sha256(canon(read_json(b))), b.with_suffix(".sig").read_text().strip()) for b in bundles),
        source=src,
        derivation="HMAC-SHA256 of each bundle's canonical body checked against its .sig",
    )
    plain = [
        f"{b.parent.parent.parent.parent.name}/{b.name}:{t}"
        for b in bundles
        for t, meta in read_json(b)["desired_state"]["tools"].items()
        if not str(meta.get("credential", "")).startswith("secret://")
    ]
    F.add("raw.plaintext_credentials_in_bundles", len(plain), source=src, derivation="tools whose credential is not a secret:// reference")

    runs = [t for p in sorted(run.glob("scenarios/*/transcript.jsonl")) for t in read_jsonl(p) if t["request"].get("op") == "run"]
    src = f"{base}/scenarios/*/transcript.jsonl"
    F.add("raw.run_requests", len(runs), source=src)
    F.add(
        "raw.request_hashes_recomputed",
        sum(t.get("request_sha256") == digest({k: t["request"][k] for k in ("agent", "task")}) for t in runs),
        source=src,
        derivation="request_sha256 recomputed from each recorded run request (agent, task)",
    )
    labels = [lab for p in sorted(run.glob("scenarios/*/volatile.json")) for lab in read_json(p)["runtime_pids"]]
    src = f"{base}/scenarios/*/volatile.json → runtime_pids (labels)"
    F.add("raw.runtime_processes", len(labels), source=src)
    F.add("raw.runtime_restarts", sum(int(re.search(r"pid-(\d+)$", lab).group(1)) > 1 for lab in labels), source=src, derivation="labels pid-2 and later")
    F.add(
        "raw.agent_code_hashes",
        len({s["agent_code_sha256"] for s in scenarios}),
        source=f"{base}/scenarios/*/scenario.json → agent_code_sha256",
        derivation="distinct agent source hashes across every scenario",
    )

    # ---- replay ------------------------------------------------------------------------------------------------------
    rp = ROOT / "evidence" / "runs" / run_id / "replay.json"
    replay = json.loads(rp.read_text()) if rp.exists() else None
    if replay:
        src = f"evidence/runs/{run_id}/replay.json"
        F.add("replay.level", replay["replay_level"], source=src)
        F.add("replay.files", replay["files"], source=src)
        F.add("replay.deterministic_equivalent", replay["classes"]["DETERMINISTIC_EQUIVALENT"], source=src + " → classes")
        F.add("replay.nondeterministic", replay["classes"]["NONDETERMINISTIC"], source=src + " → classes", derivation="volatile.json: raw process ids only")
        F.add(
            "replay.not_equivalent",
            sum(replay["classes"][k] for k in ("REGRESSION", "MODEL_OUTPUT_VARIATION", "METHODOLOGY_CHANGE")),
            source=src + " → classes",
        )
        F.add("replay.fresh_model_calls", replay["fresh_model_calls"], source=src)

    data = {"manifest": read_json(run / "manifest.json"), "scenarios": scenarios, "roles": read_json(run / "scenarios.json"), "replay": replay}
    return F, data
