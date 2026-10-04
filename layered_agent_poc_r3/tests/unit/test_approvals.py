import pytest

from layered_platform.policy.approvals import Approvals, ApprovalError, digest
from layered_platform.policy.identity import Directory
from layered_platform.storage.db import connect

ARGS = {"service": "checkout-api", "environment": "production", "to_release": "rel-2030"}


@pytest.fixture
def approvals(tmp_path):
    return Approvals(connect(tmp_path / "p.db"), Directory())


def test_request_is_idempotent_per_action(approvals):
    a = approvals.request("wf1", "deploy.rollback", ARGS, "sre.alice", "incident-commander")
    b = approvals.request("wf1", "deploy.rollback", ARGS, "sre.alice", "incident-commander")
    assert a["id"] == b["id"] and a["digest"] == digest("wf1", "deploy.rollback", ARGS)


def test_grant_is_bound_to_the_exact_action(approvals):
    r = approvals.request("wf1", "deploy.rollback", ARGS, "sre.alice", "incident-commander")
    approvals.decide(r["id"], "ic.bob", True)
    approvals.verify_grant(r["id"], "wf1", "deploy.rollback", ARGS, "incident-commander")
    with pytest.raises(ApprovalError):
        approvals.verify_grant(r["id"], "wf1", "deploy.rollback", {**ARGS, "to_release": "rel-2029"}, "incident-commander")
    with pytest.raises(ApprovalError):
        approvals.verify_grant(r["id"], "wf2", "deploy.rollback", ARGS, "incident-commander")


def test_role_and_separation_of_duties(approvals):
    r = approvals.request("wf1", "deploy.rollback", ARGS, "sre.alice", "incident-commander")
    with pytest.raises(ApprovalError):
        approvals.decide(r["id"], "sre.alice", True)          # lacks the role
    r2 = approvals.request("wf2", "deploy.rollback", ARGS, "ic.bob", "incident-commander")
    with pytest.raises(ApprovalError):
        approvals.decide(r2["id"], "ic.bob", True)            # approving your own request


def test_decision_is_final_and_rejection_is_not_a_grant(approvals):
    r = approvals.request("wf1", "deploy.rollback", ARGS, "sre.alice", "incident-commander")
    approvals.decide(r["id"], "ic.bob", False)
    assert approvals.decide(r["id"], "ic.bob", True)["status"] == "REJECTED"
    with pytest.raises(ApprovalError):
        approvals.verify_grant(r["id"], "wf1", "deploy.rollback", ARGS, "incident-commander")
