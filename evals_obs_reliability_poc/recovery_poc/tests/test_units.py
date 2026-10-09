"""Unit tests: the deterministic pieces in isolation (no processes, no network unless a world is started)."""
import json
import urllib.request

import pytest

from recovery import gates, scripted
from recovery.classify import certainty, classify_call
from recovery.common import matrix, prereg_check, tools
from recovery.policy import decide, situation
from recovery.telemetry import redact
from recovery.toolclient import Evidence
from recovery.world import World

T = tools()


def ev(**kw):
    base = dict(target="tool:issue_credit", method="POST", path="/credits", attempt_id="a1")
    return Evidence(**{**base, **kw})


# ---- certainty rules (config/recovery-matrix.toml [[certainty]]) -----------------------------------------------------
@pytest.mark.parametrize("e,want", [
    (ev(), ("NOT_EXECUTED", "C1")),
    (ev(transport="CONNECT_REFUSED"), ("NOT_EXECUTED", "C2")),
    (ev(request_sent=True, transport="OK", response_received=True, status=201), ("EXECUTED", "C3")),
    (ev(request_sent=True, transport="OK", response_received=True, status=422), ("NOT_EXECUTED", "C4")),
    (ev(request_sent=True, transport="OK", response_received=True, status=503, not_executed_header=True), ("NOT_EXECUTED", "C5")),
    (ev(request_sent=True, transport="TIMEOUT"), ("UNKNOWN", "C6")),
    (ev(request_sent=True, transport="RESET"), ("UNKNOWN", "C6")),
    (ev(request_sent=True, transport="OK", response_received=True, status=500), ("UNKNOWN", "C11")),
])
def test_certainty_rules(e, want):
    assert certainty(e, T["issue_credit"]["pre_execution"]) == want


def test_timeout_is_not_a_failure_but_the_mutant_says_it_is():
    e = ev(request_sent=True, transport="TIMEOUT")
    assert certainty(e, [])[0] == "UNKNOWN"
    assert certainty(e, [], unknown_as_failed=True)[0] == "NOT_EXECUTED"      # X1


@pytest.mark.parametrize("e,cls", [
    (ev(transport="CONNECT_REFUSED"), "TOOL_UNAVAILABLE"),
    (ev(request_sent=True, transport="TIMEOUT"), "RESPONSE_LOST"),
    (ev(request_sent=True, transport="OK", response_received=True, status=422, body={"error": "CHARGE_DISPUTED"}), "TOOL_REJECTED"),
    (ev(request_sent=True, transport="OK", response_received=True, status=422, body={"error": "AMOUNT_MISMATCH"}), "ARGUMENT_VALIDATION"),
    (ev(request_sent=True, transport="OK", response_received=True, status=403), "AUTHORIZATION_DENIED"),
    (ev(request_sent=True, transport="OK", response_received=True, status=500), "TOOL_SERVER_ERROR"),
])
def test_classes_are_distinct(e, cls):
    assert classify_call("r", "credit", "tool", e, T["issue_credit"]).failure_class == cls


def test_success_is_not_a_failure():
    e = ev(request_sent=True, transport="OK", response_received=True, status=201)
    assert classify_call("r", "credit", "tool", e, T["issue_credit"]) is None


# ---- the recovery matrix -----------------------------------------------------------------------------------------------
C0 = {"retries": 0, "repairs": 0, "reconciles": 0}


def act(cls, cert, tool, **kw):
    return decide(situation(cls, cert, T.get(tool), {**C0, **kw.pop("c", {})}, **kw)).action


def test_one_timeout_four_correct_answers():
    """The same RESPONSE_LOST / UNKNOWN, four tool contracts, four different correct actions."""
    assert act("RESPONSE_LOST", "UNKNOWN", "lookup_charges") == "RETRY"          # a read: repeat it
    assert act("RESPONSE_LOST", "UNKNOWN", "issue_credit") == "RECONCILE"        # queryable write: ask first
    assert act("RECONCILE_FAILED", "UNKNOWN", "issue_credit", key_fresh=True, c={"reconciles": 2}) == "RETRY"   # keyed, fresh
    assert act("RESPONSE_LOST", "UNKNOWN", "send_notification") == "ESCALATE"    # no key, no query: a person decides


def test_terminal_refusals_are_never_retried():
    assert act("AUTHORIZATION_DENIED", "NOT_EXECUTED", "issue_credit") == "ABORT"
    assert act("TOOL_REJECTED", "NOT_EXECUTED", "issue_credit") == "ESCALATE"
    assert act("ARGUMENT_VALIDATION", "NOT_EXECUTED", "issue_credit") == "REPAIR"
    assert act("ARGUMENT_VALIDATION", "NOT_EXECUTED", "issue_credit", c={"repairs": 1}) == "ESCALATE"


def test_confirmed_effects_are_never_replayed():
    assert act("PROCESS_INTERRUPTED", "EXECUTED", "issue_credit") == "CONTINUE"
    assert act("RECONCILED", "EXECUTED", "issue_credit") == "CONTINUE"
    assert act("PROCESS_INTERRUPTED", "NOT_EXECUTED", "issue_credit") == "RESUME"


def test_expired_key_does_not_license_a_retry():
    assert act("RECONCILE_FAILED", "UNKNOWN", "issue_credit", key_fresh=False, c={"reconciles": 2}) == "ESCALATE"


def test_duplicates_compensate_only_when_undoable():
    assert act("DUPLICATE_EFFECT", "EXECUTED", "create_ticket") == "COMPENSATE"
    assert act("DUPLICATE_EFFECT", "EXECUTED", "issue_credit") == "ESCALATE"


def test_every_oracle_action_exists_in_the_matrix(sc):
    actions = {r["action"] for r in matrix()["rules"]}
    assert {d[2] for s in sc.values() for d in s["decisions"]} <= actions


def test_matrix_ends_in_a_catch_all():
    last = matrix()["rules"][-1]
    assert last["action"] == "ESCALATE" and set(last) <= {"id", "action", "status", "why"}


def test_preregistration_is_frozen():
    assert prereg_check() == []


# ---- gates -------------------------------------------------------------------------------------------------------------
CH = [{"id": "a", "amount": 42.5, "customer": "C", "description": "x", "date": "2026-10-01T09:14:02Z"},
      {"id": "b", "amount": 42.5, "customer": "C", "description": "x", "date": "2026-10-01T09:14:09Z", "duplicate_of": "a"}]


def prop(tool="issue_credit", **a):
    return {"tool": tool, "arguments": a or {"charge_id": "b", "amount": 42.5}, "requires_approval": False, "citations": [], "reply": ""}


def test_gates():
    gates.validate(prop(), CH)
    with pytest.raises(gates.GateError) as e:
        gates.validate(prop("delete_customer_account"), CH)
    assert e.value.cls == "TOOL_SELECTION_INVALID"
    for bad in ({"charge_id": "b", "amount": 425.0}, {"charge_id": "a", "amount": 42.5}, {"charge_id": "zz", "amount": 1.0}):
        with pytest.raises(gates.GateError) as e:
            gates.validate(prop(**bad), CH)
        assert e.value.cls == "ARGUMENT_VALIDATION"
    with pytest.raises(gates.GateError) as e:
        gates.parse("{not json")
    assert e.value.cls == "MODEL_OUTPUT_INVALID"


def test_policy_denies_over_limit_and_is_deterministic():
    p = gates.Policy()
    ch = [{"id": "x", "amount": 480.0, "customer": "C"}]
    a = p.authorize("r", 1, "issue_credit", {"charge_id": "x", "amount": 480.0}, "C", ch)
    b = p.authorize("r", 1, "issue_credit", {"charge_id": "x", "amount": 480.0}, "C", ch)
    assert a == b and a["effect"] == "DENY" and a["rule"] == "P1"


# ---- scripted models, telemetry ---------------------------------------------------------------------------------------
def test_scripted_v2_regression_targets_the_original():
    charges = [{k: v for k, v in c.items() if k != "duplicate_of"} for c in CH]
    assert scripted.decide("scripted-v1", "charged twice", charges, [])["arguments"]["charge_id"] == "b"
    assert scripted.decide("scripted-v2", "charged twice", charges, [])["arguments"]["charge_id"] == "a"


def test_redaction():
    out = redact({"m": "card 4111 1111 1111 1111 mail dana.reyes@example.test key sk_live_CANARY_7f3a9e2b41", "id": "op-1234abcd"})
    assert "4111" not in out["m"] and "@" not in out["m"] and "sk_live" not in out["m"] and out["id"] == "op-1234abcd"


# ---- the simulated providers --------------------------------------------------------------------------------------------
def post(port, path, body, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read()), dict(r.headers)


def test_provider_idempotency_window_and_replay():
    """Test 4: the same logical operation twice changes external state once, inside the key's window only."""
    w = World([])
    port = w.start()
    try:
        b = {"charge_id": "ch_1042_b", "amount": 42.5}
        h = {"Idempotency-Key": "op-1", "X-Operation-Id": "op-1"}
        s1, r1, _ = post(port, "/credits", b, h)
        s2, r2, h2 = post(port, "/credits", b, h)
        assert (s1, s2) == (201, 201) and r1 == r2 and h2.get("Idempotent-Replayed") == "true"
        assert len(w.ledger()["credits"]) == 1
        post(port, "/admin/clock", {"advance_s": 90000})
        post(port, "/credits", b, h)                                    # the window expired: a new credit
        assert len(w.ledger()["credits"]) == 2
    finally:
        w.stop()


def test_ticket_api_ignores_idempotency_keys():
    w = World([])
    port = w.start()
    try:
        b = {"case_id": "CASE-1042", "reference": "op-9", "summary": "s"}
        post(port, "/tickets", b, {"Idempotency-Key": "k"})
        post(port, "/tickets", b, {"Idempotency-Key": "k"})
        assert len(w.ledger()["tickets"]) == 2
    finally:
        w.stop()
