"""E8: can one request be followed to the exact tool action?  Scored from each architecture's own telemetry.

Expected chain (preregistered):  request · workflow · agent · model call · policy decision · tool call · checkpoint ·
result, all linked by one correlation id, plus "action attributable": the physical backend execution can be tied to
the request by an identifier rather than by timestamps.
"""

from __future__ import annotations

from typing import Any

CHAIN = ["request", "workflow", "agent", "model_call", "policy_decision", "tool_call", "checkpoint", "result", "linked", "action_attributable"]


def layered(raw: dict[str, Any]) -> dict[str, Any]:
    """Scored on the workflow's spans: those carrying f2.* attributes and their descendants.  The MCP SDK also emits spans
    of its own when a client connects (server/discover, tools/list); they belong to the connection, not the request, and
    are counted separately (revision r2, see experiments/evidence-revisions.yaml)."""
    allspans = raw["traces"]
    wf_traces = {s["trace_id"] for s in allspans if any(k.startswith("f2.") for k in (s.get("attributes") or {}))}
    spans = [s for s in allspans if s["trace_id"] in wf_traces]
    sdk = [s for s in allspans if s["trace_id"] not in wf_traces]
    by_name: dict[str, list[dict[str, Any]]] = {}
    for s in spans:
        by_name.setdefault(s["name"], []).append(s)
    a = lambda s, k: (s.get("attributes") or {}).get(k)  # noqa: E731
    ids = {s["span_id"] for s in spans}
    trace_ids = {s["trace_id"] for s in spans}
    ops = {t["op_id"] for t in raw.get("tool_calls", []) if t.get("op_id")}
    keys = {e["idempotency_key"] for e in raw["executions"] if e.get("idempotency_key")}
    present = {
        "request": any(a(s, "f2.request_id") for s in by_name.get("request", [])),
        "workflow": bool(by_name.get("workflow.step")) and all(a(s, "f2.workflow_id") for s in by_name["workflow.step"]),
        "agent": bool(by_name.get("invoke_agent")),
        "model_call": bool(by_name.get("chat")),
        "policy_decision": bool(by_name.get("policy.evaluate")) and all(a(s, "f2.policy.effect") for s in by_name["policy.evaluate"]),
        "tool_call": bool(by_name.get("execute_tool")),
        "checkpoint": any(a(s, "f2.checkpoint.seq") for s in by_name.get("workflow.step", [])),
        "result": any(a(s, "f2.status") in ("COMPLETED", "ESCALATED") for s in by_name.get("workflow.step", [])),
        "linked": len(trace_ids) == 1,
        "action_attributable": bool(keys) and keys <= ops,
    }
    return {"present": present, "score": sum(present.values()), "of": len(CHAIN), "spans": len(spans), "trace_ids": len(trace_ids),
            "processes": len({s["pid"] for s in spans}), "sdk_connection_spans": len(sdk),
            "spans_parented_on_a_span_lost_at_sigkill": sum(1 for s in spans if s["parent_id"] and s["parent_id"] not in ids)}


def monolith(raw: dict[str, Any]) -> dict[str, Any]:
    log = raw["agent_log"]
    ev = {e["event"] for e in log}
    writes = [e for e in raw["executions"] if e["tool"] != "update_incident"]
    present = {
        "request": "run_start" in ev,
        "workflow": False,                                   # no workflow identity exists
        "agent": "run_start" in ev,
        "model_call": "model_call" in ev,
        "policy_decision": "approval" in ev,                 # the approval callback's yes/no, without a rule or reason
        "tool_call": "tool_call" in ev,
        "checkpoint": False,                                 # nothing is checkpointed
        "result": "run_end" in ev,
        "linked": len({e["session_id"] for e in log}) == 1,  # one session id, shared by every retry of the request
        "action_attributable": bool(writes) and all(e.get("idempotency_key") for e in writes),
    }
    return {"present": present, "score": sum(present.values()), "of": len(CHAIN), "events": len(log), "processes": len({e["pid"] for e in log})}
