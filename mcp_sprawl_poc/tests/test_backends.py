"""Incident evidence consistency in the deterministic mock backends."""

from __future__ import annotations

from servers.common.handlers import Ctx, resolve
from servers.core_catalog import CORE_TOOLS


def call(world, run_id, tool_id, args):
    spec = CORE_TOOLS[tool_id]
    return resolve(spec.handler)(Ctx(world, run_id, spec.server, spec), args)


def test_latency_regression_starts_after_deployment(world):
    deps = call(world, "r", "source_control.search_deployments", {"service": "checkout-api", "environment": "production", "limit": 1})
    assert deps["deployments"][0]["version"] == "v4.17" and deps["deployments"][0]["started_at"] == "2026-09-08T10:15:00Z"
    lat = call(world, "r", "observability.query_latency", {"service": "checkout-api", "environment": "production", "percentile": "p95", "time_range": "60m"})
    before = [p["value"] for p in lat["series"] if p["t"] < "10:15"]
    after = [p["value"] for p in lat["series"] if p["t"] >= "10:20"]
    assert max(before) < 250 and min(after) > 2000


def test_connection_pool_is_the_bottleneck(world):
    pool = call(world, "r", "database.get_connection_pool_stats", {"service": "checkout-api", "environment": "production"})
    assert pool["max_connections"] == 10 and pool["in_use"] == 10 and pool["waiting"] > 100
    logs = call(world, "r", "observability.search_logs", {"service": "checkout-api", "environment": "production", "level": "ERROR"})
    assert "ConnectionPoolTimeoutError" in logs["patterns"][0]["message"]
    trace = call(world, "r", "observability.get_trace", {"trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"})
    slowest = max(trace["spans"], key=lambda s: s["duration_ms"])
    assert slowest["name"] == "db.pool.acquire" and slowest["duration_ms"] > trace["duration_ms"] * 0.8
    diff = call(world, "r", "source_control.get_diff", {"sha": "a91f3c2"})
    assert "max_connections: 10" in diff["diff"] and "DB_POOL_MAX:50" in diff["diff"]


def test_red_herrings_are_ruled_out(world):
    pods = call(world, "r", "kubernetes.get_pods", {"service": "checkout-api", "environment": "production"})
    assert all(p["restarts"] == 0 and p["ready"] and p["cpu_pct"] < 50 for p in pods["pods"])
    pg = call(world, "r", "observability.query_latency", {"service": "payment-gateway", "environment": "production", "percentile": "p95", "time_range": "60m"})
    assert pg["summary"]["max"] < 400
    db = call(world, "r", "cloud.describe_resource", {"resource_id": "orders-db-prod"})
    assert db["metrics"]["cpu_utilization_pct"] < 30
    staging = call(world, "r", "observability.get_service_health", {"service": "checkout-api", "environment": "staging"})
    assert staging["status"] == "healthy"


def test_rollback_recovers_service_and_is_isolated_per_run(world):
    assert call(world, "a", "observability.get_service_health", {"service": "checkout-api", "environment": "production"})["status"] == "degraded"
    call(world, "a", "source_control.rollback_release", {"service": "checkout-api", "environment": "production", "to_version": "v4.16"})
    health = call(world, "a", "observability.get_service_health", {"service": "checkout-api", "environment": "production"})
    assert health["status"] == "healthy" and health["firing_alerts"] == []
    assert call(world, "a", "kubernetes.get_deployment", {"service": "checkout-api", "environment": "production"})["image"].endswith(":v4.16")
    assert call(world, "b", "observability.get_service_health", {"service": "checkout-api", "environment": "production"})["status"] == "degraded"


def test_restart_does_not_fix_the_regression(world):
    call(world, "r", "kubernetes.restart_deployment", {"service": "checkout-api", "environment": "production"})
    assert call(world, "r", "observability.get_service_health", {"service": "checkout-api", "environment": "production"})["status"] == "degraded"


def test_incident_updates_are_recorded(world):
    call(world, "r", "itsm.update_incident", {"incident_id": "INC-4917", "status": "monitoring", "root_cause": "v4.17 pool max 10"})
    call(world, "r", "itsm.add_incident_comment", {"incident_id": "INC-4917", "comment": "rolled back"})
    inc = call(world, "r", "itsm.get_incident", {"incident_id": "INC-4917"})
    assert inc["status"] == "monitoring" and inc["root_cause"] == "v4.17 pool max 10" and inc["comments"][0]["comment"] == "rolled back"
