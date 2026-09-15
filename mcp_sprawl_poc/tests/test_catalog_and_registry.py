"""Catalog generation, tool metadata validation and registry behaviour."""

from __future__ import annotations

import json
import re

from benchmark.catalog_generator.generator import LADDER, build_pool
from control_plane.paths import CATALOG_DIR
from servers.common.handlers import resolve
from servers.core_catalog import CORE_TOOLS

EXPOSED_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _manifest(name: str) -> dict:
    return json.loads((CATALOG_DIR / f"{name}.json").read_text())


def test_generation_is_deterministic():
    a, b = build_pool(), build_pool()
    assert [t.tool_id for t in a["pool"]] == [t.tool_id for t in b["pool"]]
    assert a["variants"] == b["variants"]


def test_committed_catalogs_match_generator():
    built = build_pool()
    for n in LADDER:
        assert [f"{t['server']}.{t['name']}" for t in _manifest(f"catalog_{n}")["tools"]] == built["ladder"][n]


def test_ladder_is_nested_and_sized():
    previous: set[str] = set()
    for n in LADDER:
        ids = {f"{t['server']}.{t['name']}" for t in _manifest(f"catalog_{n}")["tools"]}
        assert len(ids) == n
        assert previous <= ids
        previous = ids


def test_pool_composition():
    counts = build_pool()["counts"]
    assert counts == {"core": 50, "operational": 150, "business": 300}


def test_semantic_collisions_are_real_names():
    names = {t["name"] for t in _manifest("catalog_500")["tools"]}
    for name in ["search_logs", "query_logs", "find_logs", "get_logs", "get_pod_logs", "query_cloud_logs", "search_application_logs",
                 "restart_service", "restart_pod", "restart_deployment", "restart_instance", "restart_task", "redeploy_service",
                 "rollback_deployment", "rollback_release", "get_incident", "find_incident", "query_incidents", "get_incident_details"]:
        assert name in names, name


def test_tool_metadata_is_valid():
    for tool in _manifest("catalog_500")["tools"]:
        assert EXPOSED_NAME.match(f"{tool['server']}__{tool['name']}")
        assert tool["description"] and len(tool["description"]) > 15
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert set(schema["required"]) <= set(schema["properties"])
        resolve(tool["handler"])  # every tool has a backend


def test_registry_loads_every_registered_tool(registry):
    assert len(registry) == 495
    rec = registry.get("source_control.rollback_release")
    assert rec.risk == "HIGH_RISK_WRITE" and rec.requires_approval and rec.authoritative
    assert registry.get("ops_debug.exec_command") is None  # shadow server is not registered


def test_registry_records_are_consistent(registry):
    for rec in registry.find(lifecycles=None):
        assert rec.read_only == (rec.risk == "READ_ONLY")
        assert rec.side_effect == (not rec.read_only)
        assert rec.requires_approval == (rec.risk == "HIGH_RISK_WRITE")
        assert rec.required_scopes
        assert rec.environments
        if rec.deprecated:
            assert rec.lifecycle == "deprecated"
        if rec.tool_id in CORE_TOOLS:
            assert rec.lifecycle == "active"


def test_registry_filters(registry):
    staging = registry.find(environment="staging", lifecycles=None)
    assert all("staging" in r.environments for r in staging)
    assert not any(r.server == "k8s_dev_eu" for r in staging)
    active = {r.tool_id for r in registry.find()}
    assert "legacy_monitoring.get_latency_report" not in active  # deprecated filtered out by default
    read_only = registry.find(max_risk="READ_ONLY")
    assert read_only and all(r.risk == "READ_ONLY" for r in read_only)
    obs = registry.find(domains=["observability"])
    assert all(r.domain == "observability" for r in obs)


def test_documented_catalog_facts():
    """README.md states these numbers; if the catalog changes, the README must change with it."""
    summary = json.loads((CATALOG_DIR / "catalog_summary.json").read_text())["ladder_composition"]["catalog_500"]
    assert (summary["tools_sharing_a_name"], summary["deprecated"], summary["unregistered"], summary["servers"]) == (59, 30, 5, 44)


def test_registry_drift_detection(registry):
    published = {t["server"] + "." + t["name"]: {"annotations": {"readOnlyHint": t["read_only_hint"]}}
                 for t in _manifest("catalog_500")["tools"]}
    report = registry.sync(published)
    assert set(report.unregistered) == {f"ops_debug.{n}" for n in ["exec_command", "kubectl_exec", "restart_service", "run_sql", "tail_logs"]}
    assert {m["tool_id"] for m in report.annotation_mismatches} == {"cloud_ops.restart_service", "cloud_ops.delete_volume"}
    assert not report.clean
