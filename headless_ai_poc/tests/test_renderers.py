"""H6, the unit half: one response, four presentations, same meaning; rendering is a pure function."""

from __future__ import annotations

import json

from headless_ai_platform.contracts import CapabilityResponse
from headless_ai_platform.renderers import api, cli, slack, web

WAITING = {
    "capability": "incident.remediation", "capability_version": "incident.remediation@1", "workflow_id": "wf-0123456789",
    "status": "WAITING_APPROVAL",
    "state": {"incident_id": "INC-4917", "service": "checkout-api", "environment": "production",
              "summary": "v4.17 shrank the orders-db pool from 50 to 10", "suspect": "checkout-api v4.17 (DEP-88213)",
              "confidence": "high", "policy_decision": "REQUIRE_APPROVAL", "policy_rule": "P4-prod-high-risk-approval",
              "approval_status": "PENDING", "approval_required_role": "incident-commander", "current_step": "await_approval",
              "recommended_action": {"tool": "source_control.rollback_release", "target": "v4.16",
                                     "environment": "production",
                                     "description": "rollback release checkout-api to v4.16 in production"}},
    "available_actions": [
        {"action_id": "approve-remediation", "type": "APPROVE", "label": "Approve source_control.rollback_release → v4.16",
         "required_role": "incident-commander", "allowed_for_actor": True, "binding": "abc123"},
        {"action_id": "reject-remediation", "type": "REJECT", "label": "Reject", "required_role": "incident-commander",
         "allowed_for_actor": True, "binding": "abc123"}],
    "actor": {"principal_id": "alice", "channel": "slack"}, "started_by": {"principal_id": "alice", "channel": "slack"},
    "trace_id": "t" * 32,
}


def response(**changes) -> CapabilityResponse:
    return CapabilityResponse.model_validate({**WAITING, **changes})


def test_each_channel_offers_the_same_actions_in_its_own_form():
    r = response()
    buttons = [e["action_id"] for b in slack.render(r)["blocks"] if b["type"] == "actions" for e in b["elements"]]
    card = web.render(r)
    text = cli.render(r)
    body = api.render(r)
    assert buttons == ["approve-remediation", "reject-remediation"]
    assert "data-action='approve-remediation'" in card and "data-action='reject-remediation'" in card
    assert f"hai approve {r.workflow_id}" in text and f"hai reject {r.workflow_id}" in text
    assert [a["action_id"] for a in body["available_actions"]] == buttons
    assert cli.exit_code(r) == 10


def test_every_rendering_carries_the_same_facts():
    r = response()
    outputs = [json.dumps(slack.render(r)), web.render(r), cli.render(r), json.dumps(api.render(r))]
    for fact in ("INC-4917", "wf-0123456789", "v4.16"):
        assert all(fact in o for o in outputs), fact


def test_a_person_without_the_role_sees_no_slack_button_and_a_disabled_web_button():
    denied = [{**a, "allowed_for_actor": False} for a in WAITING["available_actions"]]
    r = response(available_actions=denied, actor={"principal_id": "bob", "channel": "slack"})
    assert not [b for b in slack.render(r)["blocks"] if b["type"] == "actions"]
    assert "incident-commander" in json.dumps(slack.render(r))
    assert web.render(r).count(" disabled") == 2
    assert "# needs role incident-commander" in cli.render(r)


def test_web_card_escapes_model_text():
    evil = {**WAITING["state"], "summary": "<img src=x onerror=alert(1)>"}
    card = web.render(response(state=evil))
    assert "<img" not in card and "&lt;img" in card


def test_renderers_are_deterministic_and_leave_the_response_unchanged():
    r = response()
    before = r.model_dump_json()
    for fn in (slack.render, web.render, cli.render, api.render):
        assert fn(r) == fn(r)
    assert r.model_dump_json() == before


def test_api_rendering_is_the_contract():
    r = response()
    body = api.render(r)
    assert CapabilityResponse.model_validate({k: v for k, v in body.items() if k != "links"}) == r


def test_completed_renders_everywhere():
    done = {**WAITING["state"], "approval_status": "APPROVED", "approved_by": "alice", "verified": True,
            "p95_ms": 200.0, "slo_p95_ms": 400.0, "current_step": "complete"}
    r = response(status="COMPLETED", state=done, available_actions=[])
    assert "approved by alice" in json.dumps(slack.render(r))
    assert "status-completed" in web.render(r) and "class='now'" not in web.render(r)
    assert cli.exit_code(r) == 0 and "p95 200 ms" in cli.render(r)
