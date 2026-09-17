"""The boundary itself, over an in-memory platform: idempotency, stale buttons, subscriptions and delivery."""

from __future__ import annotations

import pytest

from headless_ai_platform.contracts import CapabilityError, ErrorCode, Status
from headless_ai_platform.gateway import CapabilityGateway
from headless_ai_platform.interactions import InteractionStore
from tests.conftest import run
from tests.fakes import FakePlatform

CAP = "incident.remediation"


@pytest.fixture
def gw(tmp_path):
    return CapabilityGateway(FakePlatform(), InteractionStore(tmp_path / "h.db"))


def start(channel="slack", subject="U04ALICE", **ctx):
    return {"capability": CAP, "operation": "start", "actor": {"channel": channel, "channel_subject": subject},
            "input": {"incident_id": "INC-4917"}, "channel_context": ctx}


def act(wf, action="approve-remediation", channel="web", subject="oidc|alice-92ab", binding=None, **ctx):
    return {"capability": CAP, "operation": "act", "workflow_id": wf, "action_id": action, "binding": binding,
            "actor": {"channel": channel, "channel_subject": subject}, "channel_context": ctx}


def test_a_retried_webhook_joins_the_same_workflow(gw):
    async def go():
        a = await gw.handle(start(idempotency_key="Ev01"), wait=True)
        b = await gw.handle(start(idempotency_key="Ev01"), wait=True)
        c = await gw.handle(start(idempotency_key="Ev02"), wait=True)
        return a, b, c

    a, b, c = run(go())
    assert a.workflow_id == b.workflow_id != c.workflow_id
    assert sum(call.startswith("submit") for call in gw.platform.calls) == 2


def test_a_stale_button_is_a_conflict_and_changes_nothing(gw):
    async def go():
        r = await gw.handle(start(), wait=True)
        with pytest.raises(CapabilityError) as exc:
            await gw.handle(act(r.workflow_id, binding="0000000000000000"), wait=True)
        return r, exc.value

    r, err = run(go())
    assert err.code is ErrorCode.CONFLICT
    assert gw.platform.view(r.workflow_id)["status"] == "WAITING_APPROVAL"


def test_a_second_decision_from_another_channel_is_a_conflict(gw):
    async def go():
        r = await gw.handle(start(), wait=True)
        b = r.action(r.available_actions[0].type).binding
        await gw.handle(act(r.workflow_id, binding=b), wait=True)
        with pytest.raises(CapabilityError) as exc:
            await gw.handle(act(r.workflow_id, channel="slack", subject="U04ALICE", binding=b), wait=True)
        return exc.value

    assert run(go()).code is ErrorCode.CONFLICT


def test_unknown_workflow_capability_and_action(gw):
    async def go():
        errors = []
        for payload in (act("wf-missing"), {**start(), "capability": "billing.refund"},
                        act((await gw.handle(start(), wait=True)).workflow_id, action="deploy-anything")):
            try:
                await gw.handle(payload, wait=True)
            except CapabilityError as exc:
                errors.append(exc.code)
        return errors

    assert run(go()) == [ErrorCode.NOT_FOUND, ErrorCode.UNKNOWN_CAPABILITY, ErrorCode.CONFLICT]


def test_every_interaction_is_recorded_with_its_principal_and_outcome(gw):
    async def go():
        r = await gw.handle(start(thread_ref="T1/C1/1"), wait=True)
        try:
            await gw.handle(act(r.workflow_id, subject="oidc|bob-51cd"), wait=True)
        except CapabilityError:
            pass
        await gw.handle(act(r.workflow_id), wait=True)
        return r

    r = run(go())
    rows = gw.store.interactions(r.workflow_id)
    assert [(x["channel"], x["principal_id"], x["operation"], x["outcome"]) for x in rows] == [
        ("slack", "alice", "start", "OK"), ("web", "bob", "act", "FORBIDDEN"), ("web", "alice", "act", "OK")]
    assert rows[0]["thread_ref"] == "T1/C1/1"


def test_subscribers_get_one_message_per_status_and_failures_stay_queued(gw):
    sent, up = [], {"slack": False}

    async def slack_sender(address, thread_ref, response):
        if not up["slack"]:
            raise ConnectionError("slack unreachable")
        sent.append((address, thread_ref, response["status"]))

    async def go():
        r = await gw.handle(start(thread_ref="T1/C1/1", reply_to="https://hooks.example/slack"), wait=True)
        first = await gw.deliver({"slack": slack_sender})              # Slack is down
        await gw.handle(act(r.workflow_id, binding=r.available_actions[0].binding), wait=True)
        second = await gw.deliver({"slack": slack_sender})             # still down; the workflow finished anyway
        up["slack"] = True
        third = await gw.deliver({"slack": slack_sender})              # back: both updates arrive, in order
        fourth = await gw.deliver({"slack": slack_sender})
        gw.reconcile(r.workflow_id)                                    # reconciling again queues nothing new
        return r, first, second, third, fourth

    r, first, second, third, fourth = run(go())
    assert gw.platform.view(r.workflow_id)["status"] == Status.COMPLETED
    assert (first, second) == ({"delivered": 0, "failed": 1}, {"delivered": 0, "failed": 2})
    assert third == {"delivered": 2, "failed": 0} and fourth == {"delivered": 0, "failed": 0}
    assert [s[2] for s in sent] == ["WAITING_APPROVAL", "COMPLETED"]
    assert all(s[1] == "T1/C1/1" for s in sent)
    assert len(gw.store.outbox(r.workflow_id)) == 2


def test_notifications_are_rendered_for_the_subscriber_not_the_last_actor(gw):
    async def go():
        r = await gw.handle(start(subject="U04BOB", reply_to="https://hooks.example/slack"), wait=True)
        return r

    r = run(go())
    payload = gw.store.outbox(r.workflow_id)[0]["payload"]
    assert payload["actor"]["principal_id"] == "bob"
    assert all(a["allowed_for_actor"] is False for a in payload["available_actions"])
