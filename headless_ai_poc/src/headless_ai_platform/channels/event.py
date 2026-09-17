"""Event channel: machine-started work (an Alertmanager-shaped webhook).

    POST /events/alerts   {"alerts": [{"status": "firing", "fingerprint": "...", "labels": {...}}]}

No person pressed anything, so the request runs on behalf of whoever is on call for the service (see
config/channel_identities.yaml). A repeated alert with the same fingerprint joins the existing workflow.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from headless_ai_platform.channels import CAPABILITY, gateway, http_error
from headless_ai_platform.contracts import CapabilityError

router = APIRouter()
CHANNEL = "event"


@router.post("/events/alerts", status_code=202)
async def alerts(request: Request) -> dict[str, Any]:
    body = await request.json()
    source = body.get("receiver", "alertmanager")
    out = []
    for alert in body.get("alerts", []):
        labels = alert.get("labels", {})
        if alert.get("status") != "firing" or "incident_id" not in labels:
            continue
        try:
            resp = await gateway(request).handle({
                "capability": CAPABILITY, "operation": "start",
                "actor": {"channel": CHANNEL, "channel_subject": source},
                "input": {"incident_id": labels["incident_id"], "service": labels.get("service"),
                          "request": alert.get("annotations", {}).get("description") or None},
                "channel_context": {"idempotency_key": alert.get("fingerprint")}})
        except CapabilityError as exc:
            raise http_error(exc) from exc
        out.append({"fingerprint": alert.get("fingerprint"), "workflow_id": resp.workflow_id, "status": resp.status.value,
                    "on_behalf_of": resp.started_by.principal_id})
    return {"accepted": out}
