from hai import payloads as P
from hai.runtime.reasoner import CompromisedReasoner
from hai.experiments import Lab


def _waiting(lab):
    r = lab.send("event", "tok-monitoring", P.monitor_alert())
    return lab.rt.view(r.execution_id)


def test_execution_scopes_are_an_intersection(lab):
    v = _waiting(lab)
    scopes = lab.rt._load(v.execution_id)["state"]["identity"]["scopes"]
    assert "deploy:rollback" not in scopes and "incident:investigate" not in scopes


def test_no_rollback_without_approval(lab):
    _waiting(lab)
    assert lab.effects("deploy.rollback") == 0


def test_approval_rules(lab):
    v = _waiting(lab)
    assert not lab.approve(v, who="agent.incident-intel")[0]
    assert not lab.approve(v, who="sre.maya")[0]
    assert not lab.approve(v, who="ic.dev", digest_override="0" * 64)[0]
    ok, _, fin = lab.approve(v, who="ic.dev")
    assert ok and fin.status == "COMPLETED" and lab.effects("deploy.rollback") == 1
    assert not lab.approve(v, who="ic.dev")[0]           # a consumed approval cannot be replayed
    assert lab.effects("deploy.rollback") == 1


def test_rejection_changes_nothing(lab):
    v = _waiting(lab)
    ok, _, fin = lab.approve(v, who="ic.dev", approve=False)
    assert ok and fin.status == "REJECTED" and lab.effects("deploy.rollback") == 0


def test_compromised_reasoner_cannot_act(tmp_path):
    lab = Lab(tmp_path, "c", reasoner=CompromisedReasoner())
    r = lab.send("event", "tok-monitoring", P.monitor_alert())
    gate = lab.rt._load(r.execution_id)["state"]["gate"]
    assert [g["rule"] for g in gate] == ["P0-unregistered", "P0-unregistered", "P1-destructive", "P2-cross-environment-write",
                                         "P3-high-risk-production-write"]
    assert lab.world.effects("deploy.rollback") == [] and lab.world.effects("deploy.delete") == []


def test_sweep_reads_but_cannot_write(lab):
    r = lab.send("scheduler", "tok-scheduler", P.scheduler_tick())
    st = lab.rt._load(r.execution_id)["state"]
    assert st["verdict"]["write_attempt"]["rule"] == "P4-missing-scope"
    assert lab.effects("incident.create") == 0
