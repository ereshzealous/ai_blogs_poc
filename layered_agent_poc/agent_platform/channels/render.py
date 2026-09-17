"""Plain-text rendering of a workflow view for terminal-like channels."""

from __future__ import annotations

from typing import Any

ICON = {"RUNNING": "▶", "WAITING_APPROVAL": "⏸", "COMPLETED": "✔", "FAILED": "✖", "REJECTED": "⊘"}


def text(view: dict[str, Any]) -> str:
    lines = [f"{ICON.get(view['status'], '•')} {view['workflow_id']}  {view['incident_id']}  {view['status']}  "
             f"(step: {view['current_step']}, channel: {view['channel']}, by: {view['requested_by']})"]
    d = view.get("diagnosis")
    if d:
        lines += [f"  diagnosis   {d['suspect_service']} {d['suspect_version']} ({d['suspect_deployment_id']}), confidence {d['confidence']}",
                  f"  root cause  {d['root_cause']}"]
    p = view.get("proposal")
    if p:
        target = p.get('target_version') or f"revision {p.get('revision')}"
        lines.append(f"  proposal    {p['tool_id']} → {target} in {p['environment']}")
    pol = view.get("policy")
    if pol:
        lines.append(f"  policy      {pol['decision']} ({pol['rule_id']})")
    a = view.get("approval")
    if a:
        who = f" by {a['decided_by']}" if a.get("decided_by") else f" (needs role {a['required_role']})"
        lines.append(f"  approval    {a['id']} {a['status']}{who}")
    r = view.get("remediation")
    if r:
        lines.append(f"  remediation {r['status']} attempts={r['attempts']} replayed={r['replayed']} op={r['operation_id']}")
    v = view.get("verification")
    if v:
        lines.append(f"  verify      {'ok' if v.get('ok') else 'FAILED'} p95={v.get('p95_ms')} ms (SLO {v.get('slo_p95_ms')})")
    n = view.get("note")
    if n:
        lines.append(f"  incident    {n['status']}: {n['note'][:160]}")
    lines.append(f"  tokens {view.get('tokens_used', 0)} · checkpoints {view.get('checkpoints', 0)} · trace {view.get('trace_id')}")
    return "\n".join(lines)


def trace_tree(spans: list[dict[str, Any]]) -> str:
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    ids = {s["span_id"] for s in spans}
    for s in spans:
        parent = s["parent_id"] if s["parent_id"] in ids else None
        by_parent.setdefault(parent, []).append(s)
    out: list[str] = []

    def walk(parent: str | None, depth: int) -> None:
        for s in sorted(by_parent.get(parent, []), key=lambda x: x["start_ns"]):
            ms = (s["end_ns"] - s["start_ns"]) / 1e6
            a = s["attributes"]
            extra = " ".join(f"{k.split('.')[-1]}={a[k]}" for k in ("lap.policy.decision", "gen_ai.usage.input_tokens",
                                                                      "gen_ai.usage.output_tokens", "lap.attempt",
                                                                      "lap.idempotency.replayed", "lap.checkpoint.seq") if k in a)
            out.append(f"{'  ' * depth}{s['name']}  {ms:,.0f} ms  {extra}")
            walk(s["span_id"], depth + 1)

    walk(None, 0)
    return "\n".join(out)
