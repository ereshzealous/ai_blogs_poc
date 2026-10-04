"""The decision function and the control plane's change governance, unit by unit."""

import copy

import pytest
import yaml

from acp.common import CONFIG, canon, set_path, sha256, sign, verify_signature
from acp.controlplane import ChangeRejected, ControlPlane
from acp.controlplane.admin import authorize_change, is_restricting
from acp.controlplane.validate import validate
from acp.runtime import pdp

S = yaml.safe_load((CONFIG / "desired-state.yaml").read_text())
ADMINS = yaml.safe_load((CONFIG / "admins.yaml").read_text())
WL = S["agents"]["incident-agent"]["workload"]


def tool(state, agent="incident-agent", name="restart_service", args=None, n=0, wl=WL):
    return pdp.decide_tool(state, agent, wl, name, args or {"environment": "production"}, n)


def test_seed_is_valid():
    assert validate(S) == []


def test_conditions_pick_the_matching_rule():
    s = set_path(
        S,
        "agents.incident-agent.tools.restart_service",
        [{"when": {"environment": "staging"}, "effect": "allow"}, {"when": {"environment": "production"}, "effect": "approval_required"}],
    )
    assert tool(s, args={"environment": "staging"}).effect == "allow"
    d = tool(s, args={"environment": "production"})
    assert (d.effect, d.rule) == ("approval_required", "agents.incident-agent.tools.restart_service[1]")


def test_refund_threshold():
    assert tool(S, "support-agent", "refund_customer", {"amount": 80}).effect == "allow"
    assert tool(S, "support-agent", "refund_customer", {"amount": 420}).effect == "approval_required"


@pytest.mark.parametrize("status,reason", [("suspended", "AGENT_SUSPENDED"), ("paused", "AGENT_PAUSED"), ("disabled", "AGENT_DISABLED")])
def test_lifecycle_status_denies(status, reason):
    assert tool(set_path(S, "agents.incident-agent.status", status)).reason == reason


def test_quarantine_allows_reads_denies_mutations():
    q = set_path(S, "agents.incident-agent.status", "quarantined")
    assert tool(q, name="query_logs").effect == "allow"
    assert tool(q).reason == "AGENT_QUARANTINED"


def test_identity_binding():
    assert tool(S, wl="spiffe://acp.example/ns/other/sa/impostor").reason == "IDENTITY_MISMATCH"
    assert tool(S, agent="ghost-agent").reason == "AGENT_NOT_REGISTERED"


def test_registry_and_grants():
    assert tool(set_path(S, "mcp_servers.deploy-mcp.status", "disabled")).reason == "MCP_SERVER_DISABLED"
    assert tool(S, name="delete_resource").effect == "deny"
    assert tool(S, "finance-agent").reason == "TOOL_NOT_GRANTED"
    assert tool(S, name="drop_database").reason == "TOOL_NOT_REGISTERED"


def test_emergency_freeze_blocks_mutations_only():
    f = set_path(S, "emergency.deny_all_mutations", True)
    assert tool(f).reason == "EMERGENCY_MUTATION_FREEZE"
    assert tool(f, name="query_logs").effect == "allow"


def test_tool_call_quota():
    assert tool(S, name="query_logs", n=9).effect == "allow"
    assert tool(S, name="query_logs", n=10).reason == "TOOL_CALL_BUDGET_EXCEEDED"


def test_models_resolve_from_profile_and_data_class():
    est = lambda m: 0.01
    assert pdp.decide_model(S, "incident-agent", WL, "internal", est, 0)[1] == "fast-model"
    assert pdp.decide_model(S, "support-agent", WL, "confidential", est, 0)[1] == "private-model"
    no_private = set_path(S, "models.catalog.private-model.status", "disabled")
    assert pdp.decide_model(no_private, "support-agent", WL, "confidential", est, 0)[0].reason == "NO_ALLOWED_MODEL_FOR_DATA_CLASS"
    no_fast = set_path(S, "models.catalog.fast-model.status", "disabled")
    assert pdp.decide_model(no_fast, "incident-agent", WL, "internal", est, 0)[1] == "large-model"  # fallback
    assert pdp.decide_model(S, "incident-agent", WL, "internal", lambda m: 99, 0)[0].reason == "COST_BUDGET_EXCEEDED"


def test_change_classification():
    assert is_restricting("agents.x.status", "active", "suspended")
    assert not is_restricting("agents.x.status", "suspended", "active")
    assert is_restricting("agents.x.limits.max_tool_calls", 10, 2)
    assert not is_restricting("agents.x.limits.max_tool_calls", 10, 50)
    assert is_restricting("agents.x.tools.t", "allow", "deny")
    assert not is_restricting("agents.x.tools.t", "deny", "allow")
    assert not is_restricting("models.profiles.standard.default", "fast-model", "large-model")


def test_change_authorization():
    widen = {"agents.incident-agent.tools.delete_resource": "allow"}
    assert not authorize_change(ADMINS, S, widen, "incident-agent", None, False).allowed
    assert not authorize_change(ADMINS, S, widen, "platform.admin", None, False).allowed
    assert not authorize_change(ADMINS, S, widen, "platform.admin", "platform.admin", False).allowed
    assert authorize_change(ADMINS, S, widen, "platform.admin", "sre.lead", False).allowed
    assert authorize_change(ADMINS, S, {"agents.incident-agent.status": "suspended"}, "oncall.ic", None, True).allowed
    assert not authorize_change(ADMINS, S, {"agents.support-agent.status": "suspended"}, "oncall.ic", None, True).allowed


def test_validation_rejects_plaintext_credentials_and_dangling_refs():
    bad = set_path(S, "tools.restart_service.credential", "hunter2")
    assert any("secret://" in p for p in validate(bad))
    bad = set_path(S, "agents.finance-agent.tools.teleport", "allow")
    assert any("unregistered tool" in p for p in validate(bad))
    bad = copy.deepcopy(S)
    del bad["agents"]["finance-agent"]["owner"]
    assert any("missing owner" in p for p in validate(bad))


def test_signatures():
    body = {"version": "v1", "x": 1}
    sig = sign(sha256(canon(body)))
    assert verify_signature(sha256(canon(body)), sig)
    assert not verify_signature(sha256(canon({**body, "x": 2})), sig)


def test_versions_are_immutable_and_logged(tmp_path):
    cp = ControlPlane(tmp_path)
    cp.bootstrap(0)
    v1 = (tmp_path / "controlplane" / "bundles" / "v1.json").read_text()
    cp.publish_change("suspend-incident-agent", 1)
    with pytest.raises(ChangeRejected):
        cp.publish_change("restore-incident-agent", 2)  # widening, no second approver
    assert (tmp_path / "controlplane" / "bundles" / "v1.json").read_text() == v1
    assert cp.versions() == ["v1", "v2"]
    rows = (tmp_path / "controlplane" / "changelog.jsonl").read_text().splitlines()
    assert len(rows) == 3 and '"rejected"' in rows[2]
