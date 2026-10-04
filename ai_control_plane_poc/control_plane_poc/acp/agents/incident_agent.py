"""incident-agent: investigate a service incident and remediate it.

Business reasoning only. This file names no model, no permission, no approval rule, no budget, no credential and no
kill switch. It asks for evidence, reasons about it, and proposes a remediation; the runtime context `ctx` decides,
from the control plane's current desired state, whether each step may run.

The plan is fixed (no LLM) so every proof is deterministic: the question is what governs the plan, not how it is made.
"""


def run(task, ctx):
    service, env = task["service"], task["environment"]

    logs = ctx.call("query_logs", service=service, environment=env)
    metrics = ctx.call("query_metrics", service=service, environment=env)
    summary = ctx.model("Summarise the incident evidence and propose a remediation", data=[logs.value, metrics.value])

    remediation = None
    if metrics.ok and metrics.value["error_rate"] > task.get("error_budget", 0.01):
        remediation = ctx.call("restart_service", service=service, environment=env)

    return {
        "service": service,
        "environment": env,
        "evidence": [logs.status, metrics.status],
        "summary": summary.value["text"] if summary.ok else None,
        "remediation": None if remediation is None else remediation.status,
        "approval_id": None if remediation is None else remediation.approval_id,
    }
