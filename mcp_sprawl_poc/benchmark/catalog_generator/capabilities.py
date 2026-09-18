"""Builds the declared capability catalog for discovery v5.

    python -m benchmark.catalog_generator.capabilities        # writes benchmark/catalogs/capabilities.json

Every registered tool maps to one capability and one implementation role:

* the 50 core tools are the authoritative implementations of 50 capabilities, mapped by hand below from what each
  tool does (system, resource, action, when to use it and what it is not for);
* generated tools are mapped by rule from the generator's own tags: a per-cluster copy is an environment variant of
  the matching core capability, a mirror of a core tool is a substitute, a deprecated server's tools are legacy, and
  a handful of tools are declared equivalents of core tools;
* everything else is its own capability.

The registry (`registry.json`) is not changed; this file sits next to it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmark.catalog_generator.generator import build_pool
from control_plane.registry.vocabulary import BUSINESS_SYSTEM, DOMAIN_SYSTEM, READ_ACTIONS

CAPABILITIES_FILE = Path(__file__).resolve().parents[1] / "catalogs" / "capabilities.json"

# tool_id: (system, resource, action, use when, not for)
CORE: dict[str, tuple[str, str, str, str, str]] = {
    "itsm.get_incident": ("incident management", "incident", "read",
        "you have an incident number and need its status, severity, owner or timeline",
        "finding incidents without a number; chat history"),
    "itsm.search_incidents": ("incident management", "incident", "search",
        "you need to find incidents by text, service, status or severity",
        "reading one incident you already have the number of"),
    "itsm.update_incident": ("incident management", "incident", "update",
        "changing an incident's fields: status, severity, summary, root cause, resolution notes",
        "adding a note without changing fields; closing an incident; posting in chat"),
    "itsm.add_incident_comment": ("incident management", "incident", "comment",
        "adding a work note or comment to the incident's activity stream",
        "posting a message in a chat channel; changing incident fields"),
    "itsm.close_incident": ("incident management", "incident", "close",
        "closing an incident with a resolution code after recovery is verified",
        "updating fields or status of an open incident"),
    "itsm.create_change": ("incident management", "change request", "create",
        "recording a planned or emergency production change for approval",
        "making the change itself"),
    "observability.query_latency": ("monitoring", "latency", "read",
        "you need latency percentiles (p50, p95, p99) for a service against its SLO",
        "error rates; general metrics; one trace"),
    "observability.query_metrics": ("monitoring", "metric", "read",
        "you need a time series for one application metric such as throughput, CPU, memory or pool wait",
        "a latency percentile report against the SLO; the error rate"),
    "observability.query_error_rate": ("monitoring", "error rate", "read",
        "you need the share of failed requests (5xx and timeouts) for a service",
        "latency; log lines"),
    "observability.get_service_health": ("monitoring", "service health", "read",
        "you want a single verdict on whether an application service is healthy, with SLO status and active alerts",
        "the cloud provider's own status; a dashboard of every golden signal"),
    "observability.get_dashboard": ("monitoring", "dashboard", "read",
        "you want the big picture of a service: latency, errors, traffic and saturation together",
        "one specific metric or a health verdict"),
    "observability.get_alerts": ("monitoring", "alert", "search",
        "you need the monitoring alerts that are firing or resolved",
        "incidents; log search"),
    "observability.search_logs": ("monitoring", "application logs", "search",
        "searching a service's application logs by text, level or time; the system of record for application logs",
        "one pod's container output; provider-side logs of a database or VM"),
    "observability.get_trace": ("monitoring", "trace", "read",
        "you have a trace ID and need its spans",
        "finding traces without an ID"),
    "observability.search_traces": ("monitoring", "trace", "search",
        "finding slow or recent traces for a service",
        "reading one trace you already have the ID of"),
    "kubernetes.get_pods": ("kubernetes", "kubernetes pod", "read",
        "listing the pods behind a service with their readiness, restarts and resource use",
        "the deployment object's replicas and image; pod logs"),
    "kubernetes.get_deployment": ("kubernetes", "kubernetes deployment", "read",
        "reading a service's Kubernetes Deployment: replicas, image, rollout revision",
        "the release pipeline's deployment history; individual pods"),
    "kubernetes.get_pod_logs": ("kubernetes", "pod logs", "read",
        "reading the recent container output of one named pod",
        "searching a service's application logs across pods"),
    "kubernetes.get_events": ("kubernetes", "kubernetes events", "read",
        "cluster events for a service's workloads: scaling, rollouts, probe failures, OOM kills, evictions",
        "application logs; deployment history"),
    "kubernetes.restart_pod": ("kubernetes", "kubernetes pod", "restart",
        "recovering one stuck or unhealthy pod by recreating it",
        "restarting every pod of a service; rolling back a release"),
    "kubernetes.restart_deployment": ("kubernetes", "kubernetes deployment", "restart",
        "a rolling restart of every pod of a service with the same version",
        "one pod; going back to an earlier version"),
    "kubernetes.scale_deployment": ("kubernetes", "kubernetes deployment", "scale",
        "changing how many replicas a service runs",
        "restarting pods; changing a connection-pool size"),
    "kubernetes.rollback_deployment": ("kubernetes", "kubernetes deployment", "roll back",
        "undoing a Kubernetes rollout directly on the cluster, for workloads not managed by the release pipeline",
        "rolling back a service release that the release pipeline and GitOps manage"),
    "source_control.search_deployments": ("release pipeline", "deployment record", "search",
        "what version was deployed where and when; the system of record for deployment history",
        "the Kubernetes Deployment object; one deployment you have the ID of"),
    "source_control.get_deployment": ("release pipeline", "deployment record", "read",
        "reading one deployment record you have the ID of",
        "listing recent deployments"),
    "source_control.rollback_release": ("release pipeline", "service release", "roll back",
        "rolling a service back to a previous release through the release pipeline, keeping GitOps consistent",
        "undoing a raw Kubernetes rollout; restarting pods"),
    "source_control.get_release": ("release pipeline", "service release", "read",
        "reading a release by version: its commit and the commits it includes",
        "deployment history; a single commit's diff"),
    "source_control.get_commit": ("release pipeline", "commit", "read",
        "reading one commit's message, author and changed files",
        "the code diff itself; searching history"),
    "source_control.get_diff": ("release pipeline", "code diff", "read",
        "seeing the actual code changes a commit introduced",
        "commit metadata; searching history"),
    "source_control.search_commits": ("release pipeline", "commit", "search",
        "searching a repository's commit history by text or date",
        "one commit you already have the hash of"),
    "database.get_connection_pool_stats": ("database", "connection pool", "read",
        "a service's database connection-pool usage: max, in use, waiting, acquire wait",
        "slow queries; database engine sessions"),
    "database.list_slow_queries": ("database", "database query", "search",
        "the slowest statements on a database cluster",
        "connection-pool usage of a service"),
    "database.kill_session": ("database", "database session", "cancel",
        "terminating one database session or connection",
        "failing over a cluster; restarting a service"),
    "database.failover_cluster": ("database", "database cluster", "fail over",
        "forcing a database cluster onto its standby",
        "killing one session"),
    "cloud.describe_resource": ("cloud", "cloud resource", "read",
        "describing any cloud resource by ID, including managed databases and caches: status, configuration, events, metrics",
        "a virtual machine's own details; the provider's regional status"),
    "cloud.get_instance": ("cloud", "cloud instance", "read",
        "reading a virtual machine instance's state, type and CPU",
        "Kubernetes pods; other cloud resources"),
    "cloud.get_service_health": ("cloud", "provider status", "read",
        "whether the cloud provider itself has an outage in a region",
        "the health of your own application"),
    "cloud.query_cloud_logs": ("cloud", "cloud logs", "search",
        "provider-level logs of a cloud resource: database engine, load balancer or VM system logs",
        "application logs of a service"),
    "cloud.restart_instance": ("cloud", "cloud instance", "restart",
        "rebooting one virtual machine",
        "Kubernetes pods or deployments; container tasks"),
    "cloud.restart_task": ("cloud", "container task", "restart",
        "replacing one stopped or stuck container task",
        "Kubernetes pods; virtual machines"),
    "cloud.terminate_instance": ("cloud", "cloud instance", "terminate",
        "permanently removing a virtual machine",
        "rebooting it"),
    "collaboration.post_message": ("chat", "chat message", "post",
        "telling people something in a chat channel",
        "adding a note to the incident record"),
    "collaboration.search_messages": ("chat", "chat message", "search",
        "finding what was said in chat",
        "reading one channel's topic and latest messages"),
    "collaboration.get_channel": ("chat", "chat channel", "read",
        "reading a channel's topic and most recent messages",
        "searching messages across channels"),
    "collaboration.create_incident_channel": ("chat", "chat channel", "create",
        "opening a dedicated chat channel for an incident",
        "posting in an existing channel"),
    "feature_flags.get_flag": ("feature flags", "feature flag", "read",
        "a feature flag's current state in an environment",
        "the history of flag changes; changing a flag"),
    "feature_flags.set_flag": ("feature flags", "feature flag", "change",
        "turning a feature flag on or off, or changing its rollout percentage",
        "restarting or rolling back a service"),
    "feature_flags.list_flag_changes": ("feature flags", "flag change", "search",
        "who changed which feature flags recently",
        "one flag's current state"),
    "cmdb.get_service": ("service catalog", "service record", "read",
        "a service's owning team, support group and tier",
        "who is on call right now; dependencies"),
    "cmdb.get_dependencies": ("service catalog", "service dependencies", "read",
        "what a service depends on",
        "ownership"),
}

# pairs of core capabilities that look alike but must not be confused
NOT_EQUIVALENT = [
    ("source_control.rollback_release", "kubernetes.rollback_deployment"),
    ("kubernetes.restart_pod", "kubernetes.restart_deployment"),
    ("kubernetes.restart_deployment", "kubernetes.rollback_deployment"),
    ("itsm.add_incident_comment", "collaboration.post_message"),
    ("itsm.update_incident", "itsm.close_incident"),
    ("observability.search_logs", "kubernetes.get_pod_logs"),
    ("observability.search_logs", "cloud.query_cloud_logs"),
    ("observability.get_service_health", "cloud.get_service_health"),
    ("source_control.search_deployments", "kubernetes.get_deployment"),
    ("cloud.describe_resource", "cloud.get_instance"),
    ("cloud.restart_instance", "cloud.restart_task"),
    ("feature_flags.get_flag", "feature_flags.list_flag_changes"),
]

PER_CLUSTER_SERVERS = {"k8s_prod_eu", "k8s_staging_eu", "k8s_dev_eu"}
CLUSTER_CORE = {"get_pods": "kubernetes.get_pods", "describe_pod": "kubernetes.get_pods", "get_deployment": "kubernetes.get_deployment",
                "get_logs": "kubernetes.get_pod_logs", "restart_pod": "kubernetes.restart_pod",
                "restart_deployment": "kubernetes.restart_deployment", "rollback_deployment": "kubernetes.rollback_deployment",
                "scale_deployment": "kubernetes.scale_deployment"}
# mirrors whose job differs from the core tool whose data they return: their own capability
OWN_JOB = {"db_admin.get_db_connections", "db_admin.get_replication_lag"}
# generated tools that do a core tool's job without mirroring it
DECLARED_EQUIVALENTS = {
    "logstream.query_logs": "observability.search_logs",
    "servicedesk_v1.update_ticket": "itsm.update_incident", "servicedesk_v1.add_ticket_note": "itsm.add_incident_comment",
    "servicedesk_v1.resolve_ticket": "itsm.close_incident", "flags_legacy.toggle_flag": "feature_flags.set_flag",
    "cloud_ops.reboot_vm": "cloud.restart_instance", "cloud_ops.terminate_instance": "cloud.terminate_instance",
    "db_admin.kill_query": "database.kill_session", "cicd.rollback_pipeline": "source_control.rollback_release",
}

# required parameter -> entity types it takes (docs/CAPABILITY_RESOLUTION_V5.md, section 3)
PARAM_ENTITIES = {
    "incident_id": ("incident",), "number": ("incident",), "channel": ("channel",), "pod": ("pod",),
    "instance_id": ("instance",), "task_id": ("task",), "database_id": ("database",),
    "resource_id": ("instance", "task", "database", "cache"), "deployment_id": ("deployment",),
    "to_version": ("release",), "version": ("release",), "sha": ("commit",), "trace_id": ("trace",),
}
FLAG_PARAMS = {"key", "name"}  # only on feature-flag tools

VERB_ACTION = {"get": "read", "describe": "read", "list": "search", "search": "search", "query": "search", "find": "search",
               "count": "search", "tail": "read", "show": "read", "run": "read", "export": "create", "create": "create",
               "update": "update", "delete": "terminate", "restart": "restart", "reboot": "restart", "stop": "cancel",
               "start": "change", "terminate": "terminate", "resize": "scale", "scale": "scale", "cancel": "cancel",
               "kill": "cancel", "set": "change", "toggle": "change", "rotate": "change", "revoke": "cancel",
               "purge": "cancel", "flush": "cancel", "evict": "cancel", "drain": "cancel", "cordon": "change",
               "exec": "change", "page": "post", "acknowledge": "update", "escalate": "update", "override": "change",
               "post": "post", "approve": "update", "pay": "update", "award": "update", "sign": "update", "merge": "update",
               "launch": "change", "pause": "change", "assign": "update", "publish": "change", "reship": "create",
               "check": "update", "grant": "change", "trigger": "change", "redeploy": "restart", "rollback": "roll back",
               "promote": "change", "snapshot": "create", "ack": "update", "silence": "change", "resolve": "close",
               "add": "comment", "find_incident": "read"}


def _entity_types(input_schema: dict[str, Any], domain: str) -> list[str]:
    types: list[str] = []
    for param in input_schema.get("required") or []:
        found = PARAM_ENTITIES.get(param, ("flag",) if param in FLAG_PARAMS and domain == "feature-flags" else ())
        types += [t for t in found if t not in types]
    return types


def _slug(text: str) -> str:
    return text.replace(" ", "-")


def build_capabilities() -> dict[str, Any]:
    pool = build_pool()["pool"]
    specs = {t.tool_id: t for t in pool}
    tools: dict[str, dict[str, str]] = {}
    caps: dict[str, dict[str, Any]] = {}

    def add(tool_id: str, cap_id: str, role: str) -> None:
        spec = specs[tool_id]
        tools[tool_id] = {"capability": cap_id, "role": role}
        caps[cap_id]["implementations"].append({"tool_id": tool_id, "role": role, "environments": spec.registry["environments"],
                                                "lifecycle": spec.registry["lifecycle"]})

    def new(cap_id: str, **fields: Any) -> None:
        caps[cap_id] = {"id": cap_id, "not_equivalent": [], "implementations": [], **fields}

    core_ids = {}
    for tool_id, (system, resource, action, use_when, not_for) in CORE.items():
        spec = specs[tool_id]
        reg = spec.registry
        cap_id = f"{_slug(resource)}.{_slug(action).replace('-', '')}"
        if cap_id in caps:
            raise AssertionError(f"duplicate core capability {cap_id}")
        new(cap_id, system=system, resource=resource, action=action, domain=reg["domain"], core=True, authoritative=tool_id,
            risk=reg["risk"], side_effect=reg["side_effect"], use_when=use_when, not_for=not_for,
            summary=spec.description.split(". ")[0].rstrip("."), entity_types=_entity_types(spec.input_schema, reg["domain"]))
        add(tool_id, cap_id, "authoritative")
        core_ids[tool_id] = cap_id
    for a, b in NOT_EQUIVALENT:
        caps[core_ids[a]]["not_equivalent"].append(core_ids[b])
        caps[core_ids[b]]["not_equivalent"].append(core_ids[a])

    for spec in pool:
        if spec.family == "core" or spec.registry is None:
            continue
        reg = spec.registry
        tool_id, server, name = spec.tool_id, spec.server, spec.name
        deprecated = reg["lifecycle"] == "deprecated"
        kind, _, rest = spec.handler.partition("|")
        mirrored = rest.split("|")[0] if kind in ("generated:mirror", "generated:deprecated") else None
        if server in PER_CLUSTER_SERVERS:
            core = CLUSTER_CORE.get(name)
            cap_id = core_ids[core] if core else f"kubernetes-cluster.{name}"
            role = "legacy" if deprecated else "environment_variant"
        elif mirrored and tool_id not in OWN_JOB:
            cap_id, role = core_ids[mirrored], "legacy" if deprecated else "substitute"
        elif tool_id in DECLARED_EQUIVALENTS:
            cap_id, role = core_ids[DECLARED_EQUIVALENTS[tool_id]], "legacy" if deprecated else "substitute"
        else:
            cap_id = f"{server}.{name}"
            role = "legacy" if deprecated else "authoritative"
        if cap_id not in caps:
            system = BUSINESS_SYSTEM if spec.family == "business" else DOMAIN_SYSTEM.get(reg["domain"], reg["domain"])
            verb = name.split("_", 1)[0]
            action = VERB_ACTION.get(verb, "read" if reg["read_only"] else "update")
            if reg["read_only"] and action not in READ_ACTIONS:
                action = "read"
            new(cap_id, system=system, resource=reg["resource_type"].replace("-", " "), action=action, domain=reg["domain"],
                core=False, authoritative=None, risk=reg["risk"], side_effect=reg["side_effect"], use_when="", not_for="",
                summary=spec.description.split(". ")[0].rstrip("."), entity_types=_entity_types(spec.input_schema, reg["domain"]))
        if role == "authoritative":
            caps[cap_id]["authoritative"] = tool_id
        add(tool_id, cap_id, role)

    for cap in caps.values():
        cap["not_equivalent"] = sorted(set(cap["not_equivalent"]))
        cap["implementations"].sort(key=lambda i: (["authoritative", "environment_variant", "substitute", "legacy"].index(i["role"]),
                                                   i["tool_id"]))
    return {"version": 1, "capabilities": dict(sorted(caps.items())), "tools": dict(sorted(tools.items()))}


def write_capabilities(path: Path = CAPABILITIES_FILE) -> dict[str, Any]:
    data = build_capabilities()
    path.write_text(json.dumps(data, indent=1) + "\n")
    return data


def main() -> None:
    data = write_capabilities()
    roles: dict[str, int] = {}
    for t in data["tools"].values():
        roles[t["role"]] = roles.get(t["role"], 0) + 1
    print(f"wrote {CAPABILITIES_FILE}: {len(data['capabilities'])} capabilities, {len(data['tools'])} tools, roles {roles}")


if __name__ == "__main__":
    main()
