"""Discovery v5: entity lookup, declared canonical capabilities, confidence and one meaning-based question.

The model is a scripted stand-in and retrieval is lexical only; held-out set 3 measures the real thing.
"""

from __future__ import annotations

import json

import pytest

from agent.llm import LLMResponse
from control_plane.discovery.clarify import Constraint, answer_constraint, build_question, simulated_answer
from control_plane.discovery.pipeline import DiscoveryService
from control_plane.discovery.resolver import decide
from control_plane.discovery.rewrite import QueryRewriter
from control_plane.paths import CATALOG_DIR
from control_plane.registry.capabilities import CapabilityCatalog


class ScriptedModel:
    def __init__(self, replies):
        self.replies = dict(replies)

    def chat(self, messages, tools=None, options=None):
        return LLMResponse(self.replies.get(messages[-1]["content"], "not json"), [], 120, 30, 5.0)


def reply(first_step, operation, system, environment=None):
    return json.dumps({"first_step": first_step, "operation": operation, "system": system, "environment": environment})


FLAG = "Kill new-pricing-engine in production. Turn it off completely."
NOTE = "Wrapping up: drop a final 'mitigated, monitoring' note in #inc-4917-checkout-latency."
POD = "can you restart checkout-api-6c7d8e9f0-d3e4f in staging? it's stuck"
BOUNCE = "bounce checkout in prod"
PAST = "has this happened before? checkout throwing 5xx after a redis failover rings a bell"
RECYCLE = "Recycle checkout-api-7d9f8c6b5-2kq8x on prod-eu-west-1, it's the noisy one."
TOGGLE = "did somebody flip a toggle in staging recently?"
ROLLBACK = "Roll back checkout-api in production to the previous release"
REPLIES = {
    FLAG: reply("restart the new-pricing-engine deployment", "write", "kubernetes", "production"),  # a wrong reading
    NOTE: reply("add a note to the incident", "write", "incident management"),
    POD: reply("restart the stuck pod", "write", "kubernetes", "staging"),
    BOUNCE: reply("restart checkout-api", "write", "kubernetes", "production"),
    ROLLBACK: reply("roll back checkout-api to the previous release", "write", "release pipeline and code", "production"),
    PAST: reply("search past incidents for redis failover", "read", "incident management"),
    RECYCLE: reply("check pod logs", "read", "kubernetes", "production"),
    TOGGLE: reply("check recent changes to feature flags", "read", "feature flags", "staging"),
}


def service(profile="v5", ablation=None):
    manifest = json.loads((CATALOG_DIR / "catalog_500.json").read_text())
    tools = {f"{t['server']}.{t['name']}": (t["server"], t["name"], t["description"], t["input_schema"]) for t in manifest["tools"]}
    from control_plane.registry.registry import CapabilityRegistry
    return DiscoveryService(tools, CapabilityRegistry.load(), embedder=None, profile=profile,
                            rewriter=QueryRewriter(ScriptedModel(REPLIES)), ablation=ablation)


@pytest.fixture(scope="module")
def v5():
    return service()


@pytest.fixture(scope="module")
def catalog():
    return CapabilityCatalog.load()


def test_a_named_flag_surfaces_the_flag_tool_even_when_the_model_misreads_the_request(v5):
    res = v5.resolve(FLAG)
    assert "feature_flags.set_flag" in res.tool_ids
    assert [e["type"] for e in res.entities if e["type"] != "service"] == ["flag"]
    assert res.route.domains[:2] == ["runtime", "feature-flags"]


def test_a_named_channel_surfaces_the_chat_tool(v5):
    res = v5.resolve(NOTE)
    assert {"collaboration.post_message", "itsm.add_incident_comment"} <= set(res.tool_ids)


def test_one_implementation_per_capability_and_the_organisations_tool(v5, catalog):
    res = v5.resolve(POD)
    assert res.tool_ids[0] == "kubernetes.restart_pod"
    assert "k8s_staging_eu.restart_pod" not in res.tool_ids
    caps = [catalog.capability_of(t) for t in res.tool_ids]
    assert len(caps) == len(set(caps))
    assert res.route.environment == "staging"


def test_the_release_rollback_leads_and_the_margin_is_reported(v5):
    res = v5.resolve(ROLLBACK)
    assert res.tool_ids[0] == "source_control.rollback_release"
    assert res.capabilities[0]["capability"] == "service-release.rollback"
    assert res.margin == pytest.approx(res.capabilities[0]["score"] - res.capabilities[1]["score"])


def test_the_boost_follows_the_models_read_or_write_judgement(v5, catalog):
    res = v5.resolve(PAST)  # "failover" is a write word, but the user asks a question
    assert res.route.operation == "write"  # writes stay available
    assert not catalog.get(res.tool_ids[0]).side_effect and "itsm.search_incidents" in res.tool_ids[:3]
    assert all(not c["operation_match"] for c in res.capabilities if catalog.capabilities[c["capability"]].side_effect)


def test_the_write_slot_prefers_a_write_on_the_named_entity(v5):
    res = v5.resolve(RECYCLE)  # the model misread it as a read; the pod is named
    assert res.stages["write_slots"] == 1 and res.tool_ids[-1] == "kubernetes.restart_pod"


def test_an_unnamed_mention_suggests_a_system_but_is_not_evidence(v5):
    res = v5.resolve(TOGGLE)
    assert "feature-flags" in res.route.domains and res.evidence_types == []
    assert not any(c["entity_match"] for c in res.capabilities)


def test_a_constraint_keeps_only_matching_capabilities(v5, catalog):
    chat = v5.resolve(NOTE, constraint=Constraint(dimension="system", value="chat"))
    assert chat.tool_ids and all(catalog.get(t).system == "chat" for t in chat.tool_ids)
    assert chat.tool_ids[0] == "collaboration.post_message"
    without = v5.resolve(NOTE, constraint=Constraint(exclude=frozenset({"chat-message.post", "incident.comment"})))
    assert not {"collaboration.post_message", "itsm.add_incident_comment"} & set(without.tool_ids)
    reads = v5.resolve(BOUNCE, constraint=Constraint(reads_only=True))
    assert reads.tool_ids and not any(catalog.get(t).side_effect for t in reads.tool_ids)


def test_ablations(catalog):
    no_entities = service(ablation="no-entities").resolve(FLAG)
    assert no_entities.entities == [] and "feature_flags.set_flag" not in no_entities.tool_ids
    no_canonical = service(ablation="no-canonical").resolve(POD)
    assert "k8s_staging_eu.restart_pod" in no_canonical.tool_ids or "kubernetes.restart_pod" in no_canonical.tool_ids
    with pytest.raises(ValueError):
        service(ablation="no-such-thing")


# ---------------------------------------------------------------------------------------------- confidence
THRESHOLDS = {"READ_ONLY": 0.1, "LOW_RISK_WRITE": 0.2, "HIGH_RISK_WRITE": 0.3}


def test_an_agreeing_pick_with_a_clear_margin_is_automatic(v5):
    res = v5.resolve(ROLLBACK)
    d = decide(res, "source_control.rollback_release", THRESHOLDS | {"HIGH_RISK_WRITE": 0.0}, catalog=v5.catalog)
    assert d.agreement and d.tier == "HIGH_RISK_WRITE"
    assert d.auto == d.structural
    assert d.structural == (res.rewrite is not None and d.checks["system"] and d.checks["authoritative"] and d.checks["entities"])


def test_disagreement_or_a_small_margin_asks(v5):
    res = v5.resolve(ROLLBACK)
    assert not decide(res, "kubernetes.rollback_deployment", THRESHOLDS, catalog=v5.catalog).auto
    assert not decide(res, "source_control.rollback_release", THRESHOLDS | {"HIGH_RISK_WRITE": 99.0}, catalog=v5.catalog).auto
    assert not decide(res, "source_control.rollback_release", THRESHOLDS | {"HIGH_RISK_WRITE": None}, catalog=v5.catalog).auto
    assert not decide(res, None, THRESHOLDS, catalog=v5.catalog).auto


def test_high_risk_writes_need_the_structural_checks(v5):
    res = v5.resolve(POD)
    d = decide(res, "kubernetes.restart_pod", {"HIGH_RISK_WRITE": 0.0}, catalog=v5.catalog)
    assert d.checks == {"entities": True, "authoritative": True, "system": True, "operation": True} and d.auto


# ---------------------------------------------------------------------------------------------- the question
def test_the_question_compares_systems_in_plain_words(v5):
    res = v5.resolve(NOTE)
    q = build_question(res, "itsm.add_incident_comment", catalog=v5.catalog, prefer="collaboration.post_message")
    assert q.dimension == "system"
    assert {o.value for o in q.options} == {"chat", "incident management"}
    assert "__" not in q.text and "post_message" not in q.text and "?" in q.text


def test_the_question_compares_resources_and_actions(v5, catalog):
    res = v5.resolve(BOUNCE)
    q = build_question(res, "kubernetes.restart_pod", catalog=catalog, prefer="kubernetes.restart_deployment")
    assert (q.dimension, {o.value for o in q.options}) == ("resource", {"kubernetes pod", "kubernetes deployment"})
    q = build_question(res, "kubernetes.restart_deployment", catalog=catalog, prefer="kubernetes.rollback_deployment")
    assert (q.dimension, {o.value for o in q.options}) == ("action", {"restart", "roll back"})


def test_no_question_when_the_two_capabilities_cannot_be_told_apart(v5, catalog):
    res = v5.resolve(BOUNCE)  # two DBA reads: both "read database sessions in the database"
    assert build_question(res, "db_admin.show_processlist", catalog=catalog, prefer="db_admin.get_db_connections") is None


def test_the_simulated_user_answers_only_from_the_hidden_intent(v5, catalog):
    q = build_question(v5.resolve(NOTE), "itsm.add_incident_comment", catalog=catalog, prefer="collaboration.post_message")
    assert simulated_answer({"system": "chat", "resource": "chat message"}, q).value == "chat"
    assert simulated_answer({"system": "database"}, q).kind == "neither"
    assert simulated_answer({"system": None, "resource": "incident"}, q).kind == "not_sure"


def test_answers_become_constraints(v5, catalog):
    q = build_question(v5.resolve(NOTE), "itsm.add_incident_comment", catalog=catalog, prefer="collaboration.post_message")
    chosen = answer_constraint(q, simulated_answer({"system": "chat"}, q), catalog=catalog)
    assert (chosen.dimension, chosen.value) == ("system", "chat")
    neither = answer_constraint(q, simulated_answer({"system": "database"}, q), catalog=catalog)
    assert neither.exclude == {o.capability for o in q.options}
    unsure = answer_constraint(q, simulated_answer({}, q), catalog=catalog)
    assert unsure is None  # both options are writes: abstain
    q2 = build_question(v5.resolve(BOUNCE), "kubernetes.restart_pod", catalog=catalog, prefer="kubernetes.get_pods")
    assert answer_constraint(q2, simulated_answer({}, q2), catalog=catalog).reads_only
