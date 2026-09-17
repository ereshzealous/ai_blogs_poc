"""Quality gates against the real layered platform (MCP servers, policy, workflow, SQLite). Model answers are replayed
from Part 2's recording, so these run without Ollama and workflows run one after another."""

from __future__ import annotations

import pytest

from headless_ai_platform.contracts import ActionType, CapabilityError, ErrorCode, Status
from headless_ai_platform.renderers import api, cli, slack, web
from headless_ai_platform.runtime import open_gateway
from tests.conftest import run

pytestmark = pytest.mark.platform
CAP = "incident.remediation"
SUBJECTS = {"slack": ("U04ALICE", "U04BOB"), "web": ("oidc|alice-92ab", "oidc|bob-51cd"),
            "cli": ("alice@company.example", "bob@company.example"), "rest": ("api|alice", "api|bob")}


def start(channel: str, subject: str | None = None, **ctx) -> dict:
    return {"capability": CAP, "operation": "start", "input": {"incident_id": "INC-4917"}, "channel_context": ctx,
            "actor": {"channel": channel, "channel_subject": subject or SUBJECTS[channel][0]}}


def act(wf: str, channel: str, subject: str | None = None, action: str = "approve-remediation", binding=None) -> dict:
    return {"capability": CAP, "operation": "act", "workflow_id": wf, "action_id": action, "binding": binding,
            "actor": {"channel": channel, "channel_subject": subject or SUBJECTS[channel][0]}}


def get(wf: str, channel: str) -> dict:
    return {"capability": CAP, "operation": "get", "workflow_id": wf,
            "actor": {"channel": channel, "channel_subject": SUBJECTS[channel][0]}}


def test_h2_started_in_slack_approved_on_the_web_seen_complete_from_the_cli(platform_env):
    async def go():
        async with open_gateway() as gw:
            started = await gw.handle(start("slack", thread_ref="T1/C-INC/1726.1"), wait=True)
            waiting_web = await gw.handle(get(started.workflow_id, "web"))
            approve = waiting_web.action(ActionType.APPROVE)
            approved = await gw.handle(act(started.workflow_id, "web", binding=approve.binding), wait=True)
            done = await gw.handle(get(started.workflow_id, "cli"))
            return gw, started, waiting_web, approved, done, gw.platform.trace(started.workflow_id)

    gw, started, waiting, approved, done, trace = run(go())
    assert started.status is Status.WAITING_APPROVAL and waiting.status is Status.WAITING_APPROVAL
    assert done.status is Status.COMPLETED and done.state.approved_by == "alice" and done.state.verified
    assert {started.workflow_id, waiting.workflow_id, approved.workflow_id, done.workflow_id} == {started.workflow_id}
    assert done.started_by.channel == "slack" and done.actor.channel == "cli"
    rows = gw.store.interactions(started.workflow_id)
    assert [r["channel"] for r in rows] == ["slack", "web", "web", "cli"]
    assert len({r["trace_id"] for r in rows}) == 1                        # one trace across three channels
    names = {s["name"] for s in trace}
    assert {"approval.request", "approval.decide"} <= names and any(n.startswith("invoke_workflow") for n in names)


def test_h4_every_channel_gets_the_same_governance_and_no_channel_can_forge_approval(platform_env):
    async def go():
        out = {}
        async with open_gateway() as gw:
            for channel in ("slack", "rest", "cli", "web"):
                r = await gw.handle(start(channel), wait=True)
                out[channel] = r
            forged = []
            wf = out["rest"].workflow_id
            for extra in ({"approved": True}, {"input": {"incident_id": "INC-4917", "approved": True}},
                          {"actor": {"channel": "rest", "channel_subject": "api|alice", "principal_id": "alice"}}):
                try:
                    await gw.handle({**start("rest"), **extra}, wait=True)
                except CapabilityError as exc:
                    forged.append(exc.code)
            after = await gw.handle(get(wf, "rest"))
            return out, forged, after

    out, forged, after = run(go())
    decisions = {c: (r.status, r.state.policy_decision, r.state.policy_rule, r.state.approval_required_role)
                 for c, r in out.items()}
    assert set(decisions.values()) == {(Status.WAITING_APPROVAL, "REQUIRE_APPROVAL", "P4-prod-high-risk-approval",
                                        "incident-commander")}, decisions
    assert all(r.state.remediation_status is None for r in out.values())  # nothing executed before approval
    assert forged == [ErrorCode.INVALID_REQUEST] * 3
    assert after.status is Status.WAITING_APPROVAL and after.state.approval_status == "PENDING"


def test_h5_bob_cannot_approve_from_any_channel_alice_can_from_any(platform_env):
    async def go():
        async with open_gateway() as gw:
            r = await gw.handle(start("slack"), wait=True)
            bob = {}
            for channel, (_, bob_subject) in SUBJECTS.items():
                seen = await gw.handle({**get(r.workflow_id, channel),
                                        "actor": {"channel": channel, "channel_subject": bob_subject}})
                try:
                    await gw.handle(act(r.workflow_id, channel, bob_subject), wait=True)
                    bob[channel] = ("ALLOWED", seen)
                except CapabilityError as exc:
                    bob[channel] = (exc.code, seen)
            still = await gw.handle(get(r.workflow_id, "web"))
            done = await gw.handle(act(r.workflow_id, "rest"), wait=True)
            return bob, still, done

    bob, still, done = run(go())
    assert {c: code for c, (code, _) in bob.items()} == {c: ErrorCode.FORBIDDEN for c in SUBJECTS}
    assert all(not a.allowed_for_actor for _, seen in bob.values() for a in seen.available_actions)
    assert all(seen.actor.principal_id == "bob" for _, seen in bob.values())
    assert still.status is Status.WAITING_APPROVAL
    assert done.status is Status.COMPLETED and done.state.approved_by == "alice"


def test_h1_the_same_capability_from_cli_rest_and_slack_has_the_same_semantics(platform_env):
    async def go():
        finals = {}
        async with open_gateway() as gw:
            for channel in ("cli", "rest", "slack"):
                r = await gw.handle(start(channel), wait=True)
                finals[channel] = await gw.handle(act(r.workflow_id, channel, binding=r.available_actions[0].binding),
                                                  wait=True)
        return finals

    finals = run(go())
    semantics = {c: (r.status, r.state.recommended_action.tool, r.state.recommended_action.target,
                     r.state.policy_decision, r.state.approval_status, r.state.verified, r.started_by.channel == c)
                 for c, r in finals.items()}
    assert len({v[:-1] for v in semantics.values()}) == 1, semantics
    assert all(v[-1] for v in semantics.values())
    assert next(iter(semantics.values()))[:3] == (Status.COMPLETED, "source_control.rollback_release", "v4.16")


def test_h6_rendering_does_no_model_tool_policy_or_workflow_work(platform_env):
    async def go():
        async with open_gateway() as gw:
            r = await gw.handle(start("slack"), wait=True)
            before = gw.platform.activity(r.workflow_id)
            rendered = [slack.render(r), web.render(r), cli.render(r), api.render(r)] * 25
            after = gw.platform.activity(r.workflow_id)
            return before, after, rendered

    before, after, rendered = run(go())
    assert before == after and before["model_calls"] > 0 and len(rendered) == 100
