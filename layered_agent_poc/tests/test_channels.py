"""Every channel turns its own format into the same platform command; none holds workflow logic."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_platform.channels.rest import create_app

pytestmark = pytest.mark.mcp


@pytest.fixture
def client(platform_env, monkeypatch):
    monkeypatch.setenv("LAP_RECOVER_ON_START", "0")
    app = create_app()
    with TestClient(app) as c:
        captured = []

        def fake_submit(cmd):
            captured.append(cmd)

            async def nothing():
                return None

            return "wf-fake", nothing()

        monkeypatch.setattr(app.state.svc, "submit", fake_submit)
        monkeypatch.setattr(app.state.svc, "workflow", lambda wf: {"workflow_id": wf, "incident_id": "INC-4917",
                                                                     "status": "RUNNING", "approval": None})
        c.captured = captured
        yield c


def test_rest_and_chat_produce_the_same_command(client):
    r = client.post("/v1/incidents/INC-4917/investigations", headers={"X-User-Id": "alice"},
                    json={"request": "Checkout latency is up, investigate"})
    assert r.status_code == 202 and r.json()["workflow_id"] == "wf-fake"
    r = client.post("/v1/chat/events", json={"type": "event_callback", "event": {
        "type": "app_mention", "user": "U04ALICE", "channel": "C-INC4917",
        "text": "<@UBOT> INC-4917 Checkout latency is up, investigate"}})
    assert r.status_code == 200 and r.json()["response_type"] == "in_channel"
    rest, chat = client.captured
    assert (rest.incident_id, rest.user_id, rest.request) == (chat.incident_id, chat.user_id, chat.request)
    assert (rest.channel, chat.channel) == ("rest", "chat")


def test_unknown_chat_user_is_rejected(client):
    r = client.post("/v1/chat/events", json={"type": "event_callback", "event": {
        "type": "app_mention", "user": "U999", "text": "INC-4917 please look"}})
    assert r.status_code == 403


def test_approval_without_a_pending_request_is_a_conflict(client):
    r = client.post("/v1/workflows/wf-none/approvals", headers={"X-User-Id": "alice"}, json={"approve": True})
    assert r.status_code == 409


def test_cli_builds_the_same_command(client):
    from agent_platform.channels import cli

    client.post("/v1/incidents/INC-4917/investigations", headers={"X-User-Id": "alice"},
                json={"request": "Checkout latency is up, investigate"})
    rest = client.captured[0]
    cmd = cli.command_from_args(cli.parser().parse_args(["run", "INC-4917", "Checkout latency is up, investigate", "--as", "alice"]))
    assert cmd.model_dump(exclude={"channel"}) == rest.model_dump(exclude={"channel"})
