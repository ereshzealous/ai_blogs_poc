"""Deterministically generated tools from the rest of the (simulated) company.

These are not the commerce-support systems the benchmark cases need, but they are
what a real estate is full of: other business units' MCP servers.  Some are close
semantic neighbours of the core tools ("refund a subscription invoice", "refund a
marketplace order", "issue a credit note"), most are unrelated.  A few carry their own
sprawl (a retired copy, a staging copy).

Every generated tool is backed by a generic simulated handler; writes are recorded in
the effects ledger as ``distractor_write`` so any call to one is visible as an
unexpected side effect.  Server order is fixed so the 50/100/500 estates are nested.
"""

from __future__ import annotations

from typing import Any

from .core import DESTRUCTIVE, RO, WRITE, obj

S = {"type": "string"}
N = {"type": "number"}
I = {"type": "integer"}


def t(name, description, props, required, write=False, destructive=False):
    return {
        "name": name,
        "description": description,
        "inputSchema": obj(props, required),
        "annotations": DESTRUCTIVE if destructive else (WRITE if write else RO),
        "handler": "generic.write" if (write or destructive) else "generic.read",
    }


# ---------------------------------------------------------------- hand-written near-miss families
SUBSCRIPTIONS = [
    t("refund_subscription_invoice", "Refund a paid subscription invoice to the subscriber's card.", {"invoice_id": S, "amount": N}, ["invoice_id"], write=True),
    t("cancel_subscription", "Cancel a customer's subscription at the end of the billing period.", {"subscription_id": S}, ["subscription_id"], destructive=True),
    t("pause_subscription", "Pause a subscription for up to 3 billing cycles.", {"subscription_id": S, "cycles": I}, ["subscription_id"], write=True),
    t("resume_subscription", "Resume a paused subscription.", {"subscription_id": S}, ["subscription_id"], write=True),
    t("change_plan", "Move a subscription to a different plan.", {"subscription_id": S, "plan_id": S}, ["subscription_id", "plan_id"], write=True),
    t("get_subscription", "Get a subscription by id.", {"subscription_id": S}, ["subscription_id"]),
    t("list_subscriptions", "List a customer's subscriptions.", {"customer_id": S}, ["customer_id"]),
    t("list_invoices", "List invoices for a subscription.", {"subscription_id": S}, ["subscription_id"]),
    t("get_invoice", "Get a subscription invoice.", {"invoice_id": S}, ["invoice_id"]),
    t("retry_failed_payment", "Retry the card charge for a failed subscription invoice.", {"invoice_id": S}, ["invoice_id"], write=True),
    t("update_billing_email", "Change the billing email used for subscription invoices.", {"subscription_id": S, "email": S}, ["subscription_id", "email"], write=True),
    t("update_payment_method", "Replace the card on file for a subscription.", {"subscription_id": S, "payment_method_token": S}, ["subscription_id", "payment_method_token"], write=True),
    t("apply_subscription_discount", "Apply a discount code to a subscription.", {"subscription_id": S, "code": S}, ["subscription_id", "code"], write=True),
    t("issue_subscription_credit", "Credit a subscriber's next invoice.", {"subscription_id": S, "amount": N}, ["subscription_id", "amount"], write=True),
    t("get_dunning_status", "Get the dunning (failed payment recovery) status of a subscription.", {"subscription_id": S}, ["subscription_id"]),
    t("preview_proration", "Preview proration for a plan change.", {"subscription_id": S, "plan_id": S}, ["subscription_id", "plan_id"]),
]

GIFT_CARDS = [
    t("issue_gift_card", "Issue a new gift card to a recipient email.", {"recipient_email": S, "amount": N}, ["recipient_email", "amount"], write=True),
    t("refund_gift_card_purchase", "Refund the purchase of a gift card to the buyer's card and void the card.", {"gift_card_id": S}, ["gift_card_id"], write=True),
    t("void_gift_card", "Void a gift card so it can no longer be used.", {"gift_card_id": S}, ["gift_card_id"], destructive=True),
    t("get_gift_card_balance", "Get the remaining balance on a gift card.", {"gift_card_id": S}, ["gift_card_id"]),
    t("reload_gift_card", "Add value to an existing gift card.", {"gift_card_id": S, "amount": N}, ["gift_card_id", "amount"], write=True),
    t("transfer_gift_card_balance", "Move balance from one gift card to another.", {"from_card": S, "to_card": S}, ["from_card", "to_card"], write=True),
    t("list_gift_cards", "List gift cards bought by a customer.", {"customer_id": S}, ["customer_id"]),
    t("resend_gift_card_email", "Resend the gift card email to the recipient.", {"gift_card_id": S}, ["gift_card_id"], write=True),
    t("extend_gift_card_expiry", "Extend a gift card's expiry date.", {"gift_card_id": S, "months": I}, ["gift_card_id"], write=True),
    t("lock_gift_card", "Temporarily lock a gift card suspected of fraud.", {"gift_card_id": S}, ["gift_card_id"], write=True),
    t("get_gift_card_transactions", "List transactions on a gift card.", {"gift_card_id": S}, ["gift_card_id"]),
    t("bulk_issue_gift_cards", "Issue gift cards in bulk for a corporate order.", {"batch_id": S, "count": I, "amount": N}, ["batch_id", "count", "amount"], write=True),
]

LOYALTY = [
    t("get_points_balance", "Get a loyalty member's points balance.", {"member_id": S}, ["member_id"]),
    t("adjust_points", "Add or remove loyalty points with a reason.", {"member_id": S, "points": I, "reason": S}, ["member_id", "points"], write=True),
    t("reverse_points_for_order", "Reverse the loyalty points earned on an order.", {"order_id": S}, ["order_id"], write=True),
    t("award_bonus_points", "Award bonus points as a goodwill gesture.", {"member_id": S, "points": I}, ["member_id", "points"], write=True),
    t("get_member_tier", "Get a member's loyalty tier.", {"member_id": S}, ["member_id"]),
    t("upgrade_member_tier", "Upgrade a member to a higher loyalty tier.", {"member_id": S, "tier": S}, ["member_id", "tier"], write=True),
    t("list_rewards", "List rewards a member can redeem.", {"member_id": S}, ["member_id"]),
    t("redeem_reward", "Redeem a reward for a member.", {"member_id": S, "reward_id": S}, ["member_id", "reward_id"], write=True),
    t("expire_points", "Expire a member's points past their expiry date.", {"member_id": S}, ["member_id"], destructive=True),
    t("get_member_by_email", "Find a loyalty member by email.", {"email": S}, ["email"]),
    t("merge_members", "Merge two duplicate loyalty memberships.", {"primary_id": S, "duplicate_id": S}, ["primary_id", "duplicate_id"], destructive=True),
    t("get_points_history", "Get a member's points history.", {"member_id": S}, ["member_id"]),
]

MARKETPLACE = [
    t("refund_marketplace_order", "Refund a marketplace (third-party seller) order to the buyer.", {"marketplace_order_id": S, "amount": N}, ["marketplace_order_id", "amount"], write=True),
    t("cancel_marketplace_order", "Cancel a marketplace order before the seller ships it.", {"marketplace_order_id": S}, ["marketplace_order_id"], destructive=True),
    t("track_marketplace_shipment", "Track a shipment sent by a marketplace seller.", {"marketplace_order_id": S}, ["marketplace_order_id"]),
    t("refund_seller_fee", "Refund a fee charged to a marketplace seller.", {"seller_id": S, "amount": N}, ["seller_id", "amount"], write=True),
    t("issue_seller_payout", "Pay out a seller's available balance.", {"seller_id": S}, ["seller_id"], write=True),
    t("hold_seller_payout", "Put a hold on a seller's payouts.", {"seller_id": S, "reason": S}, ["seller_id"], write=True),
    t("get_seller", "Get a marketplace seller profile.", {"seller_id": S}, ["seller_id"]),
    t("list_seller_orders", "List a seller's marketplace orders.", {"seller_id": S}, ["seller_id"]),
    t("get_marketplace_order", "Get a marketplace order.", {"marketplace_order_id": S}, ["marketplace_order_id"]),
    t("open_buyer_dispute", "Open a dispute between a buyer and a seller.", {"marketplace_order_id": S, "reason": S}, ["marketplace_order_id"], write=True),
    t("resolve_buyer_dispute", "Resolve a marketplace dispute in favour of buyer or seller.", {"dispute_id": S, "outcome": S}, ["dispute_id", "outcome"], write=True),
    t("suspend_seller", "Suspend a marketplace seller.", {"seller_id": S, "reason": S}, ["seller_id"], destructive=True),
    t("update_seller_bank_account", "Update a seller's payout bank account.", {"seller_id": S, "iban": S}, ["seller_id", "iban"], write=True),
    t("list_open_disputes", "List open marketplace disputes.", {"limit": I}, []),
    t("get_seller_rating", "Get a seller's rating.", {"seller_id": S}, ["seller_id"]),
    t("approve_seller_listing", "Approve a seller's product listing.", {"listing_id": S}, ["listing_id"], write=True),
    t("remove_seller_listing", "Remove a seller's product listing.", {"listing_id": S}, ["listing_id"], destructive=True),
    t("get_seller_balance", "Get a seller's pending and available balance.", {"seller_id": S}, ["seller_id"]),
    t("export_seller_statement", "Export a seller's monthly statement.", {"seller_id": S, "month": S}, ["seller_id", "month"]),
    t("send_seller_message", "Send a message to a seller.", {"seller_id": S, "message": S}, ["seller_id", "message"], write=True),
    t("list_marketplace_returns", "List return requests for marketplace orders.", {"seller_id": S}, []),
    t("approve_marketplace_return", "Approve a return on a marketplace order.", {"marketplace_order_id": S}, ["marketplace_order_id"], write=True),
    t("charge_seller_penalty", "Charge a seller a policy penalty.", {"seller_id": S, "amount": N}, ["seller_id", "amount"], write=True),
    t("get_marketplace_fees", "Get the current marketplace fee schedule.", {}, []),
]

B2B_BILLING = [
    t("issue_credit_note", "Issue a credit note against a business customer's invoice.", {"invoice_id": S, "amount": N}, ["invoice_id", "amount"], write=True),
    t("refund_invoice_payment", "Refund a payment received on a business invoice.", {"invoice_id": S, "amount": N}, ["invoice_id", "amount"], write=True),
    t("create_invoice", "Create an invoice for a business account.", {"account_id": S, "amount": N}, ["account_id", "amount"], write=True),
    t("void_invoice", "Void an unpaid business invoice.", {"invoice_id": S}, ["invoice_id"], destructive=True),
    t("get_business_account", "Get a business (B2B) account.", {"account_id": S}, ["account_id"]),
    t("update_billing_contact", "Update the billing contact on a business account.", {"account_id": S, "email": S}, ["account_id", "email"], write=True),
    t("list_open_invoices", "List unpaid invoices for a business account.", {"account_id": S}, ["account_id"]),
    t("record_wire_payment", "Record a wire transfer against an invoice.", {"invoice_id": S, "amount": N}, ["invoice_id", "amount"], write=True),
    t("set_payment_terms", "Set payment terms (net 30/60) for an account.", {"account_id": S, "terms": S}, ["account_id", "terms"], write=True),
    t("send_payment_reminder", "Email a payment reminder for an overdue invoice.", {"invoice_id": S}, ["invoice_id"], write=True),
    t("get_invoice_pdf", "Get the PDF link for an invoice.", {"invoice_id": S}, ["invoice_id"]),
    t("apply_account_credit", "Apply an account credit balance to an invoice.", {"invoice_id": S}, ["invoice_id"], write=True),
    t("get_credit_limit", "Get a business account's credit limit.", {"account_id": S}, ["account_id"]),
    t("raise_credit_limit", "Raise a business account's credit limit.", {"account_id": S, "limit": N}, ["account_id", "limit"], write=True),
    t("export_ar_aging", "Export the accounts receivable aging report.", {}, []),
    t("write_off_invoice", "Write off an uncollectible invoice.", {"invoice_id": S}, ["invoice_id"], destructive=True),
    t("list_credit_notes", "List credit notes for an account.", {"account_id": S}, ["account_id"]),
    t("create_quote", "Create a price quote for a business account.", {"account_id": S, "items": S}, ["account_id", "items"], write=True),
    t("convert_quote_to_invoice", "Convert an accepted quote into an invoice.", {"quote_id": S}, ["quote_id"], write=True),
    t("get_tax_exemption", "Get tax exemption certificates on file.", {"account_id": S}, ["account_id"]),
]

WARRANTY = [
    t("create_warranty_claim", "Open a manufacturer warranty claim for a product.", {"serial_number": S, "issue": S}, ["serial_number", "issue"], write=True),
    t("get_warranty_claim", "Get a warranty claim.", {"claim_id": S}, ["claim_id"]),
    t("approve_warranty_claim", "Approve a warranty claim.", {"claim_id": S}, ["claim_id"], write=True),
    t("reject_warranty_claim", "Reject a warranty claim.", {"claim_id": S, "reason": S}, ["claim_id", "reason"], write=True),
    t("check_warranty_status", "Check whether a serial number is under warranty.", {"serial_number": S}, ["serial_number"]),
    t("register_product", "Register a product for warranty.", {"serial_number": S, "customer_email": S}, ["serial_number", "customer_email"], write=True),
    t("list_claims_for_customer", "List warranty claims for a customer.", {"customer_email": S}, ["customer_email"]),
    t("ship_warranty_replacement", "Ship a replacement unit for an approved warranty claim.", {"claim_id": S}, ["claim_id"], write=True),
    t("extend_warranty", "Sell or apply an extended warranty.", {"serial_number": S, "months": I}, ["serial_number", "months"], write=True),
    t("get_repair_center", "Find the nearest authorised repair center.", {"postcode": S}, ["postcode"]),
    t("schedule_repair", "Schedule an in-person repair appointment.", {"claim_id": S, "date": S}, ["claim_id", "date"], write=True),
    t("close_warranty_claim", "Close a warranty claim.", {"claim_id": S}, ["claim_id"], write=True),
]

RETURNS_3PL = [
    t("schedule_return_pickup", "Schedule a courier pickup for a customer return (3PL partner).", {"rma_id": S, "date": S}, ["rma_id", "date"], write=True),
    t("get_rma_status", "Get the processing status of a return (RMA) at the 3PL warehouse.", {"rma_id": S}, ["rma_id"]),
    t("create_rma", "Create a return merchandise authorisation at the 3PL partner.", {"reference": S, "sku": S}, ["reference", "sku"], write=True),
    t("inspect_return", "Record the inspection result of a returned item.", {"rma_id": S, "grade": S}, ["rma_id", "grade"], write=True),
    t("restock_return", "Restock an inspected return into sellable inventory.", {"rma_id": S}, ["rma_id"], write=True),
    t("dispose_return", "Dispose of a returned item that cannot be resold.", {"rma_id": S}, ["rma_id"], destructive=True),
    t("list_pending_returns", "List returns awaiting inspection.", {"warehouse": S}, []),
    t("get_pickup_slots", "Get available courier pickup slots.", {"postcode": S}, ["postcode"]),
    t("cancel_return_pickup", "Cancel a scheduled return pickup.", {"rma_id": S}, ["rma_id"], destructive=True),
    t("print_packing_slip", "Generate a packing slip for a return.", {"rma_id": S}, ["rma_id"]),
    t("get_return_policy", "Get the 3PL partner's return handling policy.", {}, []),
    t("export_returns_report", "Export the weekly returns report.", {"week": S}, ["week"]),
    t("update_return_reason", "Update the reason code on a return.", {"rma_id": S, "reason_code": S}, ["rma_id", "reason_code"], write=True),
    t("get_carrier_for_return", "Get the courier assigned to a return.", {"rma_id": S}, ["rma_id"]),
]

FRAUD = [
    t("flag_order_for_review", "Flag an order for manual fraud review.", {"order_id": S, "reason": S}, ["order_id"], write=True),
    t("get_risk_score", "Get the fraud risk score for an order.", {"order_id": S}, ["order_id"]),
    t("accept_chargeback", "Accept a card chargeback without contesting it.", {"chargeback_id": S}, ["chargeback_id"], write=True),
    t("contest_chargeback", "Contest a chargeback with evidence.", {"chargeback_id": S, "evidence": S}, ["chargeback_id", "evidence"], write=True),
    t("list_chargebacks", "List open chargebacks.", {"status": S}, []),
    t("block_card", "Block a card fingerprint from future purchases.", {"card_fingerprint": S}, ["card_fingerprint"], destructive=True),
    t("allowlist_customer", "Add a customer to the fraud allowlist.", {"customer_id": S}, ["customer_id"], write=True),
    t("get_device_history", "Get device fingerprints seen for a customer.", {"customer_id": S}, ["customer_id"]),
    t("release_order_hold", "Release a fraud hold on an order.", {"order_id": S}, ["order_id"], write=True),
    t("cancel_fraudulent_order", "Cancel an order confirmed as fraudulent.", {"order_id": S}, ["order_id"], destructive=True),
    t("get_velocity_stats", "Get purchase velocity statistics for a card.", {"card_fingerprint": S}, ["card_fingerprint"]),
    t("report_account_takeover", "Report a suspected account takeover.", {"customer_id": S}, ["customer_id"], write=True),
    t("lock_customer_account", "Lock a customer account pending investigation.", {"customer_id": S}, ["customer_id"], destructive=True),
    t("get_chargeback", "Get a chargeback case.", {"chargeback_id": S}, ["chargeback_id"]),
    t("list_review_queue", "List orders waiting for fraud review.", {}, []),
    t("update_fraud_rule", "Update a fraud rule threshold.", {"rule_id": S, "threshold": N}, ["rule_id", "threshold"], write=True),
]

# ---------------------------------------------------------------- combinatorial departments
VERBS = [
    ("get_{o}", "Get a {oh} by id from the {title} system. Returns the full {oh} record, including status, owner, created and updated timestamps and linked records.", "id", False, False),
    ("list_{os}", "List {osh} in the {title} system, newest first. Returns summary rows (id, name, status, updated_at); use limit to page.", "list", False, False),
    ("create_{o}", "Create a new {oh} in the {title} system. Requires a name; optional details are stored as structured fields. Returns the new {oh} id.", "create", True, False),
    ("update_{o}", "Update fields on an existing {oh} in the {title} system. Only the fields provided are changed; returns the updated record.", "id+", True, False),
    ("search_{os}", "Search {osh} in the {title} system by keyword across names, descriptions and tags. Returns up to 20 matches ranked by relevance.", "query", False, False),
    ("archive_{o}", "Archive a {oh} in the {title} system so it no longer appears in active lists. An administrator can restore it.", "id", True, True),
    ("export_{os}", "Export {osh} from the {title} system to CSV for reporting. Returns a download link valid for 24 hours.", "list", False, False),
    ("approve_{o}", "Approve a pending {oh} in the {title} system. The approval is recorded with the caller's identity and a timestamp.", "id", True, False),
]

COMBINATORIAL: dict[str, tuple[str, list[str]]] = {
    "inventory": ("Inventory", ["stock_level", "stock_transfer", "reorder_rule", "cycle_count"]),
    "catalog": ("Product catalog", ["product", "product_variant", "category", "product_image"]),
    "warehouse": ("Warehouse operations", ["pick_list", "packing_station", "inbound_shipment", "bin_location"]),
    "pricing": ("Pricing", ["price_rule", "markdown", "price_list", "competitor_price"]),
    "procurement": ("Procurement", ["purchase_order", "supplier", "supplier_invoice", "rfq"]),
    "finance_gl": ("Finance general ledger", ["journal_entry", "gl_account", "cost_center", "accrual"]),
    "tax": ("Tax", ["tax_rate", "tax_filing", "nexus_registration"]),
    "hr": ("HR", ["employee", "leave_request", "job_requisition", "payroll_adjustment"]),
    "it_service": ("IT service desk", ["it_ticket", "laptop_request", "access_request", "software_license"]),
    "analytics": ("Analytics", ["dashboard", "report", "metric_definition"]),
    "marketing_email": ("Marketing email", ["email_campaign", "audience_segment", "email_template"]),
    "reviews": ("Product reviews", ["review", "review_response"]),
    "compliance": ("Compliance & legal", ["policy_document", "audit_finding", "data_request", "contract"]),
    "store_ops": ("Retail store operations", ["store_shift", "store_incident", "planogram"]),
    "facilities": ("Facilities", ["work_order", "meeting_room", "visitor_badge"]),
    "data_platform": ("Data platform", ["dataset", "pipeline_run", "data_quality_check"]),
    "security_ops": ("Security operations", ["security_alert", "vulnerability", "phishing_report"]),
}


def _plural(o: str) -> str:
    return o + ("es" if o.endswith(("s", "x", "ch")) else "s")


def combinatorial_tools(server: str, objects: list[str], count: int, title: str = "") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for verb in VERBS:
        for o in objects:
            if len(out) >= count:
                return out
            name_t, desc_t, shape, write, destructive = verb
            oh, os_ = o.replace("_", " "), _plural(o)
            osh = os_.replace("_", " ")
            idf = f"{o}_id"
            if shape == "id":
                props, req = {idf: S}, [idf]
            elif shape == "id+":
                props, req = {idf: S, "fields": {"type": "object"}}, [idf, "fields"]
            elif shape == "create":
                props, req = {"name": S, "details": {"type": "object"}}, ["name"]
            elif shape == "query":
                props, req = {"query": S}, ["query"]
            else:
                props, req = {"limit": I}, []
            out.append(t(name_t.format(o=o, os=os_), desc_t.format(oh=oh, osh=osh, title=title or server.replace("_", " ")), props, req, write=write, destructive=destructive))
    return out


def _copy(tools: list[dict[str, Any]], n: int, suffix: str = "") -> list[dict[str, Any]]:
    return [{**x, "name": x["name"] + suffix} for x in tools[:n]]


def generated_servers() -> list[dict[str, Any]]:
    """Ordered list of generated servers; estates take whole servers in this order (last one may be partial)."""
    plan: list[tuple[str, str, str, list[dict[str, Any]], dict[str, Any]]] = []

    def add(server, title, tools, kind="generated", environment="prod", lifecycle="active", replaced_by_server=None):
        plan.append((server, title, kind, tools, {"environment": environment, "lifecycle": lifecycle, "replaced_by_server": replaced_by_server}))

    def comb(server, n):
        title, objects = COMBINATORIAL[server]
        add(server, title, combinatorial_tools(server, objects, n, title))

    # 50-estate: core (34) + 16
    add("subscriptions", "Subscriptions billing", SUBSCRIPTIONS)
    # 100-estate: + 50
    add("gift_cards", "Gift cards", GIFT_CARDS)
    add("loyalty", "Loyalty program", LOYALTY)
    comb("inventory", 14)
    comb("catalog", 12)
    # 500-estate: + 400
    comb("warehouse", 14)
    add("marketplace", "Marketplace", MARKETPLACE)
    add("b2b_billing", "B2B billing", B2B_BILLING)
    add("warranty", "Warranty", WARRANTY)
    add("returns_3pl", "Returns (3PL partner)", RETURNS_3PL)
    add("fraud", "Fraud & chargebacks", FRAUD)
    comb("pricing", 20)
    comb("procurement", 24)
    comb("finance_gl", 26)
    comb("tax", 16)
    comb("hr", 28)
    comb("it_service", 28)
    comb("analytics", 22)
    comb("marketing_email", 22)
    comb("reviews", 12)
    comb("compliance", 26)
    comb("store_ops", 18)
    comb("facilities", 14)
    comb("data_platform", 14)
    comb("security_ops", 12)
    add("subscriptions_legacy", "Subscriptions billing (v1)", _copy(SUBSCRIPTIONS, 10), kind="generated_legacy", lifecycle="retired", replaced_by_server="subscriptions")
    add("gift_cards_staging", "Gift cards", _copy(GIFT_CARDS, 8), kind="generated_env_copy", environment="staging")

    servers = []
    for server, title, kind, tools, extra in plan:
        servers.append({
            "server": server,
            "title": title,
            "kind": kind,
            "owner": f"{server.replace('_legacy', '').replace('_staging', '')}-team",
            "environment": extra["environment"],
            "region": "global",
            "registered": True,
            "lifecycle": extra["lifecycle"],
            "replaced_by_server": extra["replaced_by_server"],
            "tools": tools,
        })
    return servers
