"""cloud-mcp: cloud provider resources (managed databases, VMs, container tasks) and provider status."""

from servers.common.meta import registry_record
from servers.common.toolspec import TIME_RANGE, ToolSpec, schema

S = "cloud"
OWNER = "cloud-infrastructure"
RESOURCE_ID = {"type": "string", "description": "Cloud resource ID, e.g. orders-db-prod or i-0c41e7a9d2b3f5812."}
INSTANCE_ID = {"type": "string", "pattern": "^i-[0-9a-f]{8,17}$", "description": "VM instance ID."}
TASK_ID = {"type": "string", "pattern": "^task-[a-z0-9-]+$", "description": "Container task ID."}


def _meta(capability, resource, ops, risk, scopes, authoritative=None, destructive=False):
    return registry_record(domain="cloud", capability=capability, resource_type=resource, operations=ops, risk=risk,
                           owner=OWNER, scopes=scopes, authoritative_for=authoritative, destructive=destructive)


TOOLS = [
    ToolSpec(
        S, "get_instance",
        "Get a virtual machine instance: state, instance type, region and CPU utilisation.",
        schema({"instance_id": INSTANCE_ID}, ["instance_id"]),
        title="Get instance", read_only_hint=True, open_world_hint=True, handler="cloud:get_instance",
        collision_group="infra-read", registry=_meta("infra-read", "vm-instance", ["get"], "READ_ONLY", ["cloud.read"], ["vm-instance"]),
    ),
    ToolSpec(
        S, "get_service_health",
        "Get the cloud provider's own status for its services (compute, managed databases, load balancing) in a "
        "region. Reports provider-side outages, not the health of your applications.",
        schema({"region": {"type": "string", "description": "Region, e.g. eu-west-1."},
                "provider_service": {"type": "string", "description": "Provider service, e.g. managed-postgres."}}, ["region"]),
        title="Get cloud provider status", read_only_hint=True, open_world_hint=True, handler="cloud:get_service_health",
        collision_group="service-health", registry=_meta("provider-status", "cloud-provider-status", ["get"], "READ_ONLY", ["cloud.read"], ["cloud-provider-status"]),
    ),
    ToolSpec(
        S, "query_cloud_logs",
        "Query provider-level logs for a cloud resource (database engine logs, load balancer access logs, VM "
        "system logs).",
        schema({"resource_id": RESOURCE_ID, "query": {"type": "string"}, "time_range": TIME_RANGE}, ["resource_id"]),
        title="Query cloud logs", read_only_hint=True, open_world_hint=True, handler="cloud:query_cloud_logs",
        collision_group="logs", registry=_meta("infra-read", "cloud-resource-logs", ["query"], "READ_ONLY", ["cloud.read"], ["cloud-resource-logs"]),
    ),
    ToolSpec(
        S, "describe_resource",
        "Describe any cloud resource by ID: type, status, configuration, recent provider events and key metrics "
        "such as CPU and active connections.",
        schema({"resource_id": RESOURCE_ID}, ["resource_id"]),
        title="Describe cloud resource", read_only_hint=True, open_world_hint=True, handler="cloud:describe_resource",
        collision_group="infra-read", registry=_meta("infra-read", "cloud-resource", ["describe"], "READ_ONLY", ["cloud.read"], ["cloud-resource"]),
    ),
    ToolSpec(
        S, "restart_instance",
        "Reboot a virtual machine instance. The instance is unavailable for one to three minutes.",
        schema({"instance_id": INSTANCE_ID}, ["instance_id"]),
        title="Restart instance", read_only_hint=False, destructive_hint=False, open_world_hint=True, handler="cloud:restart_instance",
        collision_group="restart", registry=_meta("compute-restart", "vm-instance", ["restart"], "HIGH_RISK_WRITE", ["cloud.compute.write"]),
    ),
    ToolSpec(
        S, "restart_task",
        "Stop a running container task so the service scheduler starts a replacement.",
        schema({"task_id": TASK_ID}, ["task_id"]),
        title="Restart task", read_only_hint=False, destructive_hint=False, open_world_hint=True, handler="cloud:restart_task",
        collision_group="restart", registry=_meta("compute-restart", "container-task", ["restart"], "HIGH_RISK_WRITE", ["cloud.compute.write"]),
    ),
    ToolSpec(
        S, "terminate_instance",
        "Permanently terminate a virtual machine instance and delete its local storage. This cannot be undone.",
        schema({"instance_id": INSTANCE_ID}, ["instance_id"]),
        title="Terminate instance", read_only_hint=False, destructive_hint=True, open_world_hint=True, handler="cloud:terminate_instance",
        collision_group="terminate",
        registry=_meta("compute-terminate", "vm-instance", ["terminate"], "HIGH_RISK_WRITE", ["cloud.compute.terminate"], destructive=True),
    ),
]
