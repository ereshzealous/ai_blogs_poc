"""Policy lineage and action-bound approvals."""
from lineage import approval as appr
from lineage import policy

ACT = {"capability": "deployment.rollback", "service": "payment-service", "environment": "production", "to_version": "v4.17.2"}
ATTR = {"agent": "incident-agent-prod", "severity": "SEV-1"}


def test_policy_decision_names_version_digest_rule_and_obligations():
    d41 = policy.evaluate("prod-rollback@41", ACT, ATTR, "exec-1")
    d42 = policy.evaluate("prod-rollback@42", ACT, ATTR, "exec-1")
    assert (d41["policy_version"], d42["policy_version"]) == (41, 42)
    assert d41["policy_digest"] != d42["policy_digest"] and d41["policy_digest"].startswith("sha256:")
    assert d41["decision"] == d42["decision"] == "ALLOW_WITH_APPROVAL"
    assert (d41["obligations"]["quorum"], d42["obligations"]["quorum"]) == (1, 2)
    assert d41["policy_evaluation_id"] != d42["policy_evaluation_id"]


def test_sev3_and_unknown_capabilities_are_denied():
    assert policy.evaluate("prod-rollback@42", ACT, {**ATTR, "severity": "SEV-3"}, "x")["decision"] == "DENY"
    assert policy.evaluate("prod-rollback@42", {**ACT, "capability": "deployment.scale"}, ATTR, "x")["decision"] == "DENY"


def test_an_approval_does_not_transfer_to_another_action(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "logs").mkdir()
    svc = appr.ApprovalService(tmp_path)
    pe = policy.evaluate("prod-rollback@41", ACT, ATTR, "exec-1")
    d1 = appr.action_digest(ACT, "INC-4471", pe["policy_evaluation_id"])
    req = svc.request("exec-1", "INC-4471", ACT, d1, pe["obligations"], pe["policy_evaluation_id"], "incident-agent-prod")
    svc.decide(req["approval_id"], "ic.dev", "APPROVED", "ok")
    dec = svc.decisions(req["approval_id"])[0]
    assert appr.check(dec, d1) == {"signature_valid": True, "digest_match": True}
    other = appr.action_digest({**ACT, "to_version": "v4.16.9"}, "INC-4471", pe["policy_evaluation_id"])
    assert appr.check(dec, other)["digest_match"] is False
    forged = {**dec, "action_digest": other}                    # copy the decision onto the other action
    assert appr.check(forged, other)["signature_valid"] is False


def test_ineligible_people_cannot_decide(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "logs").mkdir()
    svc = appr.ApprovalService(tmp_path)
    pe = policy.evaluate("prod-rollback@42", ACT, ATTR, "exec-2")
    d = appr.action_digest(ACT, "INC-4471", pe["policy_evaluation_id"])
    req = svc.request("exec-2", "INC-4471", ACT, d, pe["obligations"], pe["policy_evaluation_id"], "incident-agent-prod")
    assert svc.decide(req["approval_id"], "eng.lee", "APPROVED", "lgtm") == {"refused": True}
    assert svc.decide(req["approval_id"], "ic.dev", "APPROVED", "ok")["state"] == "PENDING"      # quorum 2 under v42
    assert svc.decide(req["approval_id"], "owner.payments", "APPROVED", "ok")["state"] == "APPROVED"
