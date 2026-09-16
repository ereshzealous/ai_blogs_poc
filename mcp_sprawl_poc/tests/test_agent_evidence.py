"""Evidence guard: diagnosis, recovery verification, call gates and reports, driven by real mock-backend responses."""

from __future__ import annotations

import yaml

from agent.evidence import (
    EvidenceLedger,
    NotExecuted,
    describe,
    diagnose,
    gate_call,
    missing_requirements,
    next_requirement,
    parse_intent,
    render_report,
    verify_recovery,
)
from control_plane.paths import REPO_ROOT
from servers.common.handlers import Ctx, resolve
from servers.core_catalog import CORE_TOOLS

PROD = {"service": "checkout-api", "environment": "production"}
STAGING = {"service": "checkout-api", "environment": "staging"}
CONTEXT = {"default_service": "checkout-api", "default_environment": "production", "incident_id": "INC-4917"}
SCENARIOS = {s["id"]: s for s in yaml.safe_load((REPO_ROOT / "benchmark" / "golden" / "agent_scenarios.yaml").read_text())["scenarios"]}


def call(world, run_id, tool_id, args):
    spec = CORE_TOOLS[tool_id]
    return resolve(spec.handler)(Ctx(world, run_id, spec.server, spec), args)


class Session:
    """Calls real mock backends in one isolated world and records every result in a ledger."""

    def __init__(self, world, run_id="r"):
        self.world, self.run_id, self.ledger, self.step = world, run_id, EvidenceLedger(), 0

    def run(self, tool_id, args, *, is_error=False):
        result = call(self.world, self.run_id, tool_id, args)
        receipt = self.ledger.record(self.step, tool_id, args, result, is_error)
        self.step += 1
        return receipt

    def deployments(self):
        return self.run("source_control.search_deployments", {**PROD, "limit": 5})

    def diff(self, sha="a91f3c2"):
        return self.run("source_control.get_diff", {"sha": sha})

    def pool(self, scope=PROD):
        return self.run("database.get_connection_pool_stats", dict(scope))

    def rollback(self):
        return self.run("source_control.rollback_release", {**PROD, "to_version": "v4.16"})

    def health(self, scope=PROD, **kw):
        return self.run("observability.get_service_health", dict(scope), **kw)


# ---------------------------------------------------------------------------------------------- intent
def test_scenario_requests_are_read_as_intended():
    s1, s2, s3, s4 = (parse_intent(SCENARIOS[i]["prompt"], **CONTEXT) for i in ("S1", "S2", "S3", "S4"))
    assert (s1.wants_cause, s1.wants_action, s1.wants_incident_update, s1.read_only) == (True, False, True, False)
    assert (s2.wants_cause, s2.wants_action, s2.read_only) == (True, False, True)
    assert (s3.wants_action, s3.wants_verification, s3.read_only) == (True, True, False)
    assert (s4.wants_action, s4.wants_verification, s4.wants_incident_update) == (True, True, False)
    assert (s1.service, s1.environment, s1.incident_id) == ("checkout-api", "production", "INC-4917")


def test_named_service_and_environment_override_the_defaults():
    intent = parse_intent("Check payment-gateway latency in staging.", **CONTEXT)
    assert (intent.service, intent.environment) == ("payment-gateway", "staging")


# ---------------------------------------------------------------------------------------------- ledger
def test_failed_calls_are_not_evidence(world):
    s = Session(world)
    assert s.health(is_error=True) is None
    assert s.deployments().eid == "E1" and len(s.ledger.receipts) == 1


def test_receipts_keep_the_full_structured_result(world):
    receipt = Session(world).pool()
    assert receipt.result["max_connections"] == 10 and receipt.result["waiting"] > 100


# ---------------------------------------------------------------------------------------------- diagnosis
def test_diagnosis_joins_deployment_diff_and_saturated_pool(world):
    s = Session(world)
    s.deployments(), s.diff(), s.pool()
    d = diagnose(s.ledger, "checkout-api", "production")
    assert d is not None
    assert (d.version, d.previous_version, d.commit, d.old_max, d.new_max) == ("v4.17", "v4.16", "a91f3c2", 50, 10)
    assert d.in_use == 10 and d.waiting > 100
    assert d.evidence == ["E1", "E2", "E3"]
    assert "v4.17" in d.sentence() and "50" in d.sentence() and "10" in d.sentence()


def test_no_diagnosis_without_the_commit_diff(world):
    s = Session(world)
    s.deployments(), s.pool()
    assert diagnose(s.ledger, "checkout-api", "production") is None


def test_no_diagnosis_from_an_unrelated_commit(world):
    s = Session(world)
    s.deployments(), s.diff("1b7f0e4"), s.pool()
    assert diagnose(s.ledger, "checkout-api", "production") is None


def test_no_diagnosis_from_another_environment(world):
    s = Session(world)
    s.deployments(), s.diff(), s.pool(STAGING)
    assert diagnose(s.ledger, "checkout-api", "production") is None


def test_a_saturated_pool_in_another_environment_is_not_evidence(world):
    s = Session(world)
    s.run("source_control.search_deployments", {**STAGING, "limit": 5}), s.diff(), s.pool(PROD)
    assert diagnose(s.ledger, "checkout-api", "staging") is None


def test_no_diagnosis_when_the_pool_is_not_saturated(world):
    s = Session(world)
    s.run("source_control.search_deployments", {**STAGING, "limit": 5}), s.diff(), s.pool(STAGING)
    assert diagnose(s.ledger, "checkout-api", "staging") is None


def test_no_diagnosis_when_the_observed_limit_differs_from_the_diff(world):
    s = Session(world)
    s.deployments(), s.diff()
    pool = call(world, "r", "database.get_connection_pool_stats", PROD)
    s.ledger.record(2, "database.get_connection_pool_stats", PROD, {**pool, "max_connections": 20, "in_use": 20}, False)
    assert diagnose(s.ledger, "checkout-api", "production") is None


def test_no_diagnosis_from_a_failed_pool_read(world):
    s = Session(world)
    s.deployments(), s.diff()
    s.run("database.get_connection_pool_stats", PROD, is_error=True)
    assert diagnose(s.ledger, "checkout-api", "production") is None


# ---------------------------------------------------------------------------------------------- recovery
def test_recovery_is_verified_by_a_later_in_slo_reading(world):
    s = Session(world)
    s.rollback()
    s.health()
    v = verify_recovery(s.ledger, "checkout-api", "production")
    assert v is not None and v.p95_ms <= v.slo_ms == 400 and v.evidence == ["E1", "E2"]


def test_latency_p95_after_the_rollback_also_verifies(world):
    s = Session(world)
    s.rollback()
    s.run("observability.query_latency", {**PROD, "percentile": "p95", "time_range": "5m"})
    assert verify_recovery(s.ledger, "checkout-api", "production") is not None


def test_a_reading_taken_before_the_rollback_is_stale(world):
    s = Session(world)
    s.health()
    s.rollback()
    assert verify_recovery(s.ledger, "checkout-api", "production") is None


def test_p50_is_not_a_recovery_measurement(world):
    s = Session(world)
    s.rollback()
    s.run("observability.query_latency", {**PROD, "percentile": "p50", "time_range": "5m"})
    assert verify_recovery(s.ledger, "checkout-api", "production") is None


def test_a_wrong_scope_reading_does_not_verify(world):
    s = Session(world)
    s.rollback()
    s.health(STAGING)
    assert verify_recovery(s.ledger, "checkout-api", "production") is None


def test_a_failed_reading_does_not_verify(world):
    s = Session(world)
    s.rollback()
    s.health(is_error=True)
    assert verify_recovery(s.ledger, "checkout-api", "production") is None


def test_a_reading_that_still_breaches_the_slo_does_not_verify(world):
    s = Session(world)
    s.run("kubernetes.restart_deployment", dict(PROD))
    s.health()
    assert verify_recovery(s.ledger, "checkout-api", "production") is None


def test_a_later_remediation_invalidates_earlier_verification(world):
    s = Session(world)
    s.rollback(), s.health()
    assert verify_recovery(s.ledger, "checkout-api", "production") is not None
    s.run("kubernetes.restart_deployment", dict(PROD))
    assert verify_recovery(s.ledger, "checkout-api", "production") is None
    s.health()
    assert verify_recovery(s.ledger, "checkout-api", "production") is not None


def test_no_verification_without_a_remediation(world):
    s = Session(world)
    s.health()
    assert verify_recovery(s.ledger, "checkout-api", "production") is None


# ---------------------------------------------------------------------------------------------- call gates
def test_closing_the_incident_needs_verified_recovery(world, registry):
    intent = parse_intent(SCENARIOS["S1"]["prompt"], **CONTEXT)
    s = Session(world)
    args = {"incident_id": "INC-4917", "resolution_code": "rolled_back"}
    gate = gate_call(intent, "itsm.close_incident", args, registry.get("itsm.close_incident"), s.ledger)
    assert not gate.allowed and "verif" in gate.message.lower()
    s.rollback(), s.health()
    assert gate_call(intent, "itsm.close_incident", args, registry.get("itsm.close_incident"), s.ledger).allowed


def test_incident_update_fields_are_rendered_from_receipts(world, registry):
    intent = parse_intent(SCENARIOS["S1"]["prompt"], **CONTEXT)
    s = Session(world)
    s.deployments(), s.diff(), s.pool()
    prose = {"incident_id": "INC-4917", "status": "resolved", "severity": "high",
             "root_cause": "an inefficient database query", "resolution_notes": "Rolled back; latency is back to baseline."}
    gate = gate_call(intent, "itsm.update_incident", prose, registry.get("itsm.update_incident"), s.ledger)
    out = gate.arguments
    assert gate.allowed and out["incident_id"] == "INC-4917"
    assert out["status"] == "identified" and "severity" not in out
    assert "v4.17" in out["root_cause"] and "inefficient" not in out["root_cause"]
    assert "resolution_notes" not in out or "back to baseline" not in out["resolution_notes"]


def test_incident_update_without_evidence_stays_investigating(world, registry):
    intent = parse_intent(SCENARIOS["S1"]["prompt"], **CONTEXT)
    gate = gate_call(intent, "itsm.update_incident", {"incident_id": "INC-4917", "status": "resolved", "root_cause": "a slow query"},
                     registry.get("itsm.update_incident"), EvidenceLedger())
    assert gate.allowed and gate.arguments["status"] == "investigating" and "root_cause" not in gate.arguments


def test_verified_recovery_allows_resolved_status(world, registry):
    intent = parse_intent(SCENARIOS["S4"]["prompt"], **CONTEXT)
    s = Session(world)
    s.rollback(), s.health()
    gate = gate_call(intent, "itsm.update_incident", {"incident_id": "INC-4917", "status": "resolved"},
                     registry.get("itsm.update_incident"), s.ledger)
    assert gate.arguments["status"] == "resolved" and "400" in gate.arguments["resolution_notes"]


def test_a_rollback_needs_the_release_history_first(world, registry):
    intent = parse_intent(SCENARIOS["S4"]["prompt"], **CONTEXT)
    args = {**PROD, "to_version": "v4.16"}
    gate = gate_call(intent, "source_control.rollback_release", args, registry.get("source_control.rollback_release"), EvidenceLedger())
    assert not gate.allowed and "release history" in gate.message


def test_a_rollback_to_a_version_the_evidence_does_not_support_is_blocked(world, registry):
    intent = parse_intent(SCENARIOS["S4"]["prompt"], **CONTEXT)
    s = Session(world)
    s.deployments()
    record = registry.get("source_control.rollback_release")
    gate = gate_call(intent, "source_control.rollback_release", {**PROD, "to_version": "v4.15"}, record, s.ledger)
    assert not gate.allowed and "v4.16" in gate.message and "E1" in gate.message
    assert gate_call(intent, "source_control.rollback_release", {**PROD, "to_version": "v4.16"}, record, s.ledger).allowed


def test_the_blocked_rollback_cites_the_deployment_receipt(world, registry):
    intent = parse_intent(SCENARIOS["S3"]["prompt"], **CONTEXT)
    s = Session(world)
    s.diff(), s.deployments(), s.pool()
    gate = gate_call(intent, "source_control.rollback_release", {**PROD, "to_version": "v4.15"},
                     registry.get("source_control.rollback_release"), s.ledger)
    assert not gate.allowed and "[E2]" in gate.message


def test_writes_without_a_version_are_not_version_checked(world, registry):
    intent = parse_intent(SCENARIOS["S3"]["prompt"], **CONTEXT)
    record = registry.get("kubernetes.restart_deployment")
    assert gate_call(intent, "kubernetes.restart_deployment", {**PROD, "deployment": "checkout-api"}, record, EvidenceLedger()).allowed


def test_the_evidence_list_says_what_each_receipt_shows(world):
    s = Session(world)
    s.run("source_control.get_commit", {"repository": "shop/checkout-api", "sha": "a91f3c2"})
    s.rollback()
    s.run("observability.query_error_rate", {**PROD, "time_range": "15m"})
    commit, rollback, errors = (describe(r, "checkout-api", "production") for r in s.ledger.receipts)
    assert commit == "commit a91f3c2: Migrate order persistence to orders-client v3"
    assert rollback.startswith("rolled checkout-api in production back from v4.17 to v4.16 through the release pipeline")
    assert errors.startswith("production error_rate_pct ")


def test_the_report_lists_actions_that_did_not_run(world):
    intent = parse_intent(SCENARIOS["S4"]["prompt"], **CONTEXT)
    ledger = EvidenceLedger()
    ledger.not_executed.append(NotExecuted(0, "source_control.rollback_release", {"to_version": "v4.15"}, "approval rejected"))
    report = render_report(intent, ledger)
    assert "Not executed: source_control.rollback_release (approval rejected)" in report


def test_a_request_for_a_recommendation_does_not_run_the_fix(world, registry):
    intent = parse_intent(SCENARIOS["S1"]["prompt"], **CONTEXT)
    s = Session(world)
    s.deployments()
    for tool_id, args in (("source_control.rollback_release", {**PROD, "to_version": "v4.16"}),
                          ("kubernetes.restart_deployment", {**PROD, "deployment": "checkout-api"})):
        gate = gate_call(intent, tool_id, args, registry.get(tool_id), s.ledger)
        assert not gate.allowed and "recommend" in gate.message
    update = gate_call(intent, "itsm.update_incident", {"incident_id": "INC-4917", "status": "investigating"},
                       registry.get("itsm.update_incident"), s.ledger)
    assert update.allowed


def test_read_only_requests_block_every_write(world, registry):
    intent = parse_intent(SCENARIOS["S2"]["prompt"], **CONTEXT)
    ledger = EvidenceLedger()
    for tool_id in ("source_control.rollback_release", "itsm.update_incident", "kubernetes.restart_deployment"):
        assert not gate_call(intent, tool_id, {**PROD, "incident_id": "INC-4917"}, registry.get(tool_id), ledger).allowed
    assert gate_call(intent, "observability.get_service_health", dict(PROD), registry.get("observability.get_service_health"), ledger).allowed


def test_unregistered_tools_count_as_writes_for_read_only_requests():
    intent = parse_intent(SCENARIOS["S2"]["prompt"], **CONTEXT)
    assert not gate_call(intent, "ops_debug.kubectl_exec", {"command": "ls"}, None, EvidenceLedger()).allowed


# ---------------------------------------------------------------------------------------------- requirements
def test_investigation_requirements_follow_the_evidence_chain(world):
    intent = parse_intent(SCENARIOS["S1"]["prompt"], **CONTEXT)
    s = Session(world)
    assert next_requirement(intent, s.ledger).name == "deployment"
    s.deployments()
    req = next_requirement(intent, s.ledger)
    assert req.name == "diff" and "a91f3c2" in req.query
    s.diff()
    assert next_requirement(intent, s.ledger).name == "pool"
    s.pool()
    assert next_requirement(intent, s.ledger).name == "incident_update"
    s.run("itsm.update_incident", {"incident_id": "INC-4917", "status": "identified"})
    assert next_requirement(intent, s.ledger) is None


def test_an_incident_update_made_before_the_diagnosis_must_be_repeated(world):
    intent = parse_intent(SCENARIOS["S1"]["prompt"], **CONTEXT)
    s = Session(world)
    s.deployments()
    s.run("itsm.update_incident", {"incident_id": "INC-4917", "status": "investigating"})
    s.diff(), s.pool()
    req = next_requirement(intent, s.ledger)
    assert req.name == "incident_update" and "root cause" in req.query
    assert missing_requirements(intent, s.ledger) == ["incident_update"]
    s.run("itsm.update_incident", {"incident_id": "INC-4917", "status": "identified"})
    assert next_requirement(intent, s.ledger) is None and missing_requirements(intent, s.ledger) == []


def test_an_incident_update_made_before_the_verification_must_be_repeated(world):
    intent = parse_intent("Roll back checkout-api, verify that latency recovered, and update the incident.", **CONTEXT)
    s = Session(world)
    s.rollback()
    s.run("itsm.update_incident", {"incident_id": "INC-4917", "status": "monitoring"})
    assert next_requirement(intent, s.ledger).name == "verification"
    s.health()
    assert next_requirement(intent, s.ledger).name == "incident_update"
    s.run("itsm.add_incident_comment", {"incident_id": "INC-4917", "comment": "verified"})
    assert next_requirement(intent, s.ledger) is None


def test_action_requirements_need_remediation_then_verification(world):
    intent = parse_intent(SCENARIOS["S4"]["prompt"], **CONTEXT)
    s = Session(world)
    s.deployments()
    assert next_requirement(intent, s.ledger).name == "remediation"
    s.rollback()
    assert next_requirement(intent, s.ledger).name == "verification"
    s.health()
    assert next_requirement(intent, s.ledger) is None


def test_an_action_request_looks_up_the_release_before_rolling_back(world):
    intent = parse_intent(SCENARIOS["S4"]["prompt"], **CONTEXT)
    s = Session(world)
    first = next_requirement(intent, s.ledger)
    assert first.name == "deployment" and "roll back to" in first.why
    s.deployments()
    req = next_requirement(intent, s.ledger)
    assert req.name == "remediation" and "from v4.17 to v4.16" in req.query


def test_read_only_requests_never_ask_for_remediation(world):
    intent = parse_intent(SCENARIOS["S2"]["prompt"], **CONTEXT)
    s = Session(world)
    s.deployments(), s.diff(), s.pool()
    assert next_requirement(intent, s.ledger) is None


# ---------------------------------------------------------------------------------------------- reports
def test_complete_report_cites_receipts_and_recommends_from_evidence(world):
    intent = parse_intent(SCENARIOS["S2"]["prompt"], **CONTEXT)
    s = Session(world)
    s.deployments(), s.diff(), s.pool()
    report = render_report(intent, s.ledger)
    assert report.startswith("FINAL:") and "incomplete" not in report.lower()
    assert "v4.17" in report and "[E1" in report and "v4.16" in report
    assert "recovered" not in report.lower()


def test_incomplete_report_lists_what_is_missing(world):
    intent = parse_intent(SCENARIOS["S4"]["prompt"], **CONTEXT)
    s = Session(world)
    s.rollback()
    report = render_report(intent, s.ledger)
    assert "incomplete" in report.lower() and "verification" in report.lower()
    assert "recovered" not in report.lower()


def test_verified_report_states_the_measured_values(world):
    intent = parse_intent(SCENARIOS["S4"]["prompt"], **CONTEXT)
    s = Session(world)
    s.rollback(), s.health()
    report = render_report(intent, s.ledger)
    v = verify_recovery(s.ledger, "checkout-api", "production")
    assert f"{v.p95_ms}" in report and "400" in report and "incomplete" not in report.lower()
