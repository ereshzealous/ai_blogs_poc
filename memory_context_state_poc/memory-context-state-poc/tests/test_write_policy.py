"""Remembering is a write operation: the write policy decides what becomes memory, with which scope and authority."""

from datetime import timedelta

from governed_memory.write_policy.policy import WritePolicy, naive_write

from .conftest import CLOCK


def _events(scenario):
    return {e["id"]: e for e in scenario.write_events}


def test_user_assertion_becomes_contextual_session_scoped_memory(scenario, policy):
    d = WritePolicy.load().apply(_events(scenario)["evt-user-assertion"], clock=CLOCK)
    assert d.persisted and d.record.source_class == "user-asserted"
    assert policy.tier(d.record).label == "contextual"
    assert d.record.scope.session == "ses-s1-older" and d.record.scope.user == "alice"
    assert d.record.claim_type == "instruction" and d.record.expires_at == CLOCK + timedelta(hours=24)


def test_unverified_tool_output_not_persisted(scenario):
    d = WritePolicy.load().apply(_events(scenario)["evt-unverified-tool"], clock=CLOCK)
    assert not d.persisted and d.reason == "unregistered_tool"


def test_speculation_without_evidence_not_persisted(scenario):
    d = WritePolicy.load().apply(_events(scenario)["evt-model-speculation"], clock=CLOCK)
    assert not d.persisted and d.reason == "no_evidence"


def test_verified_outcome_persisted_as_advisory_episode_with_provenance(scenario, policy):
    d = WritePolicy.load().apply(_events(scenario)["evt-verified-outcome"], clock=CLOCK)
    assert d.persisted and policy.tier(d.record).label == "advisory"
    assert d.record.provenance and d.record.provenance.evidence_refs == ("wf-4917/verify", "PM-4917")
    assert d.record.scope.tenant == "acme" and d.record.scope.environment == "production"
    assert d.record.expires_at == CLOCK + timedelta(days=180)


def test_user_assertion_can_never_outrank_managed_knowledge(scenario, policy):
    d = WritePolicy.load().apply(_events(scenario)["evt-user-assertion"], clock=CLOCK)
    rb = scenario.record("kb-rb-chk-007")
    assert policy.tier(d.record).rank > policy.tier(rb).rank


def test_naive_writer_persists_everything_as_plain_memory(scenario):
    recs = [naive_write(e, clock=CLOCK) for e in scenario.write_events]
    assert len(recs) == 4 and all(r.content for r in recs)
