"""BASELINE (anti-pattern): finance-agent with its governance embedded in the agent itself."""

MODEL = {"name": "large-model", "usd_per_1k_tokens": 1.5, "residency": "us"}
ALLOWED_TOOLS = {"read_ledger", "flag_transaction"}
MAX_TOOL_CALLS = 10
CREDENTIALS = {"read_ledger": "static-billing-token", "flag_transaction": "static-billing-token"}


def needs_approval(tool, args):
    return False


def run(task, tools):
    ledger = tools.call("read_ledger", ALLOWED_TOOLS, CREDENTIALS, MAX_TOOL_CALLS, needs_approval)
    flagged = []
    if ledger["status"] == "executed":
        for txn in ledger["value"]["transactions"]:
            if txn.get("duplicate_of"):
                flagged.append(tools.call("flag_transaction", ALLOWED_TOOLS, CREDENTIALS, MAX_TOOL_CALLS, needs_approval, txn=txn["txn"])["status"])
    summary = tools.model(MODEL, "Summarise today's reconciliation", [ledger])
    return {"flagged": flagged, "summary": summary["text"]}
