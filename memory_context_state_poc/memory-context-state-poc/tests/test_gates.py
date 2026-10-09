"""Scope, lifecycle and provenance gates: each failure class is excluded for the right reason, valid records pass."""

from governed_memory.retrieval.gates import lifecycle_gate, provenance_gate, scope_gate

from .conftest import rec


# ---------------------------------------------------------------- scope
def test_wrong_tenant_excluded(query):
    assert scope_gate(rec("a", scope={"tenant": "globex", "environment": "production", "entities": ["checkout-api"]}), query) == "wrong_tenant"


def test_wrong_environment_excluded(query):
    assert scope_gate(rec("a", scope={"tenant": "acme", "environment": "staging", "entities": ["checkout-api"]}), query) == "wrong_environment"


def test_environment_all_is_in_scope(query):
    assert scope_gate(rec("a", scope={"tenant": "acme", "environment": "all", "entities": ["checkout-api"]}), query) is None


def test_entity_scope_respected(query):
    assert scope_gate(rec("a", scope={"tenant": "acme", "environment": "production", "entities": ["payment-gateway"]}), query) == "wrong_entity"
    assert scope_gate(rec("a", scope={"tenant": "acme", "environment": "production", "entities": ["*"]}), query) is None
    assert scope_gate(rec("a", scope={"tenant": "acme", "environment": "production", "entities": ["orders-db"]}), query) is None


def test_session_scoped_record_only_visible_in_its_session(query):
    other = rec("a", scope={"tenant": "acme", "environment": "all", "entities": ["checkout-api"], "user": "alice", "session": "ses-other"})
    same = rec("b", scope={"tenant": "acme", "environment": "all", "entities": ["checkout-api"], "user": "alice", "session": query.session})
    assert scope_gate(other, query) == "other_session"
    assert scope_gate(same, query) is None


def test_user_scoped_record_hidden_from_other_users(query):
    r = rec("a", scope={"tenant": "acme", "environment": "all", "entities": ["*"], "user": "bob"})
    assert scope_gate(r, query) == "other_user"


# ---------------------------------------------------------------- lifecycle
def test_expired_excluded_at_the_fixed_clock(query):
    assert lifecycle_gate(rec("a", expires_at="2026-09-11T14:00:00Z"), query, present_ids=set()) == "expired"


def test_active_retained(query):
    assert lifecycle_gate(rec("a", expires_at="2026-12-01T00:00:00Z"), query, present_ids=set()) is None
    assert lifecycle_gate(rec("a", expires_at=None), query, present_ids=set()) is None


def test_superseded_excluded_when_replacement_exists(query):
    old = rec("old", superseded_by="new")
    assert lifecycle_gate(old, query, present_ids={"old", "new"}) == "superseded"


# ---------------------------------------------------------------- provenance / trust
def test_missing_provenance_excluded(query, policy):
    assert provenance_gate(rec("a", provenance=None), query, policy) == "no_provenance"
    assert provenance_gate(rec("a", provenance={"created_by": "", "evidence_refs": []}), query, policy) == "no_provenance"


def test_unverified_external_excluded(query, policy):
    assert provenance_gate(rec("a", trust={"source_class": "unverified-external"}), query, policy) == "unverified"


def test_workflow_status_never_answered_from_memory(query, policy):
    assert provenance_gate(rec("a", claim_type="workflow_status"), query, policy) == "workflow_state_not_memory"


def test_verified_episode_passes(query, policy):
    assert provenance_gate(rec("a"), query, policy) is None
