"""BASELINE (anti-pattern): support-agent with its governance embedded in the agent itself.

Its own copy of the model choice, the tool list, the refund approval threshold, the budget and the credentials.
"""

MODEL = {"name": "large-model", "usd_per_1k_tokens": 1.5, "residency": "us"}
ALLOWED_TOOLS = {"read_case", "refund_customer"}  # observability-mcp advisory: removed query_logs
MAX_TOOL_CALLS = 10
CREDENTIALS = {"read_case": "static-support-token", "query_logs": "static-observability-token", "refund_customer": "static-billing-token"}


def needs_approval(tool, args):
    return tool == "refund_customer" and args.get("amount", 0) > 100


def run(task, tools):
    case = tools.call("read_case", ALLOWED_TOOLS, CREDENTIALS, MAX_TOOL_CALLS, needs_approval, case_id=task["case_id"])
    checkout = tools.call("query_logs", ALLOWED_TOOLS, CREDENTIALS, MAX_TOOL_CALLS, needs_approval, service="payment-service", environment="production")
    note = tools.model(MODEL, "Draft the customer reply for this case", [case])
    refund = None
    if case["status"] == "executed" and task.get("refund"):
        refund = tools.call(
            "refund_customer", ALLOWED_TOOLS, CREDENTIALS, MAX_TOOL_CALLS, needs_approval, case_id=task["case_id"], amount=case["value"]["amount"]
        )
    return {"reply": note["text"], "evidence": [case["status"], checkout["status"]], "refund": None if refund is None else refund["status"]}
