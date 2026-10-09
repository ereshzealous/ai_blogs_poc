"""The deployment API as a real process: idempotency, the lost response, false success, trace propagation."""
import http.client
import json
import socket

import pytest

from lineage.deploysvc import snapshot

TOKEN = "Bearer dpl_live_7Fq2xW9rTt3LmZ"


def post(port, key=None, to="v4.17.2", timeout=5.0, headers=None):
    h = {"authorization": TOKEN, "content-type": "application/json", **(headers or {})}
    if key:
        h["idempotency-key"] = key
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    c.request("POST", "/v1/deployments/payment-service/rollback", body=json.dumps({"to_version": to}), headers=h)
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}"), dict(r.getheaders())


def revisions(sdir):
    return [r for r in snapshot(sdir)["revisions"] if r["service"] == "payment-service" and r["txn_id"]]


def test_same_key_same_body_is_replayed_not_executed(deploy_api):
    sdir, port = deploy_api()
    s1, b1, _ = post(port, key="act-1")
    s2, b2, h2 = post(port, key="act-1")
    assert (s1, s2) == (200, 200) and b2["replayed"] and h2.get("Idempotent-Replayed") == "true"
    assert b1["transaction_id"] == b2["transaction_id"]
    assert len(revisions(sdir)) == 1


def test_same_key_different_body_is_refused(deploy_api):
    sdir, port = deploy_api()
    post(port, key="act-1")
    assert post(port, key="act-1", to="v4.16.9")[0] == 422


def test_without_a_key_every_request_is_a_new_rollout(deploy_api):
    sdir, port = deploy_api()
    post(port)
    post(port)
    revs = revisions(sdir)
    assert [r["revision"] for r in revs] == [185, 186] and {r["version"] for r in revs} == {"v4.17.2"}


def test_lost_response_after_commit_then_retry_with_the_key_changes_production_once(deploy_api):
    sdir, port = deploy_api(faults=[{"kind": "drop_response_after_commit", "times": 1}], hold=1.5)
    with pytest.raises((socket.timeout, TimeoutError)):
        post(port, key="act-7", timeout=0.5)
    assert len(revisions(sdir)) == 1                   # it happened, and the caller could not know
    s, b, _ = post(port, key="act-7")
    assert s == 200 and b["replayed"] and len(revisions(sdir)) == 1


def test_ack_without_apply_reports_success_and_changes_nothing(deploy_api):
    sdir, port = deploy_api(faults=[{"kind": "ack_without_apply", "times": 1}])
    s, b, _ = post(port, key="act-9")
    assert s == 200 and b["status"] == "ROLLED_BACK"
    assert revisions(sdir) == [] and snapshot(sdir)["deployments"][1]["version"] == "v4.18.0"


def test_reject_before_commit_changes_nothing_and_frees_the_key(deploy_api):
    sdir, port = deploy_api(faults=[{"kind": "reject_before_commit", "times": 1}])
    assert post(port, key="act-3")[0] == 503 and revisions(sdir) == []
    assert post(port, key="act-3")[0] == 200 and len(revisions(sdir)) == 1


def test_unauthenticated_calls_are_refused(deploy_api):
    sdir, port = deploy_api()
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("POST", "/v1/deployments/payment-service/rollback", body="{}", headers={"content-type": "application/json"})
    assert c.getresponse().status == 401


def test_trace_context_crosses_the_process_boundary(deploy_api):
    sdir, port = deploy_api()
    tid = "4bf92f3577b34da6a3ce929d0e0e4736"
    post(port, key="act-t", headers={"traceparent": f"00-{tid}-00f067aa0ba902b7-01"})
    (sdir / "deploy" / "stop").touch()
    import time
    time.sleep(0.8)
    spans = [json.loads(l) for l in (sdir / "telemetry" / "spans-deploy-api.jsonl").read_text().splitlines()]
    srv = [s for s in spans if s["name"].startswith("POST")]
    assert srv and srv[0]["trace_id"] == tid and srv[0]["parent_span_id"] == "00f067aa0ba902b7" and srv[0]["kind"] == "SERVER"
    log = [json.loads(l) for l in (sdir / "logs" / "deploy-api.log").read_text().splitlines()]
    assert any(r.get("trace_id") == tid for r in log)          # log correlation on the server side
    assert "dpl_live" not in (sdir / "logs" / "deploy-api.log").read_text()
