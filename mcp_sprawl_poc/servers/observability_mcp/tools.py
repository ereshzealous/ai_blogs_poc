"""observability-mcp: metrics, logs, traces, alerts and dashboards for application services."""

from servers.common.meta import registry_record
from servers.common.toolspec import ENVIRONMENT, SERVICE, TIME_RANGE, ToolSpec, schema

S = "observability"
OWNER = "observability-platform"
METRICS = [
    "latency_p50_ms",
    "latency_p95_ms",
    "error_rate_pct",
    "requests_per_second",
    "db_pool_acquire_wait_p95_ms",
    "db_pool_in_use",
    "db_pool_max",
    "db_pool_waiting",
    "cpu_utilization_pct",
    "memory_utilization_pct",
]


def _read(capability: str, resource: str, ops: list[str], authoritative: list[str] | None = None) -> dict:
    return registry_record(
        domain="observability", capability=capability, resource_type=resource, operations=ops,
        risk="READ_ONLY", owner=OWNER, scopes=["observability.read"], authoritative_for=authoritative,
    )


TOOLS = [
    ToolSpec(
        S, "query_metrics",
        "Query a time series for one application metric of a service over a lookback window. Supports "
        "latency percentiles, error rate, throughput, CPU/memory utilisation and database connection-pool "
        "metrics (acquire wait, in-use, max, waiting). Returns a summary and a downsampled series.",
        schema({"service": SERVICE, "metric": {"type": "string", "enum": METRICS}, "environment": ENVIRONMENT,
                "time_range": TIME_RANGE}, ["service", "metric", "environment"]),
        title="Query metrics", read_only_hint=True, open_world_hint=False, handler="observability:query_metrics",
        collision_group="metrics", registry=_read("metrics-query", "service-metric", ["query"], ["service-metric"]),
    ),
    ToolSpec(
        S, "query_latency",
        "Get request latency percentiles (p50, p95 or p99) for a service's HTTP endpoints over a lookback "
        "window, compared with the service's latency SLO.",
        schema({"service": SERVICE, "environment": ENVIRONMENT,
                "percentile": {"type": "string", "enum": ["p50", "p95", "p99"]}, "time_range": TIME_RANGE},
               ["service", "environment", "percentile"]),
        title="Query latency", read_only_hint=True, open_world_hint=False, handler="observability:query_latency",
        collision_group="latency", registry=_read("latency-query", "service-latency", ["query"], ["service-latency"]),
    ),
    ToolSpec(
        S, "query_error_rate",
        "Get the percentage of failed requests (5xx and timeouts) for a service over a lookback window.",
        schema({"service": SERVICE, "environment": ENVIRONMENT, "time_range": TIME_RANGE}, ["service", "environment"]),
        title="Query error rate", read_only_hint=True, open_world_hint=False, handler="observability:query_error_rate",
        collision_group="errors", registry=_read("error-rate-query", "service-error-rate", ["query"], ["service-error-rate"]),
    ),
    ToolSpec(
        S, "search_logs",
        "Search application logs emitted by a service's containers. Filter by free-text query, log level and "
        "lookback window. Returns matching message patterns with counts and a few sample lines. This is the "
        "system of record for application logs.",
        schema({"service": SERVICE, "environment": ENVIRONMENT, "query": {"type": "string", "description": "Free-text filter, e.g. timeout."},
                "level": {"type": "string", "enum": ["DEBUG", "INFO", "WARN", "ERROR"]}, "time_range": TIME_RANGE},
               ["service", "environment"]),
        title="Search application logs", read_only_hint=True, open_world_hint=False, handler="observability:search_logs",
        collision_group="logs", registry=_read("log-search", "application-logs", ["search"], ["application-logs"]),
    ),
    ToolSpec(
        S, "get_trace",
        "Fetch one distributed trace by trace ID, with every span's service, name and duration.",
        schema({"trace_id": {"type": "string", "description": "32-character hex trace ID."}}, ["trace_id"]),
        title="Get trace", read_only_hint=True, open_world_hint=False, handler="observability:get_trace",
        collision_group="traces", registry=_read("trace-lookup", "distributed-trace", ["get"], ["distributed-trace"]),
    ),
    ToolSpec(
        S, "search_traces",
        "Find recent distributed traces for a service, optionally only those slower than a duration threshold. "
        "Returns trace IDs with root span, duration and the slowest child span.",
        schema({"service": SERVICE, "environment": ENVIRONMENT,
                "min_duration_ms": {"type": "integer", "minimum": 0}, "time_range": TIME_RANGE}, ["service", "environment"]),
        title="Search traces", read_only_hint=True, open_world_hint=False, handler="observability:search_traces",
        collision_group="traces", registry=_read("trace-search", "distributed-trace", ["search"], ["distributed-trace"]),
    ),
    ToolSpec(
        S, "get_service_health",
        "Summarise the current health of an application service: SLO status for latency and availability, "
        "active alerts and a healthy/degraded/down verdict.",
        schema({"service": SERVICE, "environment": ENVIRONMENT}, ["service", "environment"]),
        title="Get service health", read_only_hint=True, open_world_hint=False, handler="observability:get_service_health",
        collision_group="service-health", registry=_read("service-health", "application-service", ["get"], ["application-service-health"]),
    ),
    ToolSpec(
        S, "get_alerts",
        "List monitoring alerts, optionally filtered by service, environment and state (firing or resolved).",
        schema({"service": SERVICE, "environment": ENVIRONMENT,
                "state": {"type": "string", "enum": ["firing", "resolved", "any"]}}, []),
        title="Get alerts", read_only_hint=True, open_world_hint=False, handler="observability:get_alerts",
        collision_group="alerts", registry=_read("alert-query", "monitoring-alert", ["list"], ["monitoring-alert"]),
    ),
    ToolSpec(
        S, "get_dashboard",
        "Get the standard service dashboard: current values of the golden-signal panels (latency, errors, "
        "traffic, saturation) for a service.",
        schema({"service": SERVICE, "environment": ENVIRONMENT}, ["service", "environment"]),
        title="Get dashboard", read_only_hint=True, open_world_hint=False, handler="observability:get_dashboard",
        collision_group="dashboards", registry=_read("dashboard", "service-dashboard", ["get"]),
    ),
]
