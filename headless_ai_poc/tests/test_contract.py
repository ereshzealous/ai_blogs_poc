"""The contract rejects what a channel must not say, and says what a channel needs to render."""

from __future__ import annotations

import pytest

from headless_ai_platform.contracts import CapabilityError, ErrorCode
from headless_ai_platform.gateway import parse

BASE = {"capability": "incident.remediation", "operation": "start",
        "actor": {"channel": "slack", "channel_subject": "U04ALICE"}, "input": {"incident_id": "INC-4917"}}


def test_a_valid_start_request_parses():
    req = parse(BASE)
    assert req.schema_version == "1.0" and req.workflow_id is None and req.channel_context.thread_ref is None


@pytest.mark.parametrize("smuggled", [
    {"approved": True},
    {"actor": {"channel": "slack", "channel_subject": "U04ALICE", "principal_id": "alice"}},
    {"actor": {"channel": "slack", "channel_subject": "U04ALICE", "roles": ["incident-commander"]}},
    {"approval": {"status": "APPROVED"}},
    {"channel_context": {"thread_ref": "T/C/1", "approved": True}},
])
def test_a_channel_cannot_assert_identity_or_approval(smuggled):
    with pytest.raises(CapabilityError) as exc:
        parse({**BASE, **smuggled})
    assert exc.value.code is ErrorCode.INVALID_REQUEST


def test_an_unserved_major_version_is_refused_before_shape_checks():
    with pytest.raises(CapabilityError) as exc:
        parse({**BASE, "schema_version": "2.0", "brand_new_field": 1})
    assert exc.value.code is ErrorCode.UNSUPPORTED_VERSION
    assert parse({**BASE, "schema_version": "1.3"}).schema_version == "1.3"  # minor versions are additive


@pytest.mark.parametrize("bad", [
    {"workflow_id": "wf-1"},                                          # start takes no workflow id
    {"operation": "act", "workflow_id": "wf-1"},                      # act needs an action
    {"operation": "get"},                                             # get needs a workflow
    {"capability": "Incident Remediation"},                           # capability names are dotted identifiers
    {"actor": {"channel": "Slack!", "channel_subject": "U04ALICE"}},
])
def test_malformed_requests_are_invalid(bad):
    with pytest.raises(CapabilityError) as exc:
        parse({**BASE, **bad})
    assert exc.value.code is ErrorCode.INVALID_REQUEST


def test_the_json_schema_names_the_contract_fields():
    from headless_ai_platform.contracts import CapabilityRequest, CapabilityResponse

    req = CapabilityRequest.model_json_schema()["properties"]
    resp = CapabilityResponse.model_json_schema()["properties"]
    assert {"schema_version", "capability", "operation", "actor", "input", "workflow_id", "channel_context"} <= set(req)
    assert {"schema_version", "workflow_id", "status", "state", "available_actions", "actor", "trace_id"} <= set(resp)
    assert "html" not in str(resp).lower() and "blocks" not in resp  # no presentation in the contract
