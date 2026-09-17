"""The adapters over HTTP, against the real platform: Slack, Web, REST and alert webhooks use one gateway."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from headless_ai_platform.server import create_app

pytestmark = pytest.mark.platform
ALICE_WEB, BOB_WEB = {"X-OIDC-Subject": "oidc|alice-92ab"}, {"X-OIDC-Subject": "oidc|bob-51cd"}


def mention(user: str, event_id: str, text: str = "<@UOPS> investigate INC-4917") -> dict:
    return {"type": "event_callback", "event_id": event_id, "team_id": "T1",
            "event": {"type": "app_mention", "user": user, "text": text, "channel": "C-INC", "ts": "1726.1", "team": "T1"}}


def press(user: str, action_id: str, value: str) -> dict:
    return {"type": "block_actions", "user": {"id": user}, "team": {"id": "T1"},
            "container": {"channel_id": "C-INC", "thread_ts": "1726.1"},
            "actions": [{"action_id": action_id, "value": value}]}


def wait_for(client: TestClient, wf: str, status: str, headers=ALICE_WEB, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/web/api/workflows/{wf}", headers=headers).json()
        if body["response"]["status"] == status:
            return body
        time.sleep(0.1)
    raise AssertionError(f"{wf} did not reach {status}: {body['response']['status']}")


@pytest.fixture
def client(platform_env, monkeypatch):
    monkeypatch.setenv("HAI_SLACK_URL", "http://127.0.0.1:9/unreachable")  # delivery fails and stays queued
    with TestClient(create_app(["slack", "web", "rest", "event"])) as c:
        yield c


def test_slack_to_web_to_rest_over_http(client):
    r = client.post("/slack/events", json=mention("U04ALICE", "Ev1"))
    assert r.status_code == 200 and r.json()["response_type"] == "in_channel"
    wf = r.json()["blocks"][0]["text"]["text"].split("`")[1]
    assert client.post("/slack/events", json=mention("U04ALICE", "Ev1")).json()["blocks"][0]["text"]["text"].split("`")[1] == wf
    page = wait_for(client, wf, "WAITING_APPROVAL")
    assert "data-action='approve-remediation'" in page["card"]

    denied = client.post("/slack/actions", json=press("U04BOB", "approve-remediation", f"{wf}|"))
    assert denied.json()["response_type"] == "ephemeral" and "incident-commander" in denied.json()["text"]
    assert client.post(f"/web/api/workflows/{wf}/actions", headers=BOB_WEB,
                       json={"action_id": "approve-remediation"}).status_code == 403
    stale = client.post(f"/web/api/workflows/{wf}/actions", headers=ALICE_WEB,
                        json={"action_id": "approve-remediation", "binding": "ffffffffffffffff"})
    assert stale.status_code == 409

    binding = page["response"]["available_actions"][0]["binding"]
    ok = client.post(f"/web/api/workflows/{wf}/actions", headers=ALICE_WEB,
                     json={"action_id": "approve-remediation", "binding": binding})
    assert ok.status_code == 202
    wait_for(client, wf, "COMPLETED")
    rest = client.get(f"/v1/capabilities/incident.remediation/workflows/{wf}", headers={"X-Subject": "api|alice"})
    assert rest.status_code == 200 and rest.json()["status"] == "COMPLETED" and rest.json()["started_by"]["channel"] == "slack"
    late = client.post("/slack/actions", json=press("U04ALICE", "approve-remediation", f"{wf}|{binding}"))
    assert late.json()["response_type"] == "ephemeral"                           # already decided on the web
    outbox = client.app.state.gateway.store.outbox(wf)
    assert [o["status"] for o in outbox] == ["WAITING_APPROVAL", "COMPLETED"] and all(o["state"] == "PENDING" for o in outbox)


def test_rest_contract_errors_and_forged_fields(client):
    h = {"X-Subject": "api|alice"}
    assert client.post("/v1/capabilities/incident.remediation/workflows", headers=h,
                       json={"input": {"incident_id": "INC-4917"}, "approved": True}).status_code == 422
    raw = {"capability": "incident.remediation", "operation": "start", "input": {"incident_id": "INC-4917"},
           "actor": {"channel": "rest", "channel_subject": "api|alice"}, "approved": True}
    assert client.post("/v1/capability-requests", headers=h, json=raw).status_code == 422
    assert client.post("/v1/capability-requests", headers=h, json={**raw, "schema_version": "2.0"}).status_code == 400
    assert client.get("/v1/capabilities/incident.remediation/workflows/wf-nope", headers=h).status_code == 404
    assert client.get("/v1/capabilities/incident.remediation/workflows/wf-nope",
                      headers={"X-Subject": "U04ALICE"}).status_code == 401   # a Slack id is not a REST identity


def test_an_alert_starts_the_capability_for_the_on_call_principal_once(client):
    alert = {"receiver": "alertmanager", "alerts": [{"status": "firing", "fingerprint": "fp-4917",
             "labels": {"incident_id": "INC-4917", "service": "checkout-api"}}]}
    first = client.post("/events/alerts", json=alert).json()["accepted"][0]
    again = client.post("/events/alerts", json=alert).json()["accepted"][0]
    assert first["workflow_id"] == again["workflow_id"] and first["on_behalf_of"] == "alice"
    done = wait_for(client, first["workflow_id"], "WAITING_APPROVAL")
    assert done["response"]["started_by"] == {"principal_id": "alice", "channel": "event"}
