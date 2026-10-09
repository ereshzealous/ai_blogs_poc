from hai import payloads as P
from hai.experiments import Lab

INVESTIGATION_HEADS = ["event", "chat", "web", "api", "workflow"]


def _decision(tmp_path, head):
    """Start the investigation from one head, in its own fresh enterprise, and return what the gate decided."""
    lab = Lab(tmp_path, f"gov-{head}")
    cred, fn = P.HEADS[head]
    r = lab.send(head, cred, fn())
    v = lab.rt.view(r.execution_id)
    gate = [g for g in lab.rt._load(v.execution_id)["state"]["gate"] if g["capability"] == "rollbackDeployment"]
    return v, gate, lab.effects("deploy.rollback")


def test_policy_does_not_depend_on_the_invoking_head(tmp_path):
    seen = {}
    for head in INVESTIGATION_HEADS:
        v, gate, rollbacks = _decision(tmp_path, head)
        assert v.status == "WAITING_APPROVAL" and rollbacks == 0, head          # every head stops at the same boundary
        (g,) = gate
        # the approval digest is bound to each execution's id, so it differs; the decision and the exact call must not
        seen[head] = (g["status"], g["rule"], v.approval["required_role"], g["arguments"]["service"], g["arguments"]["environment"],
                      g["arguments"]["from_version"], g["arguments"]["to_version"])
    assert len(set(seen.values())) == 1, seen
    status, rule, role, _, _, frm, to = seen["event"]
    assert (status, rule, role, frm, to) == ("approval_required", "P3-high-risk-production-write", "incident-commander", "v4.18.0", "v4.17.2")


def test_the_deploy_system_refuses_a_rollback_from_a_version_that_is_not_running(lab):
    import pytest
    with pytest.raises(ValueError, match="precondition failed"):
        lab.world.rollback("payment-service", "production", from_version="v4.18.1", to_version="v4.17.2")
    assert lab.effects("deploy.rollback") == 0
