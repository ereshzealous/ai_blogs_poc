"""Real MCP over stdio: servers, listing with pagination, and argument checks and policy enforced on every call."""

from __future__ import annotations

import json

import pytest

from control_plane.gateway.gateway import Gateway, InvocationContext
from control_plane.paths import CATALOG_DIR

pytestmark = [pytest.mark.mcp, pytest.mark.anyio]
ROLLBACK = {"service": "checkout-api", "environment": "production", "to_version": "v4.16"}


async def test_listing_matches_manifest_and_policy_is_enforced(registry, policy, oncall, tmp_path):
    manifest = CATALOG_DIR / "catalog_100.json"
    expected = {f"{t['server']}__{t['name']}" for t in json.loads(manifest.read_text())["tools"]}
    async with Gateway(manifest, registry, policy, world_db=tmp_path / "w.sqlite") as gw:
        assert set(gw.tools) == expected  # includes servers with more than one page of tools

        read = await gw.call_tool("observability__get_service_health", {"service": "checkout-api", "environment": "production"},
                                  InvocationContext("r1", "run-1", oncall))
        assert read.executed and read.result["status"] == "degraded" and read.policy.decision.value == "ALLOW"

        pending = await gw.call_tool("source_control__rollback_release", ROLLBACK, InvocationContext("r2", "run-1", oncall))
        assert (pending.executed, pending.status) == (False, "approval_pending")

        async def reject(req, decision):
            return False

        rejected = await gw.call_tool("source_control__rollback_release", ROLLBACK, InvocationContext("r3", "run-1", oncall, approver=reject))
        assert (rejected.executed, rejected.status) == (False, "approval_rejected")

        async def approve(req, decision):
            return True

        approved = await gw.call_tool("source_control__rollback_release", ROLLBACK, InvocationContext("r4", "run-1", oncall, approver=approve))
        assert approved.executed and approved.result["to_version"] == "v4.16"
        after = await gw.call_tool("observability__get_service_health", {"service": "checkout-api", "environment": "production"},
                                   InvocationContext("r5", "run-1", oncall))
        assert after.result["status"] == "healthy"

        denied = await gw.call_tool("itsm__close_incident", {"incident_id": "INC-4917", "resolution_code": "fixed"},
                                    InvocationContext("r6", "run-1", oncall))
        assert (denied.executed, denied.status) == (False, "denied")

        observed = await gw.call_tool("itsm__close_incident", {"incident_id": "INC-4917", "resolution_code": "fixed"},
                                      InvocationContext("r7", "run-2", oncall, enforcement="observe"))
        assert observed.executed and observed.policy.decision.value == "DENY"

        unknown = await gw.call_tool("made_up__tool", {}, InvocationContext("r8", "run-1", oncall))
        assert unknown.status == "unknown_tool" and not unknown.executed

        invalid = await gw.call_tool("observability__query_latency", {"service": "checkout-api"}, InvocationContext("r9", "run-1", oncall))
        assert (invalid.status, invalid.is_error, invalid.policy) == ("invalid_arguments", True, None)
        assert "required" in str(invalid.result)

    events = [e["event"] for e in gw.audit.entries]
    assert events.count("policy.decision") == 7 and "approval.decided" in events  # invalid arguments never reach policy
    assert events[-1] == "arguments.invalid"
