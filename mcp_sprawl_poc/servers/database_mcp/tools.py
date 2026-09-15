"""database-mcp: operational views of managed databases and application connection pools."""

from servers.common.meta import registry_record
from servers.common.toolspec import ENVIRONMENT, SERVICE, ToolSpec, schema

S = "database"
OWNER = "data-platform"
DATABASE_ID = {"type": "string", "description": "Database cluster ID, e.g. orders-db-prod."}


def _meta(capability, resource, ops, risk, scopes, authoritative=None, destructive=False):
    return registry_record(domain="database", capability=capability, resource_type=resource, operations=ops, risk=risk,
                           owner=OWNER, scopes=scopes, authoritative_for=authoritative, destructive=destructive)


TOOLS = [
    ToolSpec(
        S, "get_connection_pool_stats",
        "Get a service's database connection-pool statistics as reported by its database client: max connections, "
        "in use, idle, waiting requests, acquire-wait p95 and acquire timeouts.",
        schema({"service": SERVICE, "environment": ENVIRONMENT}, ["service", "environment"]),
        title="Get connection pool stats", read_only_hint=True, open_world_hint=False, handler="database:get_connection_pool_stats",
        collision_group="db-read", registry=_meta("db-read", "connection-pool", ["get"], "READ_ONLY", ["db.read"], ["connection-pool"]),
    ),
    ToolSpec(
        S, "list_slow_queries",
        "List the slowest statements on a database cluster by mean execution time, with call rates.",
        schema({"database_id": DATABASE_ID, "limit": {"type": "integer", "minimum": 1, "maximum": 20}}, ["database_id"]),
        title="List slow queries", read_only_hint=True, open_world_hint=False, handler="database:list_slow_queries",
        collision_group="db-read", registry=_meta("db-read", "database-query", ["list"], "READ_ONLY", ["db.read"], ["database-query"]),
    ),
    ToolSpec(
        S, "kill_session",
        "Terminate a database backend session (connection) by session ID, rolling back its open transaction.",
        schema({"database_id": DATABASE_ID, "session_id": {"type": "integer", "minimum": 1}}, ["database_id", "session_id"]),
        title="Kill database session", read_only_hint=False, destructive_hint=False, open_world_hint=False, handler="database:kill_session",
        collision_group="db-write", registry=_meta("db-admin", "database-session", ["terminate"], "HIGH_RISK_WRITE", ["db.admin"]),
    ),
    ToolSpec(
        S, "failover_cluster",
        "Force a failover of a database cluster to its standby. Connections drop during promotion and in-flight "
        "transactions are lost.",
        schema({"database_id": DATABASE_ID, "reason": {"type": "string"}}, ["database_id"]),
        title="Fail over database cluster", read_only_hint=False, destructive_hint=True, open_world_hint=False,
        handler="database:failover_cluster", collision_group="db-write",
        registry=_meta("db-admin", "database-cluster", ["failover"], "HIGH_RISK_WRITE", ["db.admin"], destructive=True),
    ),
]
