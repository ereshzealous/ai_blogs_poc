"""Per-workflow measurements from the ledgers and the trace files.  Definitions are frozen in the preregistration.

duplicate tool call   same capability + same canonical arguments + same world version (no write executed in between),
                      seen earlier in the same workflow.  `cross_component` when the earlier call was made by a
                      different component (one agent re-fetching what another already fetched).
handoff               a transfer of work to a reasoning component: B = each agent invocation by the workflow,
                      C = each delegation (A2A task; retries counted separately), A = 0.
boundary overhead     C only: client-observed delegation time minus the agent's own server-side time, per completed
                      attempt (protocol + transport + serialization + process scheduling).
coordination tokens   tokens of model calls whose role is "coordination" (C's coordinator).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from coord.store import Store
from coord.util import canon


def trace_completeness(traces_dir: Path, trace_id: str) -> dict[str, Any]:
    spans = []
    for f in traces_dir.glob(f"{trace_id}.*.jsonl"):
        spans += [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    ids = {s["span_id"] for s in spans}
    roots = [s for s in spans if not s["parent_id"]]
    orphans = [s for s in spans if s["parent_id"] and s["parent_id"] not in ids]
    return {"spans": len(spans), "processes": len({s["pid"] for s in spans}), "services": sorted({s.get("service", "") for s in spans}),
            "roots": len(roots), "orphans": len(orphans), "complete": bool(spans) and len(roots) == 1 and not orphans}


def measure(store: Store, workflow_id: str, traces_dir: Path) -> dict[str, Any]:
    wf = store.workflow(workflow_id)
    assert wf
    usage = store.rows("SELECT * FROM model_usage WHERE workflow_id=? ORDER BY seq", (workflow_id,))
    calls = store.calls(workflow_id)
    steps = store.rows("SELECT * FROM steps WHERE workflow_id=? ORDER BY seq", (workflow_id,))
    dels = store.rows("SELECT * FROM delegations WHERE workflow_id=? ORDER BY started", (workflow_id,))

    seen: dict[str, str] = {}
    dup = dup_cross = 0
    dup_detail: Counter[str] = Counter()
    for c in calls:
        if c["outcome"] not in ("ok", "error"):
            continue
        key = canon([c["capability"], c["args"], c["world_version"]])
        if key in seen:
            dup += 1
            dup_detail[c["capability"]] += 1
            if seen[key] != c["component"]:
                dup_cross += 1
        else:
            seen[key] = c["component"]

    tok_in = sum(u["prompt_tokens"] for u in usage)
    tok_out = sum(u["completion_tokens"] for u in usage)
    coord_tokens = sum(u["prompt_tokens"] + u["completion_tokens"] for u in usage if u["role"] == "coordination")
    model_ms = sum(u["wall_ms"] or 0 for u in usage)
    tool_ms = sum(c["wall_ms"] or 0 for c in calls)
    latency_ms = round(((wf["ended"] or wf["started"]) - wf["started"]) * 1000, 1)

    if wf["arch"] == "B":
        handoffs = sum(1 for s in steps if s["kind"] == "handoff")
        handoff_bytes = sum(json.loads(s["detail"]).get("payload_bytes", 0) for s in steps if s["kind"] == "handoff")
    elif wf["arch"] == "C":
        handoffs = len({d["delegation_id"] for d in dels})
        handoff_bytes = sum((d["req_bytes"] or 0) + (d["resp_bytes"] or 0) for d in dels)
    else:
        handoffs, handoff_bytes = 0, 0
    completed = [d for d in dels if d["state"] == "COMPLETED"]
    boundary_ms = sum((d["client_ms"] or 0) - (d["server_ms"] or 0) for d in completed)
    review_rejections = sum(1 for s in steps if s["kind"] == "review_rejected")
    if wf["arch"] == "C":
        review_rejections = len(store.rows("SELECT artifact_id FROM artifacts WHERE workflow_id=? AND kind='review' AND body LIKE '%\"verdict\":\"reject\"%'",
                                           (workflow_id,)))
    result = json.loads(wf["result"]) if wf["result"] else {}
    tc = trace_completeness(traces_dir, wf["trace_id"]) if wf["trace_id"] else {}
    return {
        "latency_ms": latency_ms, "model_ms": round(model_ms, 1), "tool_ms": round(tool_ms, 1),
        "other_ms": round(max(0.0, latency_ms - model_ms - tool_ms), 1),
        "llm_calls": len(usage), "llm_calls_coordination": sum(1 for u in usage if u["role"] == "coordination"),
        "llm_errors": sum(1 for u in usage if not u["ok"]),
        "tokens_in": tok_in, "tokens_out": tok_out, "tokens_total": tok_in + tok_out, "tokens_coordination": coord_tokens,
        "max_prompt_tokens": max((u["prompt_tokens"] for u in usage), default=0),
        "components": sorted({u["component"] for u in usage}),
        "tool_calls": len(calls), "tool_reads": sum(1 for c in calls if c["kind"] == "read"),
        "write_requests": sum(1 for c in calls if c["kind"] == "write"), "denied": sum(1 for c in calls if c["effect"] == "DENY"),
        "duplicate_tool_calls": dup, "duplicate_cross_component": dup_cross, "duplicate_by_tool": dict(dup_detail),
        "handoffs": handoffs, "handoff_bytes": handoff_bytes,
        "delegation_attempts": len(dels), "retries": len(dels) - handoffs if wf["arch"] == "C" else 0,
        "timeouts": sum(1 for d in dels if d["state"] == "TIMEOUT"), "transport_failures": sum(1 for d in dels if d["state"] == "TRANSPORT"),
        "process_boundaries": len(dels) if wf["arch"] == "C" else 0, "boundary_overhead_ms": round(boundary_ms, 1),
        "delegation_server_ms": [d["server_ms"] for d in completed if d["server_ms"] is not None],
        "delegation_client_ms": [d["client_ms"] for d in completed if d["client_ms"] is not None],
        "deterministic_steps": sum(1 for s in steps if s["decided_by"] == "code"),
        "model_steps": sum(1 for s in steps if s["decided_by"] == "model"),
        "cycle_blocks": sum(1 for s in steps if s["kind"] == "cycle_blocked"),
        "claim_checks": sum(1 for s in steps if s["kind"] == "claim_check"),
        "review_rejections": review_rejections,
        "state_conflicts": len(result.get("state_conflicts") or []),
        "termination": wf["termination"], "outcome": wf["outcome"],
        "trace": tc,
    }
