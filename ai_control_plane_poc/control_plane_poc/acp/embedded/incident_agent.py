"""BASELINE (anti-pattern): incident-agent with its governance embedded in the agent itself.

This is how the first agent usually ships, and it is reasonable for one agent. The same business plan as
acp/agents/incident_agent.py, plus its own model choice, tool permissions, approval rule, budget and credentials.
Changing any of those means editing this file and redeploying this agent.
"""

MODEL = {"name": "fast-model", "usd_per_1k_tokens": 0.2, "residency": "us"}
ALLOWED_TOOLS = {"query_logs", "query_metrics", "restart_service"}
MAX_TOOL_CALLS = 10
CREDENTIALS = {"query_logs": "static-observability-token", "query_metrics": "static-observability-token", "restart_service": "static-deploy-token"}


def needs_approval(tool, args):
    return False  # production restarts run straight away


def run(task, tools):
    service, env = task["service"], task["environment"]
    logs = tools.call("query_logs", ALLOWED_TOOLS, CREDENTIALS, MAX_TOOL_CALLS, needs_approval, service=service, environment=env)
    metrics = tools.call("query_metrics", ALLOWED_TOOLS, CREDENTIALS, MAX_TOOL_CALLS, needs_approval, service=service, environment=env)
    summary = tools.model(MODEL, "Summarise the incident evidence and propose a remediation", [logs, metrics])
    remediation = None
    if metrics["status"] == "executed" and metrics["value"]["error_rate"] > task.get("error_budget", 0.01):
        remediation = tools.call("restart_service", ALLOWED_TOOLS, CREDENTIALS, MAX_TOOL_CALLS, needs_approval, service=service, environment=env)
    return {"summary": summary["text"], "remediation": None if remediation is None else remediation["status"]}
