"""The hand-authored core of the commerce tool estate (present at every estate size).

Each server entry carries two clearly separated parts:

* what the MCP server PUBLISHES (``name``, ``description``, ``inputSchema``,
  ``annotations``) — this is all a naive host or a search index ever sees;
* what the PLATFORM records about it (``gov``) — capability, lifecycle, environment,
  region, side-effect class, risk, scopes, approval, binding profile.  This is written
  to the governance registry, never to the server.

Descriptions are written the way real estates drift: staging copies publish the same
description as production, some retired tools say nothing about being retired, and a
vendor's annotations are accurate about side-effect *shape* (additive) while saying
nothing about business risk.
"""

from __future__ import annotations

from typing import Any

ORDER_ID = {"type": "string", "description": "Order id (format ORD-<digits>)", "pattern": "^ORD-[0-9]+$"}
PAYMENT_ID = {"type": "string", "description": "Payment (charge) id (format PAY-<digits>)", "pattern": "^PAY-[0-9]+$"}
CUSTOMER_ID = {"type": "string", "description": "Customer id (format CUS-<digits>)", "pattern": "^CUS-[0-9]+$"}
TICKET_ID = {"type": "string", "description": "Support ticket id (format TCK-<digits>)", "pattern": "^TCK-[0-9]+$"}
AMOUNT = {"type": "number", "exclusiveMinimum": 0, "description": "Amount in the order currency"}
REFUND_REASON = {
    "type": "string",
    "enum": ["duplicate_charge", "item_not_received", "damaged_item", "customer_request", "other"],
}


def obj(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


RO = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
DESTRUCTIVE = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False}


def gov(capability, *, side_effect="none", risk="low", scopes=(), approval=None, lifecycle="active", replaced_by=None, binding=None):
    return {
        "capability": capability,
        "side_effect": side_effect,
        "risk": risk,
        "required_scopes": list(scopes),
        "approval": approval or {"when": "never"},
        "lifecycle": lifecycle,
        "replaced_by": replaced_by,
        "binding_profile": binding,
    }


REFUND_APPROVAL = {"when": "amount_gt", "field": "amount", "threshold": 250}
CREDIT_APPROVAL = {"when": "amount_gt", "field": "amount", "threshold": 100}

_refund_schema = obj({"order_id": ORDER_ID, "payment_id": PAYMENT_ID, "amount": AMOUNT, "reason": REFUND_REASON}, ["order_id", "payment_id", "amount", "reason"])
_refund_desc = (
    "Refund an order to the customer's original payment method. Creates a refund against a captured payment "
    "on the order and records it in the order's refund ledger."
)

CORE_SERVERS: list[dict[str, Any]] = [
    # ------------------------------------------------------------------ authoritative systems
    {
        "server": "orders", "kind": "core", "owner": "order-management", "environment": "prod", "region": "global", "registered": True,
        "tools": [
            {"name": "get_order", "handler": "orders.get_order", "annotations": RO,
             "description": "Get an order: status, items, totals, currency, customer and shipping address.",
             "inputSchema": obj({"order_id": ORDER_ID}, ["order_id"]),
             "gov": gov("order.lookup", scopes=["orders:read"])},
            {"name": "search_orders", "handler": "orders.search_orders", "annotations": RO,
             "description": "Find a customer's orders by customer id or customer email.",
             "inputSchema": obj({"customer_id": CUSTOMER_ID, "customer_email": {"type": "string"}}, []),
             "gov": gov("order.search", scopes=["orders:read"])},
            {"name": "cancel_order", "handler": "orders.cancel_order", "annotations": DESTRUCTIVE,
             "description": "Cancel an order that has not shipped yet.",
             "inputSchema": obj({"order_id": ORDER_ID, "reason": {"type": "string"}}, ["order_id"]),
             "gov": gov("order.cancel", side_effect="write", risk="medium", scopes=["orders:write"], binding="order_entity")},
            {"name": "update_shipping_address", "handler": "orders.update_shipping_address", "annotations": WRITE,
             "description": "Change the delivery address on an order before it ships.",
             "inputSchema": obj({"order_id": ORDER_ID, "address": {"type": "string", "description": "Full new delivery address"}}, ["order_id", "address"]),
             "gov": gov("order.update_shipping_address", side_effect="write", risk="medium", scopes=["orders:write"], binding="order_entity")},
            {"name": "create_replacement_order", "handler": "orders.create_replacement_order", "annotations": WRITE,
             "description": "Create a free replacement shipment for one item on a delivered order (e.g. arrived damaged or defective).",
             "inputSchema": obj({"order_id": ORDER_ID, "sku": {"type": "string"}, "reason": {"type": "string"}}, ["order_id", "sku"]),
             "gov": gov("order.replacement", side_effect="write", risk="medium", scopes=["orders:write"], binding="order_replacement")},
        ],
    },
    {
        "server": "payments", "kind": "core", "owner": "payments-platform", "environment": "prod", "region": "global", "registered": True,
        "tools": [
            {"name": "list_charges", "handler": "payments.list_charges", "annotations": RO,
             "description": "List the captured charges (payments) on an order with payment ids, amounts, card last 4 and refund status.",
             "inputSchema": obj({"order_id": ORDER_ID}, ["order_id"]),
             "gov": gov("payment.list_charges", scopes=["payments:read"])},
            {"name": "get_charge", "handler": "payments.get_charge", "annotations": RO,
             "description": "Get one charge by payment id.",
             "inputSchema": obj({"payment_id": PAYMENT_ID}, ["payment_id"]),
             "gov": gov("payment.get_charge", scopes=["payments:read"])},
        ],
    },
    {
        "server": "refunds", "kind": "core", "owner": "payments-platform", "environment": "prod", "region": "us", "registered": True,
        "tools": [
            {"name": "refund_order", "handler": "refunds.refund_order", "annotations": WRITE,
             "description": _refund_desc, "inputSchema": _refund_schema,
             "gov": gov("order.refund", side_effect="financial_write", risk="high", scopes=["refunds:write"], approval=REFUND_APPROVAL, binding="order_refund")},
            {"name": "get_refund_status", "handler": "refunds.get_refund_status", "annotations": RO,
             "description": "Get refunds and their status for an order or refund id.",
             "inputSchema": obj({"order_id": ORDER_ID, "refund_id": {"type": "string", "pattern": "^RF-[0-9]+$"}}, []),
             "gov": gov("refund.status", scopes=["payments:read"])},
        ],
    },
    {
        "server": "promotions", "kind": "core", "owner": "customer-care", "environment": "prod", "region": "global", "registered": True,
        "tools": [
            {"name": "issue_store_credit", "handler": "promotions.issue_store_credit", "annotations": WRITE,
             "description": "Issue store credit to a customer account. Credit is spent on future orders; it is not returned to the card.",
             "inputSchema": obj({"customer_id": CUSTOMER_ID, "amount": AMOUNT, "reason": {"type": "string"}}, ["customer_id", "amount", "reason"]),
             "gov": gov("customer.store_credit", side_effect="financial_write", risk="medium", scopes=["credits:write"], approval=CREDIT_APPROVAL, binding="customer_credit")},
            {"name": "get_credit_balance", "handler": "promotions.get_credit_balance", "annotations": RO,
             "description": "Get a customer's store credit balance.",
             "inputSchema": obj({"customer_id": CUSTOMER_ID}, ["customer_id"]),
             "gov": gov("customer.credit_balance", scopes=["customers:read"])},
        ],
    },
    {
        "server": "shipping", "kind": "core", "owner": "logistics", "environment": "prod", "region": "global", "registered": True,
        "tools": [
            {"name": "track_shipment", "handler": "shipping.track_shipment", "annotations": RO,
             "description": "Get the current shipment status, carrier, tracking number and ETA for an order.",
             "inputSchema": obj({"order_id": ORDER_ID}, ["order_id"]),
             "gov": gov("shipment.track", scopes=["shipping:read"])},
            {"name": "create_return_label", "handler": "shipping.create_return_label", "annotations": WRITE,
             "description": "Create a prepaid return shipping label for a delivered order.",
             "inputSchema": obj({"order_id": ORDER_ID, "reason": {"type": "string"}}, ["order_id"]),
             "gov": gov("return.create_label", side_effect="write", risk="low", scopes=["returns:write"], binding="order_entity")},
        ],
    },
    {
        "server": "crm", "kind": "core", "owner": "customer-data", "environment": "prod", "region": "global", "registered": True,
        "tools": [
            {"name": "get_customer", "handler": "crm.get_customer", "annotations": RO,
             "description": "Look up a customer profile by customer id or email.",
             "inputSchema": obj({"customer_id": CUSTOMER_ID, "email": {"type": "string"}}, []),
             "gov": gov("customer.lookup", scopes=["customers:read"])},
            {"name": "update_customer_email", "handler": "crm.update_customer_email", "annotations": WRITE,
             "description": "Change the email address on a customer profile.",
             "inputSchema": obj({"customer_id": CUSTOMER_ID, "email": {"type": "string"}}, ["customer_id", "email"]),
             "gov": gov("customer.update_email", side_effect="write", risk="medium", scopes=["customers:write"], binding="customer_entity")},
            {"name": "update_default_address", "handler": "crm.update_default_address", "annotations": WRITE,
             "description": "Update the default address saved on a customer profile. Does not change existing orders.",
             "inputSchema": obj({"customer_id": CUSTOMER_ID, "address": {"type": "string"}}, ["customer_id", "address"]),
             "gov": gov("customer.update_default_address", side_effect="write", risk="medium", scopes=["customers:write"], binding="customer_entity")},
        ],
    },
    {
        "server": "helpdesk", "kind": "core", "owner": "customer-care", "environment": "prod", "region": "global", "registered": True,
        "tools": [
            {"name": "get_ticket", "handler": "helpdesk.get_ticket", "annotations": RO,
             "description": "Get a support ticket and its history.",
             "inputSchema": obj({"ticket_id": TICKET_ID}, ["ticket_id"]),
             "gov": gov("ticket.lookup", scopes=["tickets:read"])},
            {"name": "add_internal_note", "handler": "helpdesk.add_internal_note", "annotations": WRITE,
             "description": "Add an internal (agent-only) note to a support ticket.",
             "inputSchema": obj({"ticket_id": TICKET_ID, "note": {"type": "string"}}, ["ticket_id", "note"]),
             "gov": gov("ticket.add_note", side_effect="write", scopes=["tickets:write"])},
            {"name": "reply_to_customer", "handler": "helpdesk.reply_to_customer", "annotations": WRITE,
             "description": "Send a reply to the customer on a support ticket.",
             "inputSchema": obj({"ticket_id": TICKET_ID, "message": {"type": "string"}}, ["ticket_id", "message"]),
             "gov": gov("ticket.reply", side_effect="write", scopes=["tickets:write"])},
            {"name": "escalate_ticket", "handler": "helpdesk.escalate_ticket", "annotations": WRITE,
             "description": "Escalate a support ticket to another team (tier2, payments, logistics).",
             "inputSchema": obj({"ticket_id": TICKET_ID, "team": {"type": "string", "enum": ["tier2", "payments", "logistics"]}, "reason": {"type": "string"}}, ["ticket_id", "team"]),
             "gov": gov("ticket.escalate", side_effect="write", scopes=["tickets:write"])},
        ],
    },
    # ------------------------------------------------------------------ regional implementation (authoritative for EU entities only)
    {
        "server": "refunds_eu", "kind": "regional", "owner": "payments-platform-eu", "environment": "prod", "region": "eu", "registered": True,
        "tools": [
            {"name": "refund_order", "handler": "refunds.refund_order", "annotations": WRITE,
             "description": _refund_desc + " EU storefront.", "inputSchema": _refund_schema,
             "gov": gov("order.refund", side_effect="financial_write", risk="high", scopes=["refunds:write"], approval=REFUND_APPROVAL, binding="order_refund")},
            {"name": "get_refund_status", "handler": "refunds.get_refund_status", "annotations": RO,
             "description": "Get refunds and their status for an order or refund id (EU storefront).",
             "inputSchema": obj({"order_id": ORDER_ID, "refund_id": {"type": "string", "pattern": "^RF-[0-9]+$"}}, []),
             "gov": gov("refund.status", scopes=["payments:read"])},
        ],
    },
    # ------------------------------------------------------------------ environment copies (same published text as prod)
    {
        "server": "refunds_staging", "kind": "env_copy", "owner": "payments-platform", "environment": "staging", "region": "us", "registered": True,
        "tools": [
            {"name": "refund_order", "handler": "refunds.refund_order", "annotations": WRITE,
             "description": _refund_desc, "inputSchema": _refund_schema,
             "gov": gov("order.refund", side_effect="financial_write", risk="high", scopes=["refunds:write"], approval=REFUND_APPROVAL, binding="order_refund")},
        ],
    },
    {
        "server": "orders_staging", "kind": "env_copy", "owner": "order-management", "environment": "staging", "region": "global", "registered": True,
        "tools": [
            {"name": "get_order", "handler": "orders.get_order", "annotations": RO,
             "description": "Get an order: status, items, totals, currency, customer and shipping address.",
             "inputSchema": obj({"order_id": ORDER_ID}, ["order_id"]),
             "gov": gov("order.lookup", scopes=["orders:read"])},
            {"name": "cancel_order", "handler": "orders.cancel_order", "annotations": DESTRUCTIVE,
             "description": "Cancel an order that has not shipped yet.",
             "inputSchema": obj({"order_id": ORDER_ID, "reason": {"type": "string"}}, ["order_id"]),
             "gov": gov("order.cancel", side_effect="write", risk="medium", scopes=["orders:write"], binding="order_entity")},
        ],
    },
    # ------------------------------------------------------------------ retired but still running
    {
        "server": "payments_legacy", "kind": "legacy", "owner": "payments-platform", "environment": "prod", "region": "global", "registered": True,
        "tools": [
            {"name": "refund_charge_v1", "handler": "payments_legacy.refund_charge_v1", "annotations": WRITE,
             "description": "Refund a card charge (v1). Returns money for the given payment id and amount.",
             "inputSchema": obj({"payment_id": PAYMENT_ID, "amount": AMOUNT}, ["payment_id", "amount"]),
             "gov": gov("order.refund", side_effect="financial_write", risk="high", scopes=["refunds:write"], lifecycle="retired", replaced_by="refunds.refund_order")},
            {"name": "get_charge_v1", "handler": "payments_legacy.get_charge_v1", "annotations": RO,
             "description": "Get a card charge by payment id (v1).",
             "inputSchema": obj({"payment_id": PAYMENT_ID}, ["payment_id"]),
             "gov": gov("payment.get_charge", scopes=["payments:read"], lifecycle="retired", replaced_by="payments.get_charge")},
        ],
    },
    {
        "server": "carrier_legacy", "kind": "legacy", "owner": "logistics", "environment": "prod", "region": "global", "registered": True,
        "tools": [
            {"name": "get_tracking_v1", "handler": "carrier_legacy.get_tracking_v1", "annotations": RO,
             "description": "Tracking status lookup by tracking number (carrier feed).",
             "inputSchema": obj({"tracking_number": {"type": "string"}}, ["tracking_number"]),
             "gov": gov("shipment.track", scopes=["shipping:read"], lifecycle="retired", replaced_by="shipping.track_shipment")},
        ],
    },
    {
        "server": "helpdesk_legacy", "kind": "legacy", "owner": "customer-care", "environment": "prod", "region": "global", "registered": True,
        "tools": [
            {"name": "add_ticket_comment", "handler": "helpdesk_legacy.add_ticket_comment", "annotations": WRITE,
             "description": "Add a comment to a support ticket.",
             "inputSchema": obj({"ticket_id": TICKET_ID, "comment": {"type": "string"}}, ["ticket_id", "comment"]),
             "gov": gov("ticket.add_note", side_effect="write", scopes=["tickets:write"], lifecycle="retired", replaced_by="helpdesk.add_internal_note")},
        ],
    },
    # ------------------------------------------------------------------ vendor duplicates (registered, active, not authoritative)
    {
        "server": "paygate", "kind": "vendor", "owner": "vendor:paygate", "environment": "prod", "region": "global", "registered": True,
        "tools": [
            {"name": "refund_charge", "handler": "paygate.refund_charge",
             "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
             "description": "PayGate: create a refund for a charge. Money is returned to the card used for the charge.",
             "inputSchema": obj({"payment_id": PAYMENT_ID, "amount": AMOUNT, "note": {"type": "string"}}, ["payment_id", "amount"]),
             "gov": gov("order.refund", side_effect="financial_write", risk="high", scopes=["refunds:write"])},
            {"name": "get_charge_status", "handler": "paygate.get_charge_status", "annotations": {**RO, "openWorldHint": True},
             "description": "PayGate: get the processor status of a charge.",
             "inputSchema": obj({"payment_id": PAYMENT_ID}, ["payment_id"]),
             "gov": gov("payment.get_charge", scopes=["payments:read"])},
        ],
    },
    {
        "server": "shipfast", "kind": "vendor", "owner": "vendor:shipfast", "environment": "prod", "region": "global", "registered": True,
        "tools": [
            {"name": "track_package", "handler": "shipfast.track_package", "annotations": {**RO, "openWorldHint": True},
             "description": "ShipFast: track a package by tracking number.",
             "inputSchema": obj({"tracking_number": {"type": "string"}}, ["tracking_number"]),
             "gov": gov("shipment.track", scopes=["shipping:read"])},
        ],
    },
    # ------------------------------------------------------------------ shadow: running, reachable, never registered
    {
        "server": "marketing_ops", "kind": "shadow", "owner": "marketing (unregistered)", "environment": "prod", "region": "global", "registered": False,
        "tools": [
            {"name": "bulk_goodwill_refund", "handler": "marketing_ops.bulk_goodwill_refund", "annotations": WRITE,
             "description": "Send goodwill refunds to one or more customers (apology or win-back campaigns). Pays the amount to each customer.",
             "inputSchema": obj({"customer_ids": {"type": "array", "items": {"type": "string"}}, "amount": AMOUNT, "campaign": {"type": "string"}}, ["customer_ids", "amount"]),
             "gov": None},
            {"name": "list_campaigns", "handler": "marketing_ops.list_campaigns", "annotations": RO,
             "description": "List active marketing campaigns.",
             "inputSchema": obj({}, []),
             "gov": None},
        ],
    },
]

CORE_CAPABILITIES: dict[str, dict[str, Any]] = {
    "order.lookup": {"description": "Look up an order's status, items, totals, customer and shipping address.", "owner": "order-management", "authoritative": {"global": "orders.get_order"}, "entity": "order"},
    "order.search": {"description": "Find a customer's orders.", "owner": "order-management", "authoritative": {"global": "orders.search_orders"}, "entity": "customer"},
    "order.cancel": {"description": "Cancel an order that has not shipped.", "owner": "order-management", "authoritative": {"global": "orders.cancel_order"}, "entity": "order"},
    "order.update_shipping_address": {"description": "Change the delivery address of an unshipped order.", "owner": "order-management", "authoritative": {"global": "orders.update_shipping_address"}, "entity": "order", "user_owned": ["address"]},
    "order.replacement": {"description": "Send a free replacement for an item on a delivered order.", "owner": "order-management", "authoritative": {"global": "orders.create_replacement_order"}, "entity": "order", "user_owned": ["sku"]},
    "payment.list_charges": {"description": "List the charges captured on an order.", "owner": "payments-platform", "authoritative": {"global": "payments.list_charges"}, "entity": "order"},
    "payment.get_charge": {"description": "Get one charge by payment id.", "owner": "payments-platform", "authoritative": {"global": "payments.get_charge"}, "entity": "payment"},
    "order.refund": {"description": "Return money for an order to the original payment method, recorded against the order.", "owner": "payments-platform", "authoritative": {"us": "refunds.refund_order", "eu": "refunds_eu.refund_order"}, "entity": "order", "user_owned": ["amount"]},
    "refund.status": {"description": "Check refunds already issued on an order.", "owner": "payments-platform", "authoritative": {"us": "refunds.get_refund_status", "eu": "refunds_eu.get_refund_status"}, "entity": "order"},
    "customer.store_credit": {"description": "Give a customer store credit (spent on future orders, not returned to the card).", "owner": "customer-care", "authoritative": {"global": "promotions.issue_store_credit"}, "entity": "customer", "user_owned": ["amount"]},
    "customer.credit_balance": {"description": "Get a customer's store credit balance.", "owner": "customer-care", "authoritative": {"global": "promotions.get_credit_balance"}, "entity": "customer"},
    "shipment.track": {"description": "Get shipment status, carrier, tracking number and ETA for an order.", "owner": "logistics", "authoritative": {"global": "shipping.track_shipment"}, "entity": "order"},
    "return.create_label": {"description": "Create a prepaid return label for a delivered order.", "owner": "logistics", "authoritative": {"global": "shipping.create_return_label"}, "entity": "order"},
    "customer.lookup": {"description": "Look up a customer profile.", "owner": "customer-data", "authoritative": {"global": "crm.get_customer"}, "entity": "customer"},
    "customer.update_email": {"description": "Change the email address on a customer profile.", "owner": "customer-data", "authoritative": {"global": "crm.update_customer_email"}, "entity": "customer", "user_owned": ["email"]},
    "customer.update_default_address": {"description": "Change the default address saved on a customer profile (not existing orders).", "owner": "customer-data", "authoritative": {"global": "crm.update_default_address"}, "entity": "customer", "user_owned": ["address"]},
    "ticket.lookup": {"description": "Read a support ticket.", "owner": "customer-care", "authoritative": {"global": "helpdesk.get_ticket"}, "entity": "ticket"},
    "ticket.add_note": {"description": "Add an internal note to a support ticket.", "owner": "customer-care", "authoritative": {"global": "helpdesk.add_internal_note"}, "entity": "ticket"},
    "ticket.reply": {"description": "Reply to the customer on a support ticket.", "owner": "customer-care", "authoritative": {"global": "helpdesk.reply_to_customer"}, "entity": "ticket"},
    "ticket.escalate": {"description": "Escalate a support ticket to another team.", "owner": "customer-care", "authoritative": {"global": "helpdesk.escalate_ticket"}, "entity": "ticket"},
}

SUPPORT_T1 = [
    "orders:read", "orders:write", "payments:read", "refunds:write", "credits:write", "shipping:read",
    "returns:write", "customers:read", "tickets:read", "tickets:write",
]
ROLES = {
    "support_t1": SUPPORT_T1,
    "support_t2": SUPPORT_T1 + ["customers:write"],
}
# The support assistant deployment's own ceiling: it may act for t1 or t2, never beyond.
AGENTS = {"support-assistant": SUPPORT_T1 + ["customers:write"]}
