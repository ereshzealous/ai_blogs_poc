"""The 50 hand-written core tools on 9 MCP servers, in a fixed, meaningful order.

The first ten entries of CORE_LADDER_ORDER form catalog_10 and the first 25 form catalog_25: the
tools an incident agent reaches for first. The full list is catalog_50.
"""

from __future__ import annotations

from servers.cloud_mcp.tools import TOOLS as CLOUD
from servers.cmdb_mcp.tools import TOOLS as CMDB
from servers.collaboration_mcp.tools import TOOLS as COLLABORATION
from servers.common.toolspec import ToolSpec
from servers.database_mcp.tools import TOOLS as DATABASE
from servers.feature_flags_mcp.tools import TOOLS as FEATURE_FLAGS
from servers.itsm_mcp.tools import TOOLS as ITSM
from servers.kubernetes_mcp.tools import TOOLS as KUBERNETES
from servers.observability_mcp.tools import TOOLS as OBSERVABILITY
from servers.source_control_mcp.tools import TOOLS as SOURCE_CONTROL

CORE_SERVERS: dict[str, list[ToolSpec]] = {
    "observability": OBSERVABILITY,
    "itsm": ITSM,
    "kubernetes": KUBERNETES,
    "source_control": SOURCE_CONTROL,
    "cloud": CLOUD,
    "collaboration": COLLABORATION,
    "database": DATABASE,
    "feature_flags": FEATURE_FLAGS,
    "cmdb": CMDB,
}

CORE_TOOLS: dict[str, ToolSpec] = {t.tool_id: t for tools in CORE_SERVERS.values() for t in tools}

CORE_LADDER_ORDER: list[str] = [
    # catalog_10
    "itsm.get_incident",
    "observability.query_latency",
    "observability.query_metrics",
    "observability.search_logs",
    "observability.get_trace",
    "source_control.search_deployments",
    "kubernetes.get_pods",
    "source_control.rollback_release",
    "itsm.update_incident",
    "collaboration.post_message",
    # catalog_25
    "observability.query_error_rate",
    "observability.get_service_health",
    "observability.get_alerts",
    "observability.search_traces",
    "itsm.search_incidents",
    "itsm.add_incident_comment",
    "kubernetes.get_deployment",
    "kubernetes.get_pod_logs",
    "kubernetes.restart_deployment",
    "kubernetes.rollback_deployment",
    "source_control.get_diff",
    "source_control.get_deployment",
    "database.get_connection_pool_stats",
    "cloud.describe_resource",
    "feature_flags.list_flag_changes",
    # catalog_50
    "observability.get_dashboard",
    "itsm.create_change",
    "itsm.close_incident",
    "kubernetes.get_events",
    "kubernetes.restart_pod",
    "kubernetes.scale_deployment",
    "source_control.get_commit",
    "source_control.search_commits",
    "source_control.get_release",
    "cloud.get_instance",
    "cloud.get_service_health",
    "cloud.query_cloud_logs",
    "cloud.restart_instance",
    "cloud.restart_task",
    "cloud.terminate_instance",
    "collaboration.search_messages",
    "collaboration.get_channel",
    "collaboration.create_incident_channel",
    "database.list_slow_queries",
    "database.kill_session",
    "database.failover_cluster",
    "feature_flags.get_flag",
    "feature_flags.set_flag",
    "cmdb.get_service",
    "cmdb.get_dependencies",
]

assert len(CORE_TOOLS) == 50, len(CORE_TOOLS)
assert sorted(CORE_LADDER_ORDER) == sorted(CORE_TOOLS), set(CORE_TOOLS) ^ set(CORE_LADDER_ORDER)
