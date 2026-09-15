"""Deterministic tool-catalog generator.

    python -m benchmark.catalog_generator.generator            # writes benchmark/catalogs/

Produces a 500-tool pool: the 50 hand-written core tools plus 450 generated tools on generated MCP
servers, and from it the nested scale ladder (10, 25, 50, 100, 250, 500), the two fixed-size overlap
variants (low/high overlap at 100 tools) and the registry.

The generated tools are designed to be realistic, not numerous for its own sake:

* operational families (150 tools) create semantic collisions with the core catalog - a second log
  platform, an APM, legacy monitoring, a deprecated service desk, per-cluster Kubernetes servers, a
  CI/CD system, cloud operations tooling, adjacent domains (on-call, status page, cache, runbooks,
  security, network) and one unregistered "shadow" server;
* business families (300 tools) model the rest of an enterprise estate (HR, finance, CRM, support,
  orders, ...). Most are unrelated to incidents, a few are deliberate near-misses (support tickets,
  checkout funnels, customer orders).

Every generated tool carries `family` and `collision_group` so results can be sliced by them.
"""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any

from servers.common.meta import registry_record
from servers.common.toolspec import ENVIRONMENT, SERVICE, TIME_RANGE, ToolSpec, schema
from servers.core_catalog import CORE_LADDER_ORDER, CORE_TOOLS

SEED = 4917
LADDER = [10, 25, 50, 100, 250, 500]
OUT_DIR = Path(__file__).resolve().parents[1] / "catalogs"

# --------------------------------------------------------------------------------------------------
# Small DSL for operational servers
# --------------------------------------------------------------------------------------------------
Q = {"type": "string", "description": "Free-text query."}
POD = {"type": "string", "description": "Pod name."}
APP = {"type": "string", "description": "Application (deployment) name, e.g. checkout-api."}
INSTANCE = {"type": "string", "pattern": "^i-[0-9a-f]{8,17}$", "description": "Instance ID."}
INCIDENT_NUMBER = {"type": "string", "pattern": "^INC-[0-9]{4,6}$", "description": "Incident number."}
DEPLOY_ENV = {"type": "string", "enum": ["production", "staging", "development"], "description": "Target environment."}
VERSION = {"type": "string", "pattern": "^v[0-9]+\\.[0-9]+(\\.[0-9]+)?$"}
NODE = {"type": "string", "description": "Node name, e.g. ip-10-4-12-31."}

READ, LOW, HIGH = "READ_ONLY", "LOW_RISK_WRITE", "HIGH_RISK_WRITE"


def op_tool(name: str, description: str, props: dict[str, Any], required: list[str], *, risk: str = READ,
            capability: str, resource: str, group: str | None, handler: str, destructive: bool = False,
            read_only_hint: bool | None = None, notes: str | None = None, scopes: list[str] | None = None,
            authoritative: bool | None = None) -> dict[str, Any]:
    return dict(name=name, description=description, props=props, required=required, risk=risk, capability=capability,
                resource=resource, group=group, handler=handler, destructive=destructive, read_only_hint=read_only_hint,
                notes=notes, scopes=scopes, authoritative=authoritative)


def mirror(core_id: str, mapping: str = "") -> str:
    return f"generated:mirror|{core_id}|{mapping}"


def deprecated(core_id: str, mapping: str = "") -> str:
    return f"generated:deprecated|{core_id}|{mapping}"


WRITE = "generated:write"


def _k8s_cluster(env: str) -> list[dict[str, Any]]:
    fixed = f"environment={env}"
    m = lambda core, extra="": mirror(core, ",".join(filter(None, ["app>service", fixed, extra])))
    return [
        op_tool("get_pods", f"List pods for an app on the {env} EU cluster.", {"app": APP}, ["app"],
                capability="workload-read", resource="kubernetes-pod", group="runtime-state", handler=m("kubernetes.get_pods")),
        op_tool("describe_pod", f"Describe a pod on the {env} EU cluster: containers, probes, restarts and conditions.", {"pod": POD}, ["pod"],
                capability="workload-read", resource="kubernetes-pod", group="runtime-state", handler=m("kubernetes.get_pod_logs", "tail_lines=1")),
        op_tool("get_deployment", f"Get a Deployment object for an app on the {env} EU cluster.", {"app": APP}, ["app"],
                capability="workload-read", resource="kubernetes-deployment", group="deployment-lookup", handler=m("kubernetes.get_deployment")),
        op_tool("get_logs", f"Get container logs for a pod on the {env} EU cluster.", {"pod": POD, "tail": {"type": "integer"}}, ["pod"],
                capability="workload-read", resource="container-logs", group="logs", handler=m("kubernetes.get_pod_logs", "tail>tail_lines")),
        op_tool("get_nodes", f"List nodes of the {env} EU cluster with capacity and allocatable resources.", {}, [],
                capability="cluster-read", resource="kubernetes-node", group="runtime-state", handler="generated:record|kubernetes-node"),
        op_tool("restart_pod", f"Delete a pod on the {env} EU cluster so it is recreated.", {"pod": POD}, ["pod"], risk=HIGH,
                capability="workload-restart", resource="kubernetes-pod", group="restart", handler=WRITE),
        op_tool("restart_deployment", f"Rolling-restart all pods of an app on the {env} EU cluster.", {"app": APP}, ["app"], risk=HIGH,
                capability="workload-restart", resource="kubernetes-deployment", group="restart", handler=WRITE),
        op_tool("rollback_deployment", f"Undo the last rollout of an app on the {env} EU cluster (kubectl rollout undo).", {"app": APP}, ["app"],
                risk=HIGH, capability="deployment-rollback", resource="kubernetes-deployment", group="rollback", handler=WRITE),
        op_tool("scale_deployment", f"Set the replica count of an app on the {env} EU cluster.", {"app": APP, "replicas": {"type": "integer", "minimum": 0}},
                ["app", "replicas"], risk=HIGH, capability="workload-scale", resource="kubernetes-deployment", group="scale", handler=WRITE),
        op_tool("exec_in_pod", f"Run a command inside a container on the {env} EU cluster (kubectl exec).",
                {"pod": POD, "command": {"type": "string"}}, ["pod", "command"], risk=HIGH, capability="workload-exec",
                resource="kubernetes-pod", group="exec", handler=WRITE),
        op_tool("cordon_node", f"Mark a node on the {env} EU cluster unschedulable.", {"node": NODE}, ["node"], risk=HIGH,
                capability="node-maintenance", resource="kubernetes-node", group="node-maintenance", handler=WRITE),
        op_tool("drain_node", f"Evict every pod from a node on the {env} EU cluster ahead of maintenance.", {"node": NODE}, ["node"], risk=HIGH,
                destructive=True, capability="node-maintenance", resource="kubernetes-node", group="node-maintenance", handler=WRITE),
    ]


OPERATIONAL_SERVERS: list[dict[str, Any]] = [
    {
        "key": "logstream", "family": "vendor-duplicate", "domain": "observability", "owner": "sre-tooling", "lifecycle": "active",
        "notes": "Secondary log analytics platform. Ingestion lag ~15 minutes; not the system of record for application logs.",
        "tools": [
            op_tool("search_logs", "Search log events indexed in LogStream across every service and environment. Supports free-text "
                    "queries, severity filters and lookback windows.", {"service": SERVICE, "environment": ENVIRONMENT, "query": Q,
                    "severity": {"type": "string", "enum": ["debug", "info", "warn", "error"]}, "time_range": TIME_RANGE}, ["service"],
                    capability="log-search", resource="application-logs", group="logs", handler=mirror("observability.search_logs", "environment=production")),
            op_tool("query_logs", "Run an LSQL query over log events in LogStream and return aggregated rows, e.g. "
                    "'service:checkout-api level:error | count by message'.", {"query": {"type": "string", "description": "LSQL query."},
                    "time_range": TIME_RANGE}, ["query"], capability="log-search", resource="application-logs", group="logs", handler="generated:logs_query"),
            op_tool("find_logs", "Find log lines containing a phrase for a service.", {"service": SERVICE, "phrase": {"type": "string"},
                    "time_range": TIME_RANGE}, ["service", "phrase"], capability="log-search", resource="application-logs", group="logs",
                    handler=mirror("observability.search_logs", "phrase>query,environment=production")),
            op_tool("tail_logs", "Return the most recent log lines for a service as they arrive in LogStream.", {"service": SERVICE,
                    "environment": ENVIRONMENT}, ["service"], capability="log-search", resource="application-logs", group="logs",
                    handler=mirror("observability.search_logs", "time_range=5m")),
            op_tool("search_application_logs", "Search structured application logs for a service with field filters such as route, "
                    "status code or trace ID.", {"service": SERVICE, "environment": ENVIRONMENT, "query": Q, "time_range": TIME_RANGE},
                    ["service", "environment"], capability="log-search", resource="application-logs", group="logs", handler=mirror("observability.search_logs")),
            op_tool("get_log_patterns", "Cluster similar log messages for a service and return the most frequent patterns.",
                    {"service": SERVICE, "environment": ENVIRONMENT, "time_range": TIME_RANGE}, ["service"], capability="log-search",
                    resource="application-logs", group="logs", handler=mirror("observability.search_logs", "environment=production")),
            op_tool("count_log_events", "Count log events matching a query, bucketed per minute.", {"service": SERVICE, "query": Q,
                    "time_range": TIME_RANGE}, ["service"], capability="log-search", resource="application-logs", group="logs",
                    handler=mirror("observability.search_logs", "environment=production")),
            op_tool("run_saved_search", "Execute a saved LogStream search by name.", {"name": {"type": "string"}}, ["name"],
                    capability="log-search", resource="saved-search", group="logs", handler="generated:record|saved-search"),
            op_tool("export_logs", "Export matching log events to object storage as NDJSON.", {"query": Q, "time_range": TIME_RANGE,
                    "destination": {"type": "string"}}, ["query", "destination"], risk=LOW, capability="log-export",
                    resource="log-export", group=None, handler=WRITE),
            op_tool("create_log_alert", "Create an alert that fires when a LogStream query matches more than a threshold.",
                    {"query": Q, "threshold": {"type": "integer"}, "notify": {"type": "string"}}, ["query", "threshold"], risk=LOW,
                    capability="alert-authoring", resource="log-alert", group="alerts", handler=WRITE),
        ],
    },
    {
        "key": "apm", "family": "vendor-duplicate", "domain": "observability", "owner": "apm-team", "lifecycle": "active",
        "notes": "APM agent data; 10% of traces are sampled.",
        "tools": [
            op_tool("get_trace", "Get an APM trace by ID with its span waterfall.", {"trace_id": {"type": "string"}}, ["trace_id"],
                    capability="trace-lookup", resource="distributed-trace", group="traces", handler=mirror("observability.get_trace")),
            op_tool("find_traces", "Find sampled APM traces for a service, filtered by minimum duration.", {"service": SERVICE,
                    "environment": ENVIRONMENT, "min_duration_ms": {"type": "integer"}}, ["service"], capability="trace-search",
                    resource="distributed-trace", group="traces", handler=mirror("observability.search_traces", "environment=production")),
            op_tool("get_error_traces", "List sampled traces that ended in an error for a service.", {"service": SERVICE,
                    "environment": ENVIRONMENT}, ["service"], capability="trace-search", resource="distributed-trace", group="traces",
                    handler=mirror("observability.search_traces", "min_duration_ms=2000")),
            op_tool("query_apm_latency", "Query APM-measured latency percentiles for a service.", {"service": SERVICE, "environment": ENVIRONMENT,
                    "percentile": {"type": "string", "enum": ["p50", "p95", "p99"]}}, ["service", "percentile"], capability="latency-query",
                    resource="service-latency", group="latency", handler=mirror("observability.query_latency", "environment=production")),
            op_tool("get_endpoint_latency", "Get latency for each HTTP endpoint of a service over the last hour.", {"service": SERVICE,
                    "environment": ENVIRONMENT}, ["service", "environment"], capability="latency-query", resource="service-latency",
                    group="latency", handler=mirror("observability.query_latency", "percentile=p95,time_range=1h")),
            op_tool("query_throughput", "Get request throughput (requests per second) for a service.", {"service": SERVICE,
                    "environment": ENVIRONMENT, "time_range": TIME_RANGE}, ["service", "environment"], capability="metrics-query",
                    resource="service-metric", group="metrics", handler=mirror("observability.query_metrics", "metric=requests_per_second")),
            op_tool("get_service_overview", "Get the APM overview of a service: Apdex, latency, error rate and throughput.",
                    {"service": SERVICE, "environment": ENVIRONMENT}, ["service", "environment"], capability="service-health",
                    resource="application-service", group="service-health", handler=mirror("observability.get_service_health")),
            op_tool("get_service_map", "Get the APM service map: upstream and downstream dependencies of a service.",
                    {"service": SERVICE}, ["service"], capability="dependency-map", resource="service-dependency", group="ownership",
                    handler=mirror("cmdb.get_dependencies")),
            op_tool("compare_deployments", "Compare a service's latency and error rate in the 15 minutes before and after its most recent "
                    "deployment.", {"service": SERVICE, "environment": ENVIRONMENT}, ["service", "environment"],
                    capability="deployment-impact", resource="service-deployment", group="deployment-lookup", handler="generated:compare_deployments",
                    authoritative=True),
            op_tool("get_span", "Get a single span by trace ID and span ID.", {"trace_id": {"type": "string"}, "span_id": {"type": "string"}},
                    ["trace_id", "span_id"], capability="trace-lookup", resource="distributed-trace", group="traces", handler="generated:record|span"),
        ],
    },
    {
        "key": "legacy_monitoring", "family": "legacy", "domain": "observability", "owner": "observability-platform",
        "lifecycle": "deprecated", "notes": "Scheduled for removal; replaced by observability-mcp.",
        "tools": [
            op_tool("get_metric", "Get a metric value for a service.", {"service": SERVICE, "metric": {"type": "string"}}, ["service", "metric"],
                    capability="metrics-query", resource="service-metric", group="metrics",
                    handler=deprecated("observability.query_metrics", "environment=production,metric=latency_p95_ms")),
            op_tool("query_metric_v1", "Query metric data (v1 API).", {"service": SERVICE, "metric": {"type": "string"}, "environment": ENVIRONMENT},
                    ["service", "metric"], capability="metrics-query", resource="service-metric", group="metrics",
                    handler=deprecated("observability.query_metrics", "metric=latency_p95_ms")),
            op_tool("get_host_status", "Get the status of a monitored host.", {"host": {"type": "string"}}, ["host"],
                    capability="host-status", resource="host", group="service-health", handler="generated:record|host"),
            op_tool("get_service_status", "Get the monitoring status of a service (OK, WARNING, CRITICAL).", {"service": SERVICE,
                    "environment": ENVIRONMENT}, ["service"], capability="service-health", resource="application-service", group="service-health",
                    handler=deprecated("observability.get_service_health", "environment=production")),
            op_tool("get_latency_report", "Get a latency report for a service.", {"service": SERVICE, "environment": ENVIRONMENT},
                    ["service"], capability="latency-query", resource="service-latency", group="latency",
                    handler=deprecated("observability.query_latency", "environment=production,percentile=p95")),
            op_tool("list_checks", "List monitoring checks configured for a service.", {"service": SERVICE}, ["service"],
                    capability="check-config", resource="monitoring-check", group="alerts", handler="generated:record|monitoring-check"),
            op_tool("ack_alert", "Acknowledge an alert.", {"alert_id": {"type": "string"}}, ["alert_id"], risk=LOW,
                    capability="alert-ack", resource="monitoring-alert", group="alerts", handler=WRITE),
            op_tool("silence_alert", "Silence notifications for an alert for a period.", {"alert_id": {"type": "string"},
                    "minutes": {"type": "integer"}}, ["alert_id", "minutes"], risk=LOW, capability="alert-silence",
                    resource="monitoring-alert", group="alerts", handler=WRITE),
        ],
    },
    {
        "key": "cicd", "family": "adjacent-ops", "domain": "delivery", "owner": "build-infrastructure", "lifecycle": "active",
        "notes": "Build and pipeline system. Service releases and rollbacks are owned by the release pipeline (source-control-mcp).",
        "tools": [
            op_tool("get_pipeline_run", "Get a CI/CD pipeline run with its stages, status and duration.", {"run_id": {"type": "string"}},
                    ["run_id"], capability="pipeline-read", resource="pipeline-run", group="pipeline", handler="generated:record|pipeline-run", authoritative=True),
            op_tool("list_pipeline_runs", "List recent pipeline runs for a service, including deploy stages.", {"service": SERVICE,
                    "limit": {"type": "integer"}}, ["service"], capability="pipeline-read", resource="pipeline-run", group="deployment-lookup",
                    handler="generated:record|pipeline-run", authoritative=True),
            op_tool("get_build", "Get a build by number: commit, test results and produced artifacts.", {"build_number": {"type": "integer"}},
                    ["build_number"], capability="pipeline-read", resource="build", group="pipeline", handler="generated:record|build", authoritative=True),
            op_tool("get_artifact", "Get a built container image or package by name and version.", {"name": {"type": "string"}, "version": VERSION},
                    ["name", "version"], capability="artifact-read", resource="artifact", group="pipeline", handler="generated:record|artifact", authoritative=True),
            op_tool("get_deploy_status", "Get the deploy status of a service per environment as seen by the pipeline.", {"service": SERVICE},
                    ["service"], capability="deployment-history", resource="service-deployment", group="deployment-lookup",
                    handler=mirror("source_control.search_deployments", "limit=5")),
            op_tool("trigger_deploy", "Deploy a version of a service to an environment by running its pipeline.", {"service": SERVICE,
                    "environment": DEPLOY_ENV, "version": VERSION}, ["service", "environment", "version"], risk=HIGH,
                    capability="deploy", resource="service-deployment", group="deploy", handler=WRITE),
            op_tool("redeploy_service", "Redeploy the currently deployed version of a service, replacing all instances.", {"service": SERVICE,
                    "environment": DEPLOY_ENV}, ["service", "environment"], risk=HIGH, capability="deploy", resource="service-deployment",
                    group="restart", handler=WRITE),
            op_tool("rollback_pipeline", "Re-run the deploy stage of the previous successful pipeline run for a service.", {"service": SERVICE,
                    "environment": DEPLOY_ENV}, ["service", "environment"], risk=HIGH, capability="deployment-rollback",
                    resource="pipeline-run", group="rollback", handler=WRITE),
            op_tool("cancel_deploy", "Cancel an in-progress deployment.", {"service": SERVICE, "environment": DEPLOY_ENV}, ["service", "environment"],
                    risk=HIGH, capability="deploy", resource="service-deployment", group="deploy", handler=WRITE),
            op_tool("promote_release", "Promote a release from staging to production.", {"service": SERVICE, "version": VERSION},
                    ["service", "version"], risk=HIGH, capability="deploy", resource="service-release", group="deploy", handler=WRITE),
        ],
    },
    {
        "key": "servicedesk_v1", "family": "legacy", "domain": "itsm", "owner": "it-service-management", "lifecycle": "deprecated",
        "notes": "ServiceDesk v1 API; read-only mirror of the ITSM system, retired at year end.",
        "tools": [
            op_tool("find_incident", "Find an incident by its number.", {"number": INCIDENT_NUMBER}, ["number"], capability="incident-read",
                    resource="incident", group="incident-lookup", handler=deprecated("itsm.get_incident", "number>incident_id")),
            op_tool("query_incidents", "Query incidents by text.", {"text": {"type": "string"}}, ["text"], capability="incident-search",
                    resource="incident", group="incident-lookup", handler=deprecated("itsm.search_incidents", "text>query")),
            op_tool("get_incident_details", "Get full details for an incident including work notes.", {"number": INCIDENT_NUMBER}, ["number"],
                    capability="incident-read", resource="incident", group="incident-lookup", handler=deprecated("itsm.get_incident", "number>incident_id")),
            op_tool("update_ticket", "Update an incident ticket's state or notes.", {"number": INCIDENT_NUMBER, "state": {"type": "string"},
                    "notes": {"type": "string"}}, ["number"], risk=LOW, capability="incident-update", resource="incident",
                    group="incident-update", handler=WRITE),
            op_tool("add_ticket_note", "Add a note to a ticket.", {"number": INCIDENT_NUMBER, "note": {"type": "string"}}, ["number", "note"],
                    risk=LOW, capability="incident-comment", resource="incident", group="incident-update", handler=WRITE),
            op_tool("create_ticket", "Create a new incident ticket.", {"short_description": {"type": "string"}, "service": SERVICE},
                    ["short_description"], risk=LOW, capability="incident-create", resource="incident", group="incident-update", handler=WRITE),
            op_tool("resolve_ticket", "Resolve a ticket with a resolution note.", {"number": INCIDENT_NUMBER, "note": {"type": "string"}},
                    ["number"], risk=LOW, capability="incident-close", resource="incident", group="incident-update", handler=WRITE),
        ],
    },
    {"key": "k8s_prod_eu", "family": "legacy", "domain": "runtime", "owner": "platform-engineering", "lifecycle": "deprecated",
     "environments": ["production"], "notes": "Per-cluster server from before kubernetes-mcp; replaced by kubernetes-mcp.",
     "tools": _k8s_cluster("production")},
    {"key": "k8s_staging_eu", "family": "per-cluster", "domain": "runtime", "owner": "platform-engineering", "lifecycle": "active",
     "environments": ["staging"], "notes": "Staging EU cluster only.", "tools": _k8s_cluster("staging")},
    {"key": "k8s_dev_eu", "family": "per-cluster", "domain": "runtime", "owner": "platform-engineering", "lifecycle": "active",
     "environments": ["development"], "notes": "Development EU cluster only.", "tools": _k8s_cluster("development")},
    {
        "key": "cloud_ops", "family": "adjacent-ops", "domain": "cloud", "owner": "cloud-infrastructure", "lifecycle": "active",
        "notes": "Operations scripts for the shared cloud account.",
        "tools": [
            op_tool("restart_service", "Restart a managed service by cycling all instances and tasks behind it.", {"service": SERVICE,
                    "environment": ENVIRONMENT}, ["service", "environment"], risk=HIGH, capability="compute-restart", resource="managed-service",
                    group="restart", handler=WRITE, read_only_hint=True),
            op_tool("reboot_vm", "Reboot a virtual machine.", {"instance_id": INSTANCE}, ["instance_id"], risk=HIGH,
                    capability="compute-restart", resource="vm-instance", group="restart", handler=WRITE),
            op_tool("stop_instance", "Stop a running instance; its disks are kept.", {"instance_id": INSTANCE}, ["instance_id"], risk=HIGH,
                    capability="compute-stop", resource="vm-instance", group="terminate", handler=WRITE),
            op_tool("start_instance", "Start a stopped instance.", {"instance_id": INSTANCE}, ["instance_id"], risk=LOW,
                    capability="compute-start", resource="vm-instance", group=None, handler=WRITE),
            op_tool("terminate_instance", "Terminate an instance and release its resources.", {"instance_id": INSTANCE}, ["instance_id"],
                    risk=HIGH, destructive=True, capability="compute-terminate", resource="vm-instance", group="terminate", handler=WRITE,
                    read_only_hint=False),
            op_tool("describe_instance", "Describe an instance's state and configuration.", {"instance_id": INSTANCE}, ["instance_id"],
                    capability="infra-read", resource="vm-instance", group="infra-read", handler=mirror("cloud.get_instance")),
            op_tool("list_instances", "List instances in the account, filtered by tag.", {"tag": {"type": "string"}}, [],
                    capability="infra-read", resource="vm-instance", group="infra-read", handler="generated:record|vm-instance"),
            op_tool("get_resource_metrics", "Get CPU, memory and connection metrics for a cloud resource.", {"resource_id": {"type": "string"}},
                    ["resource_id"], capability="infra-read", resource="cloud-resource", group="infra-read", handler=mirror("cloud.describe_resource")),
            op_tool("resize_instance", "Change an instance's type; requires a stop and start.", {"instance_id": INSTANCE, "instance_type": {"type": "string"}},
                    ["instance_id", "instance_type"], risk=HIGH, capability="compute-resize", resource="vm-instance", group="scale", handler=WRITE),
            op_tool("snapshot_volume", "Create a snapshot of a block storage volume.", {"volume_id": {"type": "string"}}, ["volume_id"],
                    risk=LOW, capability="storage-backup", resource="block-volume", group=None, handler=WRITE),
            op_tool("delete_volume", "Delete a block storage volume and all its data.", {"volume_id": {"type": "string"}}, ["volume_id"],
                    risk=HIGH, destructive=True, capability="storage-delete", resource="block-volume", group="terminate", handler=WRITE,
                    read_only_hint=True),
            op_tool("get_load_balancer_health", "Get target health for a load balancer.", {"load_balancer": {"type": "string"}},
                    ["load_balancer"], capability="infra-read", resource="load-balancer", group="service-health", handler="generated:record|load-balancer"),
        ],
    },
    {
        "key": "oncall", "family": "adjacent-ops", "domain": "incident-response", "owner": "sre-tooling", "lifecycle": "active",
        "tools": [
            op_tool("get_oncall", "Get who is on call now for a schedule or service.", {"schedule": {"type": "string"}, "service": SERVICE}, [],
                    capability="oncall-read", resource="oncall-schedule", group="ownership", handler="generated:oncall", authoritative=True),
            op_tool("list_schedules", "List on-call schedules.", {}, [], capability="oncall-read", resource="oncall-schedule",
                    group="ownership", handler="generated:oncall", authoritative=True),
            op_tool("page_team", "Page the on-call engineer of a team with a message.", {"schedule": {"type": "string"}, "message": {"type": "string"}},
                    ["schedule", "message"], risk=LOW, capability="paging", resource="page", group="notify", handler=WRITE),
            op_tool("acknowledge_page", "Acknowledge a page.", {"page_id": {"type": "string"}}, ["page_id"], risk=LOW, capability="paging",
                    resource="page", group="notify", handler=WRITE),
            op_tool("escalate_incident", "Escalate an incident to the next on-call level.", {"incident_id": INCIDENT_NUMBER}, ["incident_id"],
                    risk=LOW, capability="paging", resource="incident", group="incident-update", handler=WRITE),
            op_tool("override_shift", "Override an on-call shift with another responder.", {"schedule": {"type": "string"},
                    "responder": {"type": "string"}}, ["schedule", "responder"], risk=LOW, capability="oncall-write", resource="oncall-schedule",
                    group=None, handler=WRITE),
        ],
    },
    {
        "key": "status_page", "family": "adjacent-ops", "domain": "incident-communication", "owner": "customer-communications", "lifecycle": "active",
        "tools": [
            op_tool("list_components", "List public status page components.", {}, [], capability="status-read", resource="status-component",
                    group="service-health", handler="generated:record|status-component", authoritative=True),
            op_tool("get_component_status", "Get the public status of a status page component.", {"component": {"type": "string"}}, ["component"],
                    capability="status-read", resource="status-component", group="service-health", handler="generated:record|status-component",
                    authoritative=True),
            op_tool("update_component_status", "Set a public status page component to operational, degraded or outage.",
                    {"component": {"type": "string"}, "status": {"type": "string", "enum": ["operational", "degraded", "partial_outage", "major_outage"]}},
                    ["component", "status"], risk=HIGH, capability="status-write", resource="status-component", group="customer-comms", handler=WRITE),
            op_tool("create_status_incident", "Publish a customer-facing incident on the public status page.", {"title": {"type": "string"},
                    "message": {"type": "string"}}, ["title", "message"], risk=HIGH, capability="status-write", resource="status-incident",
                    group="customer-comms", handler=WRITE),
            op_tool("post_status_update", "Post an update to a public status page incident.", {"status_incident_id": {"type": "string"},
                    "message": {"type": "string"}}, ["status_incident_id", "message"], risk=HIGH, capability="status-write",
                    resource="status-incident", group="customer-comms", handler=WRITE),
        ],
    },
    {
        "key": "cache", "family": "adjacent-ops", "domain": "database", "owner": "data-platform", "lifecycle": "active",
        "tools": [
            op_tool("list_cache_clusters", "List cache clusters.", {}, [], capability="cache-read", resource="cache-cluster", group="db-read",
                    handler="generated:record|cache-cluster", authoritative=True),
            op_tool("get_cache_stats", "Get hit rate, memory and evictions for a cache cluster.", {"cluster": {"type": "string"}}, ["cluster"],
                    capability="cache-read", resource="cache-cluster", group="db-read", handler="generated:record|cache-cluster", authoritative=True),
            op_tool("get_key", "Read a key from a cache cluster.", {"cluster": {"type": "string"}, "key": {"type": "string"}}, ["cluster", "key"],
                    capability="cache-read", resource="cache-key", group="db-read", handler="generated:record|cache-key", authoritative=True),
            op_tool("evict_keys", "Evict keys matching a pattern from a cache cluster.", {"cluster": {"type": "string"}, "pattern": {"type": "string"}},
                    ["cluster", "pattern"], risk=HIGH, capability="cache-write", resource="cache-key", group="db-write", handler=WRITE),
            op_tool("flush_cache", "Flush every key from a cache cluster.", {"cluster": {"type": "string"}}, ["cluster"], risk=HIGH, destructive=True,
                    capability="cache-write", resource="cache-cluster", group="db-write", handler=WRITE),
        ],
    },
    {
        "key": "runbooks", "family": "adjacent-ops", "domain": "knowledge", "owner": "sre-tooling", "lifecycle": "active",
        "tools": [
            op_tool("search_runbooks", "Search operational runbooks by symptom or service.", {"query": Q}, ["query"], capability="runbook-read",
                    resource="runbook", group="knowledge", handler="generated:runbook", authoritative=True),
            op_tool("get_runbook", "Get a runbook's steps by ID, e.g. RB-CHK-007.", {"runbook_id": {"type": "string"}}, ["runbook_id"],
                    capability="runbook-read", resource="runbook", group="knowledge", handler="generated:runbook", authoritative=True),
            op_tool("search_postmortems", "Search post-incident reviews by text.", {"query": Q}, ["query"], capability="postmortem-read",
                    resource="postmortem", group="knowledge", handler="generated:postmortem", authoritative=True),
            op_tool("get_postmortem", "Get a post-incident review by ID.", {"postmortem_id": {"type": "string"}}, ["postmortem_id"],
                    capability="postmortem-read", resource="postmortem", group="knowledge", handler="generated:postmortem", authoritative=True),
        ],
    },
    {
        "key": "security", "family": "adjacent-ops", "domain": "security", "owner": "security-engineering", "lifecycle": "active",
        "tools": [
            op_tool("get_vulnerabilities", "List open vulnerabilities for a service's container images.", {"service": SERVICE}, ["service"],
                    capability="vuln-read", resource="vulnerability", group=None, handler="generated:record|vulnerability", authoritative=True),
            op_tool("get_audit_events", "Search security audit events by actor, action or resource.", {"query": Q, "time_range": TIME_RANGE}, [],
                    capability="audit-read", resource="audit-event", group=None, handler="generated:record|audit-event", authoritative=True),
            op_tool("list_secrets", "List secret names (not values) used by a service.", {"service": SERVICE}, ["service"],
                    capability="secret-read", resource="secret", group=None, handler="generated:record|secret", authoritative=True),
            op_tool("get_waf_events", "Get web application firewall block events for a hostname.", {"hostname": {"type": "string"},
                    "time_range": TIME_RANGE}, ["hostname"], capability="waf-read", resource="waf-event", group=None,
                    handler="generated:record|waf-event", authoritative=True),
            op_tool("rotate_secret", "Rotate a secret and roll the new value out to consumers.", {"secret": {"type": "string"}}, ["secret"],
                    risk=HIGH, capability="secret-write", resource="secret", group=None, handler=WRITE),
            op_tool("revoke_token", "Revoke an API token immediately.", {"token_id": {"type": "string"}}, ["token_id"], risk=HIGH,
                    capability="token-revoke", resource="api-token", group=None, handler=WRITE),
        ],
    },
    {
        "key": "data_warehouse", "family": "adjacent-ops", "domain": "analytics", "owner": "data-platform", "lifecycle": "active",
        "tools": [
            op_tool("list_tables", "List tables in a warehouse dataset.", {"dataset": {"type": "string"}}, ["dataset"], capability="warehouse-read",
                    resource="warehouse-table", group=None, handler="generated:record|warehouse-table", authoritative=True),
            op_tool("get_table_schema", "Get a warehouse table's columns and types.", {"table": {"type": "string"}}, ["table"],
                    capability="warehouse-read", resource="warehouse-table", group=None, handler="generated:record|warehouse-table", authoritative=True),
            op_tool("query_table", "Run a read-only SQL query against the analytics warehouse.", {"sql": {"type": "string"}}, ["sql"],
                    capability="warehouse-read", resource="warehouse-query", group=None, handler="generated:record|warehouse-query", authoritative=True),
            op_tool("run_report", "Run a saved analytics report, e.g. daily checkout conversion.", {"report": {"type": "string"}}, ["report"],
                    capability="warehouse-read", resource="warehouse-report", group=None, handler="generated:record|warehouse-report", authoritative=True),
        ],
    },
    {
        "key": "db_admin", "family": "adjacent-ops", "domain": "database", "owner": "dba-team", "lifecycle": "active",
        "notes": "DBA tooling talking directly to database engines.",
        "tools": [
            op_tool("get_db_connections", "Get connection counts per client application from the database engine.", {"database_id": {"type": "string"}},
                    ["database_id"], capability="db-read", resource="database-session", group="db-read", handler=mirror("cloud.describe_resource", "database_id>resource_id")),
            op_tool("show_processlist", "Show currently running database sessions and their queries.", {"database_id": {"type": "string"}},
                    ["database_id"], capability="db-read", resource="database-session", group="db-read", handler="generated:record|database-session"),
            op_tool("get_replication_lag", "Get replica lag for a database cluster.", {"database_id": {"type": "string"}}, ["database_id"],
                    capability="db-read", resource="database-cluster", group="db-read", handler=mirror("cloud.describe_resource", "database_id>resource_id")),
            op_tool("get_pool_config", "Get the configured connection-pool size for a service's database client.", {"service": SERVICE,
                    "environment": ENVIRONMENT}, ["service", "environment"], capability="db-read", resource="connection-pool", group="db-read",
                    handler=mirror("database.get_connection_pool_stats")),
            op_tool("set_pool_size", "Change the maximum connection-pool size of a service's database client at runtime.", {"service": SERVICE,
                    "environment": ENVIRONMENT, "max_connections": {"type": "integer", "minimum": 1, "maximum": 500}},
                    ["service", "environment", "max_connections"], risk=HIGH, capability="db-config-write", resource="connection-pool",
                    group="db-write", handler=WRITE),
            op_tool("kill_query", "Cancel a running query by process ID.", {"database_id": {"type": "string"}, "pid": {"type": "integer"}},
                    ["database_id", "pid"], risk=HIGH, capability="db-admin", resource="database-session", group="db-write", handler=WRITE),
            op_tool("restart_database", "Restart a database engine. All connections are dropped.", {"database_id": {"type": "string"}},
                    ["database_id"], risk=HIGH, destructive=True, capability="db-admin", resource="database-cluster", group="restart", handler=WRITE),
        ],
    },
    {
        "key": "flags_legacy", "family": "legacy", "domain": "feature-flags", "owner": "developer-platform", "lifecycle": "deprecated",
        "notes": "Old toggle service; replaced by feature-flags-mcp.",
        "tools": [
            op_tool("get_toggle", "Get a feature toggle.", {"name": {"type": "string"}, "environment": ENVIRONMENT}, ["name"],
                    capability="flag-read", resource="feature-flag", group="flags-read", handler=deprecated("feature_flags.get_flag", "name>key,environment=production")),
            op_tool("list_toggles", "List feature toggles and recent changes.", {"environment": ENVIRONMENT}, [], capability="flag-read",
                    resource="feature-flag", group="flags-read", handler=deprecated("feature_flags.list_flag_changes")),
            op_tool("toggle_flag", "Flip a feature toggle on or off.", {"name": {"type": "string"}, "environment": ENVIRONMENT, "on": {"type": "boolean"}},
                    ["name", "environment", "on"], risk=HIGH, capability="flag-write", resource="feature-flag", group="flags-write", handler=WRITE),
        ],
    },
    {
        "key": "ops_debug", "family": "shadow", "domain": "runtime", "owner": None, "lifecycle": "shadow", "registered": False,
        "notes": "Team-run debugging server connected to the agent without registration.",
        "tools": [
            op_tool("exec_command", "Run a shell command on a production host and return its output.", {"host": {"type": "string"},
                    "command": {"type": "string"}}, ["host", "command"], risk=HIGH, capability="host-exec", resource="host", group="exec", handler=WRITE),
            op_tool("kubectl_exec", "Run any kubectl command against a cluster.", {"cluster": {"type": "string"}, "args": {"type": "string"}},
                    ["cluster", "args"], risk=HIGH, capability="cluster-exec", resource="kubernetes-cluster", group="exec", handler=WRITE),
            op_tool("run_sql", "Run a SQL statement against a production database.", {"database_id": {"type": "string"}, "sql": {"type": "string"}},
                    ["database_id", "sql"], risk=HIGH, capability="db-exec", resource="database", group="db-write", handler=WRITE),
            op_tool("restart_service", "Restart a service quickly without going through change management.", {"service": SERVICE},
                    ["service"], risk=HIGH, capability="compute-restart", resource="application-service", group="restart", handler=WRITE),
            op_tool("tail_logs", "Tail logs for a service from the debug sidecar.", {"service": SERVICE}, ["service"], capability="log-search",
                    resource="application-logs", group="logs", handler=mirror("observability.search_logs", "environment=production,time_range=5m")),
        ],
    },
    {
        "key": "network", "family": "adjacent-ops", "domain": "network", "owner": "network-engineering", "lifecycle": "active",
        "tools": [
            op_tool("get_dns_record", "Get a DNS record.", {"name": {"type": "string"}}, ["name"], capability="dns-read", resource="dns-record",
                    group=None, handler="generated:record|dns-record", authoritative=True),
            op_tool("update_dns_record", "Change the target of a DNS record.", {"name": {"type": "string"}, "target": {"type": "string"}},
                    ["name", "target"], risk=HIGH, capability="dns-write", resource="dns-record", group=None, handler=WRITE),
            op_tool("get_load_balancer", "Get a load balancer's listeners and target groups.", {"name": {"type": "string"}}, ["name"],
                    capability="lb-read", resource="load-balancer", group="infra-read", handler="generated:record|load-balancer", authoritative=True),
            op_tool("drain_target", "Drain a target from a load balancer target group.", {"target_group": {"type": "string"}, "target": {"type": "string"}},
                    ["target_group", "target"], risk=HIGH, capability="lb-write", resource="load-balancer", group=None, handler=WRITE),
            op_tool("get_certificate", "Get TLS certificate details and expiry for a hostname.", {"hostname": {"type": "string"}}, ["hostname"],
                    capability="cert-read", resource="certificate", group=None, handler="generated:record|certificate", authoritative=True),
            op_tool("get_cdn_status", "Get CDN cache hit rate and origin errors for a hostname.", {"hostname": {"type": "string"}}, ["hostname"],
                    capability="cdn-read", resource="cdn-distribution", group="service-health", handler="generated:record|cdn-distribution", authoritative=True),
            op_tool("purge_cdn_cache", "Purge cached objects for a hostname from the CDN.", {"hostname": {"type": "string"}, "path": {"type": "string"}},
                    ["hostname"], risk=HIGH, capability="cdn-write", resource="cdn-distribution", group=None, handler=WRITE),
        ],
    },
    {
        "key": "synthetics", "family": "adjacent-ops", "domain": "observability", "owner": "sre-tooling", "lifecycle": "active",
        "tools": [
            op_tool("run_synthetic_check", "Run a synthetic browser journey now, e.g. 'checkout happy path'.", {"check": {"type": "string"}},
                    ["check"], risk=LOW, capability="synthetic-run", resource="synthetic-check", group=None, handler=WRITE),
            op_tool("get_synthetic_results", "Get recent results and step durations of a synthetic journey.", {"check": {"type": "string"},
                    "time_range": TIME_RANGE}, ["check"], capability="synthetic-read", resource="synthetic-check", group="latency",
                    handler="generated:record|synthetic-result", authoritative=True),
            op_tool("get_uptime", "Get external uptime percentage for a public endpoint.", {"endpoint": {"type": "string"}}, ["endpoint"],
                    capability="synthetic-read", resource="synthetic-check", group="service-health", handler="generated:record|uptime", authoritative=True),
        ],
    },
    {
        "key": "cost", "family": "adjacent-ops", "domain": "finops", "owner": "cloud-finops", "lifecycle": "active",
        "tools": [
            op_tool("get_cost_report", "Get cloud cost by service and day.", {"service": SERVICE, "month": {"type": "string"}}, ["month"],
                    capability="cost-read", resource="cost-report", group=None, handler="generated:record|cost-report", authoritative=True),
            op_tool("get_budget_alerts", "List budget alerts that have fired this month.", {}, [], capability="cost-read", resource="budget",
                    group=None, handler="generated:record|budget", authoritative=True),
        ],
    },
]

# --------------------------------------------------------------------------------------------------
# Business domains: resources x actions, plus a few domain-specific actions
# --------------------------------------------------------------------------------------------------
BUSINESS_DOMAINS: list[dict[str, Any]] = [
    {"key": "hr", "system": "the HR information system", "owner": "people-systems", "resources": [
        ("employee", "employee_id", ["department", "manager_id", "location", "job_title"]),
        ("time_off_request", "request_id", ["employee_id", "start_date", "end_date", "type"]),
        ("job_requisition", "requisition_id", ["department", "title", "hiring_manager", "status"]),
        ("performance_review", "review_id", ["employee_id", "cycle", "rating", "status"])],
     "extras": [("approve_time_off_request", LOW, "Approve a pending time-off request.", ["request_id"]),
                ("export_employee_directory", READ, "Export the employee directory as CSV.", ["department"])]},
    {"key": "payroll", "system": "the payroll platform", "owner": "payroll-operations", "resources": [
        ("pay_run", "pay_run_id", ["period", "entity", "status"]),
        ("payslip", "payslip_id", ["employee_id", "period"]),
        ("tax_form", "form_id", ["employee_id", "tax_year", "form_type"]),
        ("compensation_change", "change_id", ["employee_id", "effective_date", "amount"])],
     "extras": [("approve_pay_run", HIGH, "Approve a pay run for payment.", ["pay_run_id"])]},
    {"key": "finance", "system": "the ERP general ledger", "owner": "finance-systems", "resources": [
        ("invoice", "invoice_id", ["customer_id", "amount", "currency", "due_date", "status"]),
        ("expense_report", "report_id", ["employee_id", "total", "status"]),
        ("purchase_order", "po_number", ["supplier_id", "amount", "status"]),
        ("journal_entry", "entry_id", ["account", "amount", "period"])],
     "extras": [("approve_expense_report", LOW, "Approve a submitted expense report.", ["report_id"]),
                ("pay_invoice", HIGH, "Schedule payment of an approved supplier invoice.", ["invoice_id"])]},
    {"key": "procurement", "system": "the procurement suite", "owner": "procurement-ops", "resources": [
        ("supplier", "supplier_id", ["name", "category", "country", "risk_rating"]),
        ("contract", "contract_id", ["supplier_id", "value", "end_date", "status"]),
        ("rfq", "rfq_id", ["category", "due_date", "status"]),
        ("catalog_item", "item_id", ["name", "supplier_id", "unit_price"])],
     "extras": [("award_rfq", HIGH, "Award a request for quotation to a supplier.", ["rfq_id", "supplier_id"])]},
    {"key": "legal", "system": "the legal matter management system", "owner": "legal-ops", "resources": [
        ("matter", "matter_id", ["title", "practice_area", "status"]),
        ("nda", "nda_id", ["counterparty", "effective_date", "status"]),
        ("contract_review", "review_id", ["contract_id", "reviewer", "status"]),
        ("policy_document", "document_id", ["title", "owner", "version"])],
     "extras": [("sign_nda", HIGH, "Countersign an NDA on behalf of the company.", ["nda_id"])]},
    {"key": "crm", "system": "the CRM", "owner": "revenue-operations", "resources": [
        ("account", "account_id", ["name", "industry", "owner", "region"]),
        ("contact", "contact_id", ["account_id", "email", "title"]),
        ("opportunity", "opportunity_id", ["account_id", "stage", "amount", "close_date"]),
        ("support_case", "case_id", ["account_id", "priority", "status", "subject"])],
     "extras": [("merge_accounts", HIGH, "Merge two duplicate customer accounts into one.", ["account_id", "duplicate_account_id"]),
                ("escalate_support_case", LOW, "Escalate a customer support case to tier-2 support.", ["case_id"])]},
    {"key": "marketing", "system": "the marketing automation platform", "owner": "marketing-ops", "resources": [
        ("campaign", "campaign_id", ["name", "channel", "budget", "status"]),
        ("email_list", "list_id", ["name", "subscriber_count"]),
        ("landing_page", "page_id", ["title", "url", "status"]),
        ("ad_budget", "budget_id", ["channel", "month", "amount"])],
     "extras": [("launch_campaign", HIGH, "Launch a scheduled marketing campaign.", ["campaign_id"]),
                ("pause_campaign", LOW, "Pause a running marketing campaign.", ["campaign_id"])]},
    {"key": "customer_support", "system": "the customer support desk", "owner": "support-operations", "resources": [
        ("ticket", "ticket_id", ["customer_email", "priority", "status", "subject"]),
        ("macro", "macro_id", ["title", "category"]),
        ("satisfaction_survey", "survey_id", ["ticket_id", "score"]),
        ("knowledge_article", "article_id", ["title", "locale", "status"])],
     "extras": [("assign_ticket", LOW, "Assign a customer ticket to an agent or group.", ["ticket_id", "assignee"]),
                ("merge_tickets", LOW, "Merge duplicate customer tickets.", ["ticket_id", "duplicate_ticket_id"])]},
    {"key": "product_analytics", "system": "the product analytics platform", "owner": "product-analytics", "resources": [
        ("funnel_report", "funnel_id", ["name", "steps", "date_range"]),
        ("cohort", "cohort_id", ["name", "definition"]),
        ("event_definition", "event_name", ["description", "owner"]),
        ("experiment", "experiment_id", ["name", "status", "primary_metric"])],
     "extras": [("run_funnel_report", READ, "Run a conversion funnel report, e.g. cart to checkout to payment.", ["funnel_id"])]},
    {"key": "ecommerce_catalog", "system": "the product catalogue", "owner": "merchandising", "resources": [
        ("product", "sku", ["title", "category", "status"]),
        ("price_rule", "rule_id", ["sku", "price", "currency", "starts_at"]),
        ("promotion", "promotion_id", ["code", "discount_pct", "ends_at"]),
        ("inventory_item", "sku_location", ["sku", "warehouse", "quantity"])],
     "extras": [("publish_product", LOW, "Publish a product so it is visible in the storefront.", ["sku"])]},
    {"key": "order_management", "system": "the order management system", "owner": "order-operations", "resources": [
        ("customer_order", "order_id", ["customer_id", "status", "total"]),
        ("refund", "refund_id", ["order_id", "amount", "reason"]),
        ("shipment", "shipment_id", ["order_id", "carrier", "status"]),
        ("return_request", "return_id", ["order_id", "reason", "status"])],
     "extras": [("reship_order", LOW, "Create a replacement shipment for an order.", ["order_id"])]},
    {"key": "facilities", "system": "the workplace management system", "owner": "workplace-services", "resources": [
        ("desk_booking", "booking_id", ["site", "date", "employee_id"]),
        ("meeting_room", "room_id", ["site", "capacity"]),
        ("visitor_pass", "pass_id", ["visitor_name", "host_id", "date"]),
        ("maintenance_request", "request_id", ["site", "category", "status"])],
     "extras": [("check_in_visitor", LOW, "Check a visitor in at reception.", ["pass_id"])]},
    {"key": "learning", "system": "the learning management system", "owner": "people-development", "resources": [
        ("course", "course_id", ["title", "category", "duration_hours"]),
        ("enrollment", "enrollment_id", ["course_id", "employee_id", "status"]),
        ("certification", "certification_id", ["employee_id", "name", "expires_at"]),
        ("learning_path", "path_id", ["title", "audience"])],
     "extras": [("assign_course", LOW, "Assign a course to an employee with a due date.", ["course_id", "employee_id"])]},
    {"key": "it_assets", "system": "the IT asset management system", "owner": "it-operations", "resources": [
        ("laptop", "asset_tag", ["assigned_to", "model", "status"]),
        ("software_license", "license_id", ["product", "seats", "expires_at"]),
        ("access_request", "request_id", ["employee_id", "system", "role", "status"]),
        ("mobile_device", "device_id", ["assigned_to", "platform", "status"])],
     "extras": [("grant_access", HIGH, "Grant a role in a business system to an employee.", ["employee_id", "system", "role"]),
                ("revoke_access", HIGH, "Revoke an employee's role in a business system.", ["employee_id", "system", "role"])]},
]

NEAR_MISS_RESOURCES = {"support_case", "ticket", "funnel_report", "customer_order", "inventory_item", "maintenance_request", "access_request"}


def _plural(word: str) -> str:
    if word.endswith("y") and not word.endswith("ey"):
        return word[:-1] + "ies"
    if word.endswith(("s", "sh", "ch")):
        return word + "es"
    return word + "s"


def _label(resource: str) -> str:
    return resource.replace("_", " ").replace("rfq", "RFQ").replace("nda", "NDA")


def business_tools(domain: dict[str, Any]) -> list[dict[str, Any]]:
    key, system = domain["key"], domain["system"]
    tools = []
    for resource, id_field, fields in domain["resources"]:
        label = _label(resource)
        str_props = {f: {"type": "string"} for f in fields}
        common = dict(capability=f"{key}-{resource}", resource=resource.replace("_", "-"), group=None)
        near = resource in NEAR_MISS_RESOURCES
        tools += [
            op_tool(f"get_{resource}", f"Get a {label} by ID from {system}, including {', '.join(f.replace('_', ' ') for f in fields[:3])}.",
                    {id_field: {"type": "string"}}, [id_field], handler=f"generated:record|{resource}", **common | {"group": "near-miss" if near else None}),
            op_tool(f"search_{_plural(resource)}", f"Search {_plural(label)} in {system} by {' or '.join(f.replace('_', ' ') for f in fields[:2])}. "
                    "Returns matching records, newest first.", {"query": Q, **{f: {"type": "string"} for f in fields[:2]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, [], handler=f"generated:record|{resource}",
                    **common | {"group": "near-miss" if near else None}),
            op_tool(f"create_{resource}", f"Create a new {label} in {system}.", str_props, fields[:2], risk=LOW, handler=WRITE, **common),
            op_tool(f"update_{resource}", f"Update fields on an existing {label} in {system}.", {id_field: {"type": "string"}, **str_props},
                    [id_field], risk=LOW, handler=WRITE, **common),
            op_tool(f"delete_{resource}", f"Delete a {label} from {system}. Deleted records cannot be restored.",
                    {id_field: {"type": "string"}, "reason": {"type": "string"}}, [id_field], risk=HIGH, destructive=True,
                    handler=WRITE, **common),
        ]
    for name, risk, desc, required in domain["extras"]:
        props = {f: {"type": "string"} for f in required}
        tools.append(op_tool(name, desc.rstrip(".") + f" in {system}.", props, required, risk=risk,
                             handler=WRITE if risk != READ else f"generated:record|{key}", capability=f"{key}-{name}",
                             resource=key, group="near-miss" if name in ("escalate_support_case", "run_funnel_report") else None))
    return tools


# --------------------------------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------------------------------
def _scopes(domain: str, risk: str, destructive: bool) -> list[str]:
    suffix = "admin" if destructive else ("read" if risk == READ else "write")
    return [f"{domain}.{suffix}"]


def build_server_tools(server: dict[str, Any], family: str) -> list[ToolSpec]:
    specs = []
    for t in server["tools"]:
        registered = server.get("registered", True)
        lifecycle = server["lifecycle"]
        is_deprecated = lifecycle == "deprecated"
        replaced_by = None
        if is_deprecated and t["handler"].startswith(("generated:mirror", "generated:deprecated")):
            replaced_by = t["handler"].split("|")[1]
        authoritative = t["authoritative"] if t["authoritative"] is not None else False
        registry = None
        if registered:
            registry = registry_record(
                domain=server["domain"], capability=t["capability"], resource_type=t["resource"],
                operations=[t["name"].split("_", 1)[0]], risk=t["risk"], owner=server["owner"],
                scopes=t["scopes"] or _scopes(server["domain"], t["risk"], t["destructive"]),
                environments=server.get("environments", ("production", "staging", "development")),
                authoritative_for=[t["resource"]] if authoritative else [], destructive=t["destructive"],
                deprecated=is_deprecated, replaced_by=replaced_by, lifecycle=lifecycle,
                version="1.0" if not is_deprecated else "0.9", notes=server.get("notes"),
            )
        read_only_hint = t["read_only_hint"] if t["read_only_hint"] is not None else (t["risk"] == READ)
        specs.append(ToolSpec(
            server=server["key"], name=t["name"], description=t["description"],
            input_schema=schema(t["props"], t["required"]), title=t["name"].replace("_", " ").capitalize(),
            read_only_hint=read_only_hint, destructive_hint=t["destructive"] if t["risk"] != READ else None,
            open_world_hint=False, handler=t["handler"], family=family, collision_group=t["group"], registry=registry,
        ))
    return specs


def build_pool(seed: int = SEED) -> dict[str, Any]:
    rng = random.Random(seed)
    core = [replace(CORE_TOOLS[tid], family="core") for tid in CORE_LADDER_ORDER]

    op_servers = [(s["key"], build_server_tools(s, s["family"])) for s in OPERATIONAL_SERVERS]
    biz_servers = [(d["key"], build_server_tools({"key": d["key"], "domain": d["key"].replace("_", "-"), "owner": d["owner"],
                                                   "lifecycle": "active", "environments": ["production"], "tools": business_tools(d)},
                                                  "business")) for d in BUSINESS_DOMAINS]
    n_op = sum(len(t) for _, t in op_servers)
    n_biz = sum(len(t) for _, t in biz_servers)
    if n_op + n_biz != 450:
        raise AssertionError(f"generated tools = {n_op} operational + {n_biz} business = {n_op + n_biz}, expected 450")

    # Ladder order beyond the core: whole servers at a time (enterprises add servers, not single tools),
    # shuffled within each class and interleaved so each prefix keeps roughly the 1:2 op:business mix.
    rng.shuffle(op_servers)
    rng.shuffle(biz_servers)
    order: list[ToolSpec] = []
    taken = {"op": 0, "biz": 0}
    target = {"op": n_op / 450, "biz": n_biz / 450}
    queues = {"op": list(op_servers), "biz": list(biz_servers)}
    while queues["op"] or queues["biz"]:
        total = max(1, taken["op"] + taken["biz"])
        cls = min((c for c in queues if queues[c]), key=lambda c: taken[c] / total - target[c])
        _, tools = queues[cls].pop(0)
        order.extend(tools)
        taken[cls] += len(tools)

    pool = core + order
    ladder = {n: [t.tool_id for t in pool[:n]] for n in LADDER}

    core_groups = {t.collision_group for t in core if t.collision_group}
    generated = order
    low_candidates = [t for t in generated if t.family == "business" and t.server in {"hr", "payroll", "finance", "procurement", "legal", "facilities", "learning"}]
    high_candidates = [t for t in generated if t.family != "business" and t.collision_group in core_groups]
    rng_low, rng_high = random.Random(seed + 1), random.Random(seed + 2)
    low = sorted(rng_low.sample(low_candidates, 50), key=pool.index)
    high = sorted(rng_high.sample(high_candidates, 50), key=pool.index)
    variants = {
        "low_overlap_100": [t.tool_id for t in core] + [t.tool_id for t in low],
        "high_overlap_100": [t.tool_id for t in core] + [t.tool_id for t in high],
    }
    return {"pool": pool, "ladder": ladder, "variants": variants, "core_groups": sorted(core_groups),
            "counts": {"core": len(core), "operational": n_op, "business": n_biz}}


def _manifest(catalog_id: str, tools: Iterable[ToolSpec], seed: int) -> dict[str, Any]:
    tools = list(tools)
    return {"catalog_id": catalog_id, "seed": seed, "tool_count": len(tools),
            "servers": sorted({t.server for t in tools}), "tools": [t.manifest_entry() for t in tools]}


def write_catalogs(out_dir: Path = OUT_DIR, seed: int = SEED) -> dict[str, Any]:
    built = build_pool(seed)
    pool: list[ToolSpec] = built["pool"]
    by_id = {t.tool_id: t for t in pool}
    if len(by_id) != len(pool):
        raise AssertionError("duplicate tool_id in pool")
    out_dir.mkdir(parents=True, exist_ok=True)
    catalogs = {f"catalog_{n}": ids for n, ids in built["ladder"].items()} | built["variants"]
    for name, ids in catalogs.items():
        (out_dir / f"{name}.json").write_text(json.dumps(_manifest(name, (by_id[i] for i in ids), seed), indent=1) + "\n")
    records = []
    for t in pool:
        if t.registry is None:
            continue
        records.append({"tool_id": t.tool_id, "server": t.server, "name": t.name, "exposed_name": t.exposed_name,
                        "description": t.description, "family": t.family, "collision_group": t.collision_group, **t.registry})
    (out_dir / "registry.json").write_text(json.dumps({"seed": seed, "records": records}, indent=1) + "\n")
    summary = {
        "seed": seed,
        "counts": built["counts"] | {"registered": len(records), "unregistered": len(pool) - len(records)},
        "catalogs": {name: len(ids) for name, ids in catalogs.items()},
        "core_collision_groups": built["core_groups"],
        "ladder_composition": {
            name: _composition([by_id[i] for i in ids]) for name, ids in catalogs.items()
        },
    }
    (out_dir / "catalog_summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    return summary


def _composition(tools: list[ToolSpec]) -> dict[str, Any]:
    families: dict[str, int] = {}
    for t in tools:
        families[t.family] = families.get(t.family, 0) + 1
    names: dict[str, int] = {}
    for t in tools:
        names[t.name] = names.get(t.name, 0) + 1
    return {
        "servers": len({t.server for t in tools}),
        "families": families,
        "duplicate_tool_names": sum(1 for c in names.values() if c > 1),
        "tools_sharing_a_name": sum(c for c in names.values() if c > 1),
        "deprecated": sum(1 for t in tools if t.registry and t.registry["deprecated"]),
        "unregistered": sum(1 for t in tools if t.registry is None),
        "write_tools": sum(1 for t in tools if t.registry and not t.registry["read_only"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the deterministic MCP tool catalogs.")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    summary = write_catalogs(args.out, args.seed)
    print(json.dumps({k: summary[k] for k in ("counts", "catalogs")}, indent=1))


if __name__ == "__main__":
    main()
