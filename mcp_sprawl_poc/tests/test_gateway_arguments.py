"""The gateway checks arguments before policy, and policy, approval and the MCP call all see one canonical form."""

from __future__ import annotations

import json

import pytest

from control_plane.gateway.arguments import ArgumentChecker, canonical_json
from control_plane.gateway.gateway import Gateway, InvocationContext
from control_plane.paths import CATALOG_DIR

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["incident_id", "comment"],
          "properties": {"incident_id": {"type": "string", "pattern": "^INC-[0-9]{4,6}$"}, "comment": {"type": "string", "minLength": 1},
                         "visibility": {"type": "string", "enum": ["work_note", "customer_visible"], "default": "work_note"}}}
ROLLBACK = {"service": "checkout-api", "environment": "production", "to_version": "v4.16"}
# H162 on held-out set 2: the model sent a visibility value the schema does not allow
H162_ARGS = {"incident_id": "INC-4917", "comment": "Mitigated, monitoring.", "visibility": "public"}


def test_valid_arguments_come_back_as_a_sorted_copy_with_defaults_filled():
    args = {"comment": "Mitigated.", "incident_id": "INC-4917"}
    checked = ArgumentChecker().check("itsm__add_incident_comment", SCHEMA, args)
    assert checked.valid and checked.problems == ()
    assert checked.arguments == {"comment": "Mitigated.", "incident_id": "INC-4917", "visibility": "work_note"}
    assert list(checked.arguments) == ["comment", "incident_id", "visibility"]
    assert checked.arguments is not args and "visibility" not in args


def test_invalid_arguments_are_rejected_not_repaired():
    checked = ArgumentChecker().check("itsm__add_incident_comment", SCHEMA, H162_ARGS)
    assert not checked.valid
    assert checked.problems == ("'public' is not one of ['work_note', 'customer_visible']",)
    assert checked.message == "Invalid arguments: 'public' is not one of ['work_note', 'customer_visible']"
    assert checked.arguments == H162_ARGS


def test_at_most_three_problems_are_reported():
    checked = ArgumentChecker().check("t", SCHEMA, {"incident_id": 7, "comment": "", "visibility": "x", "extra": 1})
    assert len(checked.problems) == 3


def test_arguments_that_are_not_an_object_are_rejected():
    assert ArgumentChecker().check("t", SCHEMA, ["INC-4917"]).problems == ("arguments must be a JSON object",)  # type: ignore[arg-type]


def test_key_order_does_not_change_the_canonical_form():
    assert canonical_json({"b": 1, "a": {"d": 2, "c": 3}}) == canonical_json({"a": {"c": 3, "d": 2}, "b": 1}) == '{"a":{"c":3,"d":2},"b":1}'


@pytest.mark.mcp
@pytest.mark.anyio
async def test_invalid_arguments_stop_before_policy_and_approval(registry, policy, oncall, tmp_path):
    asked = []

    async def approver(req, decision):
        asked.append(req)
        return True

    async with Gateway(CATALOG_DIR / "catalog_50.json", registry, policy, world_db=tmp_path / "w.sqlite") as gw:
        h162 = await gw.call_tool("itsm__add_incident_comment", dict(H162_ARGS), InvocationContext("r1", "run-1", oncall))
        assert (h162.executed, h162.status, h162.is_error, h162.policy) == (False, "invalid_arguments", True, None)
        assert h162.result == "Invalid arguments: 'public' is not one of ['work_note', 'customer_visible']"

        no_version = {k: v for k, v in ROLLBACK.items() if k != "to_version"}
        rollback = await gw.call_tool("source_control__rollback_release", no_version,
                                      InvocationContext("r2", "run-1", oncall, approver=approver))
        assert (rollback.executed, rollback.status) == (False, "invalid_arguments") and "to_version" in rollback.result
        assert asked == [] and gw.approvals.pending() == []

    entries = [e for e in gw.audit.entries if e.get("request_id") in ("r1", "r2")]
    assert [e["event"] for e in entries] == ["arguments.invalid", "arguments.invalid"]
    assert entries[0]["problems"] == ["'public' is not one of ['work_note', 'customer_visible']"]


@pytest.mark.mcp
@pytest.mark.anyio
async def test_observe_mode_records_invalid_arguments_and_still_forwards_them(registry, policy, oncall, tmp_path):
    async with Gateway(CATALOG_DIR / "catalog_50.json", registry, policy, world_db=tmp_path / "w.sqlite") as gw:
        out = await gw.call_tool("itsm__add_incident_comment", dict(H162_ARGS), InvocationContext("r1", "run-1", oncall, enforcement="observe"))
    assert (out.executed, out.is_error, out.policy.decision.value) == (True, True, "ALLOW")  # the server rejects it
    assert [e["event"] for e in gw.audit.entries] == ["arguments.invalid", "policy.decision", "invocation.executed"]


@pytest.mark.mcp
@pytest.mark.anyio
async def test_the_approved_arguments_are_exactly_the_ones_that_run(registry, policy, oncall, tmp_path):
    caller_args = {"to_version": "v4.16", "service": "checkout-api", "environment": "production"}
    seen = []

    async def approver(req, decision):
        seen.append(req)
        caller_args["to_version"] = "v4.15"  # the caller changes its dict while the approval is open
        return True

    async with Gateway(CATALOG_DIR / "catalog_50.json", registry, policy, world_db=tmp_path / "w.sqlite") as gw:
        out = await gw.call_tool("source_control__rollback_release", caller_args, InvocationContext("r1", "run-1", oncall, approver=approver))
    assert out.executed and out.result["to_version"] == "v4.16"
    assert seen[0].arguments_json == canonical_json(ROLLBACK) == json.dumps(out.arguments, separators=(",", ":"))
    assert out.policy.invocation_digest == seen[0].digest
