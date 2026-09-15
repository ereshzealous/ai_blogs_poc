"""feature-flags-mcp: feature flag state and change history."""

from servers.common.meta import registry_record
from servers.common.toolspec import ENVIRONMENT, ToolSpec, schema

S = "feature_flags"
OWNER = "developer-platform"
FLAG = {"type": "string", "description": "Flag key, e.g. new-pricing-engine."}


def _meta(capability, ops, risk, scopes):
    return registry_record(domain="feature-flags", capability=capability, resource_type="feature-flag", operations=ops, risk=risk,
                           owner=OWNER, scopes=scopes, authoritative_for=["feature-flag"])


TOOLS = [
    ToolSpec(
        S, "get_flag",
        "Get a feature flag's current state in an environment: enabled, rollout percentage, owner and description.",
        schema({"key": FLAG, "environment": ENVIRONMENT}, ["key", "environment"]),
        title="Get feature flag", read_only_hint=True, open_world_hint=False, handler="feature_flags:get_flag",
        collision_group="flags-read", registry=_meta("flag-read", ["get"], "READ_ONLY", ["flags.read"]),
    ),
    ToolSpec(
        S, "list_flag_changes",
        "List recent feature flag changes (who changed what, when) in an environment, newest first.",
        schema({"environment": ENVIRONMENT, "since": {"type": "string", "format": "date-time"}}, []),
        title="List flag changes", read_only_hint=True, open_world_hint=False, handler="feature_flags:list_flag_changes",
        collision_group="flags-read", registry=_meta("flag-read", ["list"], "READ_ONLY", ["flags.read"]),
    ),
    ToolSpec(
        S, "set_flag",
        "Enable or disable a feature flag, or change its rollout percentage, in one environment. Takes effect "
        "for all traffic within seconds.",
        schema({"key": FLAG, "environment": ENVIRONMENT, "enabled": {"type": "boolean"},
                "rollout_pct": {"type": "integer", "minimum": 0, "maximum": 100}}, ["key", "environment", "enabled"]),
        title="Set feature flag", read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False,
        handler="feature_flags:set_flag", collision_group="flags-write", registry=_meta("flag-write", ["update"], "HIGH_RISK_WRITE", ["flags.write"]),
    ),
]
