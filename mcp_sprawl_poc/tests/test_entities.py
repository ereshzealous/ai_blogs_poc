"""Entity lookup (discovery v5): named things in a request, resolved against the inventory, by rule."""

from __future__ import annotations

import pytest

from control_plane.discovery.entities import EntityResolver


@pytest.fixture(scope="module")
def resolver():
    return EntityResolver.from_scenario()


def one(resolver, text, kind):
    found = [e for e in resolver.resolve(text) if e.type == kind]
    assert len(found) == 1, (text, resolver.resolve(text))
    return found[0]


def test_a_flag_key_is_a_known_flag(resolver):
    flag = one(resolver, "Kill new-pricing-engine in production. Turn it off completely.", "flag")
    assert (flag.id, flag.environment, flag.known) == ("new-pricing-engine", "production", True)


def test_a_flag_can_be_named_loosely(resolver):
    assert one(resolver, "switch off the new pricing flag", "flag").id == "new-pricing-engine"
    assert one(resolver, "is the async inventory toggle on?", "flag").id == "checkout-async-inventory"
    assert not [e for e in resolver.resolve("what is the new pricing for checkout?") if e.type == "flag"]


def test_instances_and_tasks_are_recognised_known_or_not(resolver):
    known = one(resolver, "is i-0c41e7a9d2b3f5812 (the checkout batch worker) even up?", "instance")
    assert (known.known, known.environment) == (True, "production")
    unknown = one(resolver, "reboot i-0123456789abcdef0", "instance")
    assert (unknown.known, unknown.id, unknown.environment) == (False, "i-0123456789abcdef0", None)
    assert one(resolver, "task-checkout-exporter-3f9a stopped exporting", "task").environment == "production"


def test_pods_by_name_and_by_reference(resolver):
    pod = one(resolver, "can you restart checkout-api-6c7d8e9f0-d3e4f in staging?", "pod")
    assert (pod.id, pod.environment, pod.service) == ("checkout-api-6c7d8e9f0-d3e4f", "staging", "checkout-api")
    loose = one(resolver, "bounce the bad pod in payments", "pod")
    assert (loose.id, loose.known, loose.service) == (None, False, "payment-gateway")
    assert not [e for e in resolver.resolve("restart the checkout pods") if e.type == "pod"]


def test_channels(resolver):
    assert one(resolver, "note it in #inc-4917-checkout-latency", "channel").known
    war_room = one(resolver, "post in #inc-4917-war-room", "channel")
    assert (war_room.known, war_room.id) == (False, "#inc-4917-war-room")
    assert one(resolver, "tell the war room we are rolling back", "channel").id is None


def test_incidents_deployments_commits_and_traces(resolver):
    assert one(resolver, "what's the status of INC-4917?", "incident").environment == "production"
    assert not one(resolver, "look at INC-1234", "incident").known
    assert not [e for e in resolver.resolve("post in #inc-4917-checkout-latency") if e.type == "incident"]
    assert one(resolver, "show DEP-88213", "deployment").environment == "production"
    assert one(resolver, "diff for a91f3c2 please", "commit").known
    assert not one(resolver, "diff for deadbee1 please", "commit").known
    assert one(resolver, "open trace 4bf92f3577b34da6a3ce929d0e0e4736", "trace").known
    assert one(resolver, "what went into v4.16?", "release").id == "v4.16"


def test_databases_and_caches(resolver):
    db = one(resolver, "slowest statements on orders-db-prod", "database")
    assert (db.id, db.environment) == ("orders-db-prod", "production")
    assert one(resolver, "is redis-sessions-prod healthy?", "cache").known
    loose = one(resolver, "check the orders db in staging", "database")
    assert (loose.id, loose.known) == (None, True)


def test_services_are_context_not_evidence(resolver):
    svc = one(resolver, "checkout latency is up", "service")
    assert svc.id == "checkout-api"
    assert resolver.evidence_types(resolver.resolve("checkout latency is up")) == set()


def test_environment_and_domains_from_entities(resolver):
    found = resolver.resolve("Kill new-pricing-engine now")
    assert resolver.environment(found) == "production"
    assert resolver.domains(found) == ["feature-flags"]
    mixed = resolver.resolve("restart checkout-api-6c7d8e9f0-d3e4f and check i-0c41e7a9d2b3f5812")
    assert resolver.environment(mixed) is None
    assert resolver.evidence_types(mixed) == {"pod", "instance"}
