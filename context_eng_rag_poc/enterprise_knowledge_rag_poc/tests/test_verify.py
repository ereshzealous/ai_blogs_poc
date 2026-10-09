"""The citation verifier and binding."""

from knowledge_rag.verify import bind, quote_found, verify_answer, verify_claim

E = {"E1": {"eid": "E1", "unit_id": "RB-CHK-007@v4#remediation", "doc_key": "RB-CHK-007@v4", "role": "procedure", "tier": 1,
            "admissible": True, "action": "rollback_release", "approval": "incident-commander",
            "text": "[E1] RB-CHK-007 v4 · Remediation\nRoll the release back through the release pipeline (release-pipeline rollback "
                    "checkout-api --to <previous-version>). Do not restart pods or run kubectl rollout undo: a restart does not fix "
                    "a regressed release."},
     "E2": {"eid": "E2", "unit_id": "INC-4630@v1#timeline", "doc_key": "INC-4630@v1", "role": "history", "tier": None, "admissible": True,
            "action": None, "approval": None, "text": "[E2] INC-4630 v1 · Timeline\n13:31 on-call restarted the checkout-api pods."},
     "E3": {"eid": "E3", "unit_id": "dep:acme/production/checkout-api/4.17.0", "doc_key": "dep:x", "role": "change_fact", "tier": None,
            "admissible": True, "action": None, "approval": None, "text": "[E3] deployment record\nversion: 4.17.0 · previous_version: 4.16.2\nconfig_diff: datasource.maxPoolSize 50 -> 10"}}


def c(text, kind, *cites):
    return {"text": text, "kind": kind, "citations": [{"evidence_id": e, "quote": q} for e, q in cites]}


def test_quote_must_exist():
    assert quote_found("roll the release back", E["E1"]["text"])
    assert not quote_found("roll back immediately", E["E1"]["text"])
    assert not quote_found("roll", E["E1"]["text"])            # too short to be a quote


def test_supported_claim():
    assert verify_claim(c("Roll the release back through the release pipeline.", "procedure", ("E1", "Roll the release back through the release pipeline")), E, "")["supported"]


def test_anchor_missing():
    v = verify_claim(c("4.17.0 changed the pool from 50 to 20.", "cause", ("E3", "datasource.maxPoolSize 50 -> 10")), E, "")
    assert not v["supported"] and any("20" in p for p in v["problems"])


def test_anchor_from_the_question_is_not_required():
    v = verify_claim(c("Since 10:03 the pool shrank from 50 to 10.", "cause", ("E3", "datasource.maxPoolSize 50 -> 10")), E, "p95 since about 10:03?")
    assert v["supported"]


def test_polarity():
    v = verify_claim(c("Restart the pods.", "procedure", ("E1", "Do not restart pods or run kubectl rollout undo")), E, "")
    assert not v["supported"]


def test_history_cannot_decide_procedure():
    v = verify_claim(c("Restarting the pods is the approved fix.", "procedure", ("E2", "on-call restarted the checkout-api pods")), E, "")
    assert not v["supported"] and any("may decide" in p for p in v["problems"])
    assert verify_claim(c("Last time on-call restarted the pods.", "history", ("E2", "on-call restarted the checkout-api pods")), E, "")["supported"]


def test_binding_removes_an_unsupported_action_and_sets_approval_from_metadata():
    ans = {"status": "answer", "summary": "", "recommended_action": {"action": "restart_pods", "target": "", "approval_required": False, "approver": ""},
           "claims": [c("Restart the pods.", "procedure", ("E2", "on-call restarted the checkout-api pods"))], "gaps": [], "conflicts": []}
    final, notes = bind(ans, verify_answer(ans, E, ""), E, [], None)
    assert final["recommended_action"]["action"] == "none" and final["status"] == "abstain"
    ans2 = {**ans, "recommended_action": {"action": "rollback_release", "target": "4.16.2", "approval_required": False, "approver": ""},
            "claims": [c("Roll the release back through the release pipeline.", "procedure", ("E1", "Roll the release back through the release pipeline"))]}
    final2, notes2 = bind(ans2, verify_answer(ans2, E, ""), E, [], None)
    assert final2["recommended_action"]["approval_required"] is True and final2["recommended_action"]["approver"] == "incident-commander"


def test_binding_escalates_on_a_conflict():
    ans = {"status": "answer", "summary": "", "recommended_action": {"action": "rollback_release", "target": "", "approval_required": True, "approver": ""},
           "claims": [c("Roll the release back through the release pipeline.", "procedure", ("E1", "Roll the release back through the release pipeline"))],
           "gaps": [], "conflicts": []}
    conflicts = [{"procedure_key": "k", "documents": {"A@v1": {"action": "rollback_release", "approval": "x", "owner": "o"},
                                                      "B@v1": {"action": "scale_out", "approval": "none", "owner": "o"}}}]
    final, _ = bind(ans, verify_answer(ans, E, ""), E, conflicts, {"owner": "o"})
    assert final["status"] == "escalate" and final["recommended_action"]["action"] == "escalate"
