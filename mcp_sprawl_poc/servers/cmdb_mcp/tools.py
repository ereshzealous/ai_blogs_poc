"""cmdb-mcp: configuration items, ownership and dependencies from the service catalogue."""

from servers.common.meta import registry_record
from servers.common.toolspec import SERVICE, ToolSpec, schema

S = "cmdb"
OWNER = "it-service-management"


def _meta(capability, ops):
    return registry_record(domain="service-catalog", capability=capability, resource_type="configuration-item", operations=ops,
                           risk="READ_ONLY", owner=OWNER, scopes=["cmdb.read"], authoritative_for=["service-ownership"])


TOOLS = [
    ToolSpec(
        S, "get_service",
        "Get a service's configuration item: owning team, support group, tier and business service.",
        schema({"service": SERVICE}, ["service"]),
        title="Get service record", read_only_hint=True, open_world_hint=False, handler="cmdb:get_service",
        collision_group="ownership", registry=_meta("service-ownership", ["get"]),
    ),
    ToolSpec(
        S, "get_dependencies",
        "List the upstream dependencies of a service (databases, caches, other services) with their owners.",
        schema({"service": SERVICE}, ["service"]),
        title="Get service dependencies", read_only_hint=True, open_world_hint=False, handler="cmdb:get_dependencies",
        collision_group="ownership", registry=_meta("service-dependencies", ["list"]),
    ),
]
