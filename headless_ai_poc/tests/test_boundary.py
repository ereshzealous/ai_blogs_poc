from hai import payloads as P
from hai.contracts import Accepted, ExecutionView, Rejected


def test_event_invokes_without_a_human(lab):
    r = lab.send("event", "tok-monitoring", P.monitor_alert())
    assert isinstance(r, Accepted)
    v = lab.rt.view(r.execution_id)
    assert v.status == "WAITING_APPROVAL" and v.incident_id and v.assessment.leading == "H1"


def test_credential_is_bound_to_its_channel(lab):
    r = lab.send("chat", "tok-monitoring", P.chat_message()[1])
    assert isinstance(r, Rejected) and r.stage == "authenticate"


def test_invoker_comes_from_the_credential_not_the_payload(lab):
    p = P.monitor_alert()
    p["invoker"] = "ic.dev"                                    # a payload cannot name its own invoker
    r = lab.send("event", "tok-monitoring", p)
    v = lab.rt.view(r.execution_id)
    assert v.invoker == "svc.monitoring-webhook"


def test_duplicate_delivery_returns_the_same_execution(lab):
    a = lab.send("event", "tok-monitoring", P.monitor_alert())
    b = lab.send("event", "tok-monitoring", P.monitor_alert())
    assert b.duplicate and a.execution_id == b.execution_id


def test_chat_joins_the_running_investigation(lab):
    a = lab.send("event", "tok-monitoring", P.monitor_alert())
    tok, m = P.chat_message()
    v = lab.send("chat", tok, m)
    assert isinstance(v, ExecutionView) and v.joined and v.execution_id == a.execution_id


def test_poison_goes_to_dead_letters(lab):
    r = lab.send("event", "tok-monitoring", {"id": "x", "tags": ["env:production"], "metric": "m", "value": 1, "monitor_id": "m"})
    assert isinstance(r, Rejected) and r.stage == "dead_letter"
    assert lab.rt.db.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 0


def test_viewer_cannot_invoke(lab):
    tok, m = P.chat_message(user_token="tok-slack-lee")
    r = lab.send("chat", tok, m)
    assert isinstance(r, Rejected) and r.stage == "authorize_invocation"
