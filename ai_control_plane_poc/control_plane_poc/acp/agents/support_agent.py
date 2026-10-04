"""support-agent: resolve a customer case, refunding a duplicate charge when the evidence supports it.

Business reasoning only. The case contains customer PII, so the agent marks its model call as confidential data; which
model may see confidential data, and where it runs, is the control plane's decision, not this file's.
"""


def run(task, ctx):
    case = ctx.call("read_case", case_id=task["case_id"])
    checkout = ctx.call("query_logs", service="payment-service", environment="production")
    note = ctx.model("Draft the customer reply for this case", data=[case.value], data_class="confidential")

    refund = None
    if case.ok and task.get("refund"):
        refund = ctx.call("refund_customer", case_id=task["case_id"], amount=case.value["amount"])

    return {
        "case_id": task["case_id"],
        "evidence": [case.status, checkout.status],
        "reply": note.value["text"] if note.ok else None,
        "refund": None if refund is None else refund.status,
        "approval_id": None if refund is None else refund.approval_id,
    }
