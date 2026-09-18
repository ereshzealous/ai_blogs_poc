"""Declared canonical capabilities (discovery v5): one capability per job, with the organisation's implementation named."""

from __future__ import annotations

import hashlib
import json

import pytest

from benchmark.catalog_generator.capabilities import CAPABILITIES_FILE, build_capabilities
from control_plane.paths import CATALOG_DIR
from control_plane.registry.capabilities import CapabilityCatalog
from control_plane.registry.vocabulary import ACTIONS, CORE_SYSTEMS, RESOURCES

PUBLISHED_REGISTRY_SHA256 = "13b1ff437399bd5613177406f7b2862cb53a018dcbccd62dec9d51bdd295f04f"


@pytest.fixture(scope="module")
def catalog():
    return CapabilityCatalog.load()


def test_the_committed_file_is_what_the_builder_writes():
    assert json.loads(CAPABILITIES_FILE.read_text()) == build_capabilities()


def test_the_registry_itself_is_unchanged():
    assert hashlib.sha256((CATALOG_DIR / "registry.json").read_bytes()).hexdigest() == PUBLISHED_REGISTRY_SHA256


def test_every_registered_tool_has_exactly_one_capability(catalog, registry):
    records = json.loads((CATALOG_DIR / "registry.json").read_text())["records"]
    assert {r["tool_id"] for r in records} == set(catalog.tools)
    assert catalog.capability_of("ops_debug.restart_service") is None  # unregistered


def test_core_capabilities_use_the_intent_vocabulary_and_are_distinct(catalog):
    core = [c for c in catalog.capabilities.values() if c.core]
    assert len(core) == 50
    for c in core:
        assert c.system in CORE_SYSTEMS and c.resource in RESOURCES and c.action in ACTIONS, c.id
        assert c.use_when and c.not_for, c.id
    assert len({(c.system, c.resource, c.action) for c in core}) == 50


def test_each_capability_names_at_most_one_authoritative_tool(catalog):
    for c in catalog.capabilities.values():
        roles = [i.role for i in c.implementations]
        assert roles.count("authoritative") <= 1, c.id
        if c.authoritative:
            assert catalog.role_of(c.authoritative) == "authoritative"


def test_per_cluster_copies_are_environment_variants(catalog):
    assert catalog.capability_of("k8s_staging_eu.restart_pod") == catalog.capability_of("kubernetes.restart_pod")
    assert catalog.role_of("k8s_staging_eu.restart_pod") == "environment_variant"
    assert catalog.implementation("k8s_staging_eu.restart_pod").environments == ("staging",)
    assert catalog.role_of("k8s_prod_eu.restart_pod") == "legacy"
    assert catalog.capability_of("k8s_dev_eu.get_nodes") == catalog.capability_of("k8s_staging_eu.get_nodes") != \
        catalog.capability_of("kubernetes.get_pods")
    assert catalog.capability_of("k8s_dev_eu.describe_pod") == catalog.capability_of("kubernetes.get_pods")


def test_mirrors_are_substitutes_unless_they_do_another_job(catalog):
    assert catalog.capability_of("logstream.find_logs") == catalog.capability_of("observability.search_logs")
    assert catalog.role_of("logstream.find_logs") == "substitute"
    assert catalog.capability_of("db_admin.get_replication_lag") != catalog.capability_of("cloud.describe_resource")
    assert catalog.role_of("legacy_monitoring.get_latency_report") == "legacy"
    assert catalog.capability_of("legacy_monitoring.get_latency_report") == catalog.capability_of("observability.query_latency")


def test_no_other_capability_repeats_a_core_job(catalog):
    core = {(c.system, c.resource, c.action) for c in catalog.capabilities.values() if c.core}
    assert not [c.id for c in catalog.capabilities.values() if not c.core and (c.system, c.resource, c.action) in core]
    assert catalog.role_of("logstream.query_logs") == "substitute"


def test_declared_write_equivalents(catalog):
    release = catalog.capability_of("source_control.rollback_release")
    assert catalog.capability_of("cicd.rollback_pipeline") == release and catalog.role_of("cicd.rollback_pipeline") == "substitute"
    assert catalog.capability_of("cloud_ops.reboot_vm") == catalog.capability_of("cloud.restart_instance")
    assert catalog.role_of("servicedesk_v1.resolve_ticket") == "legacy"
    k8s_rollback = catalog.capability_of("kubernetes.rollback_deployment")
    assert k8s_rollback != release
    assert k8s_rollback in catalog.capabilities[release].not_equivalent
    assert release in catalog.capabilities[k8s_rollback].not_equivalent


def test_other_tools_keep_their_own_capability(catalog):
    assert catalog.capability_of("cloud_ops.restart_service") not in {
        catalog.capability_of("cloud.restart_instance"), catalog.capability_of("kubernetes.restart_deployment")}
    assert catalog.role_of("hr.get_employee") == "authoritative"


def test_entity_types_come_from_required_parameters(catalog):
    cap = catalog.capabilities
    assert cap[catalog.capability_of("kubernetes.restart_pod")].entity_types == ("pod",)
    assert cap[catalog.capability_of("feature_flags.set_flag")].entity_types == ("flag",)
    assert cap[catalog.capability_of("collaboration.post_message")].entity_types == ("channel",)
    assert set(cap[catalog.capability_of("cloud.describe_resource")].entity_types) == {"instance", "task", "database", "cache"}
    assert cap[catalog.capability_of("cache.get_key")].entity_types == ()
    assert cap[catalog.capability_of("observability.query_latency")].entity_types == ()


def test_risk_and_effect_come_from_the_registry(catalog):
    cap = catalog.capabilities[catalog.capability_of("source_control.rollback_release")]
    assert (cap.risk, cap.side_effect, cap.domain, cap.system) == ("HIGH_RISK_WRITE", True, "delivery", "release pipeline")
    read = catalog.capabilities[catalog.capability_of("itsm.get_incident")]
    assert (read.risk, read.side_effect) == ("READ_ONLY", False)


def test_the_canonical_implementation_follows_the_environment(catalog):
    cap = catalog.capability_of("kubernetes.restart_pod")
    allowed = {"kubernetes.restart_pod", "k8s_staging_eu.restart_pod"}
    assert catalog.canonical(cap, allowed, environment="staging") == "kubernetes.restart_pod"
    assert catalog.canonical(cap, {"k8s_staging_eu.restart_pod"}, environment="staging") == "k8s_staging_eu.restart_pod"
    assert catalog.canonical(cap, {"k8s_staging_eu.restart_pod"}, environment="production") is None
    logs = catalog.capability_of("observability.search_logs")
    assert catalog.canonical(logs, {"logstream.find_logs"}, environment="production") == "logstream.find_logs"
    assert catalog.canonical(logs, {"logstream.find_logs", "observability.search_logs"}, environment=None) == "observability.search_logs"
