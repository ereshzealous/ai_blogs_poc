import pytest

from hai import payloads as P
from hai.runtime.service import Crash

MIN = 60.0


def test_lost_response_does_not_double_the_rollback(lab):
    lab.world.faults = {"rollbackDeployment": ["lost_response"]}
    r = lab.send("event", "tok-monitoring", P.monitor_alert())
    lab.approve(lab.rt.view(r.execution_id))
    assert lab.effects("deploy.rollback") == 1


def test_read_timeout_is_retried(lab):
    lab.world.faults = {"getLogs": ["timeout", "timeout"]}
    r = lab.send("event", "tok-monitoring", P.monitor_alert())
    assert lab.rt.view(r.execution_id).assessment is not None


def test_read_timeouts_beyond_budget_fail_the_execution(lab):
    lab.world.faults = {"getServiceHealth": ["timeout"] * 3}
    r = lab.send("event", "tok-monitoring", P.monitor_alert())
    assert lab.rt.view(r.execution_id).status == "FAILED"


def test_crash_resumes_from_checkpoint(lab):
    lab.rt.crash_after = "incident"
    with pytest.raises(Crash):
        lab.send("event", "tok-monitoring", P.monitor_alert())
    lab.reopen()
    (v,) = lab.rt.recover()
    assert v.status == "WAITING_APPROVAL"
    assert lab.effects("incident.create") == 1
    assert [s for _, s in lab.rt.steps_run] == ["recommend", "approve"]


def test_approval_timeout_escalates(lab):
    r = lab.send("event", "tok-monitoring", P.monitor_alert())
    lab.clock.advance(31 * MIN)
    lab.rt.tick()
    assert lab.rt.view(r.execution_id).status == "ESCALATED" and lab.effects("deploy.rollback") == 0


def test_audit_chain_detects_tampering(lab):
    r = lab.send("event", "tok-monitoring", P.monitor_alert())
    assert lab.rt.audit.verify() == (True, None)
    lab.rt.db.execute("UPDATE audit SET record='{}' WHERE n=3")
    ok, row = lab.rt.audit.verify()
    assert not ok and row == 3
