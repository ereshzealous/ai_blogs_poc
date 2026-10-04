"""finance-agent: reconcile the ledger and flag duplicate transactions.

Business reasoning only. It shares no tool with the incident and support agents, which is what lets a proof show that
revoking one MCP server stops exactly the agents that depend on it, and no others.
"""


def run(task, ctx):
    ledger = ctx.call("read_ledger")
    flagged = []
    if ledger.ok:
        for txn in ledger.value["transactions"]:
            if txn.get("duplicate_of"):
                flagged.append(ctx.call("flag_transaction", txn=txn["txn"]).status)
    summary = ctx.model("Summarise today's reconciliation", data=[ledger.value])
    return {"evidence": [ledger.status], "flagged": flagged, "summary": summary.value["text"] if summary.ok else None}
