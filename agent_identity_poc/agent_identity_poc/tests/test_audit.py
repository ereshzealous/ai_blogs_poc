"""The platform record carries the chain; the chain of records is tamper-evident."""
import copy

from aid.agents import IncidentIntel


def _rollback(p):
    ex = p.start("web", "cred-web", "agent.incident-intel", sso="sso-maya")
    d = p.call(ex, IncidentIntel().remediate())
    p.approve(d.approval_id, "ic.dev")
    p.call(ex, IncidentIntel().remediate(), approval_id=d.approval_id)
    return p.audit.calls("rollbackDeployment")[-1]


def test_record_carries_the_whole_chain(chain):
    rec = _rollback(chain)
    assert rec["invoker"] == "svc.web-portal" and rec["on_behalf_of"] == "sre.maya"
    assert rec["agent"] == "agent.incident-intel@1.3.0" and rec["workload"].endswith("/agent-runtime")
    assert rec["tool_principal"].endswith(":incident-remediator") and rec["authorized_by"] == "ic.dev"
    assert set(rec["revocation"]) == {"delegation", "invoker_credential", "agent", "workload", "tool_identity"}


def test_shared_account_record_names_no_agent(shared):
    rec = _rollback(shared)
    assert "agent" not in rec and rec["tool_principal"].endswith(":ai-automation")


def test_tamper_detected(chain):
    _rollback(chain)
    assert chain.audit.verify() == (True, None)
    rows = copy.deepcopy(chain.audit.rows)
    rows[2]["record"]["invoker"] = "someone-else"
    assert chain.audit.verify(rows) == (False, 3)


def test_run_is_deterministic(tmp_path):
    from aid.experiments import i1, i3
    assert i1()["modes"]["chain"]["platform_record"] == i1()["modes"]["chain"]["platform_record"]
    assert i3()["chain"]["delegation"] == i3()["chain"]["delegation"]
