"""source-control-mcp: repositories, commits, releases and the release pipeline's deployments."""

from servers.common.meta import registry_record
from servers.common.toolspec import ENVIRONMENT, SERVICE, ToolSpec, schema

S = "source_control"
OWNER = "developer-platform"
REPO = {"type": "string", "description": "Repository as org/name, e.g. shop/checkout-api."}
SHA = {"type": "string", "pattern": "^[0-9a-f]{7,40}$", "description": "Commit SHA (7-40 hex characters)."}
VERSION = {"type": "string", "pattern": "^v[0-9]+\\.[0-9]+(\\.[0-9]+)?$", "description": "Release version, e.g. v4.16."}


def _meta(capability, resource, ops, risk, scopes, authoritative=None):
    return registry_record(domain="delivery", capability=capability, resource_type=resource, operations=ops, risk=risk,
                           owner=OWNER, scopes=scopes, authoritative_for=authoritative)


TOOLS = [
    ToolSpec(
        S, "get_commit",
        "Get a commit by SHA: message, author, timestamp and the list of files changed.",
        schema({"sha": SHA, "repository": REPO}, ["sha"]),
        title="Get commit", read_only_hint=True, open_world_hint=False, handler="source_control:get_commit",
        collision_group="code-history", registry=_meta("code-read", "commit", ["get"], "READ_ONLY", ["source.read"], ["commit"]),
    ),
    ToolSpec(
        S, "search_commits",
        "Search a repository's commit history by message text and date.",
        schema({"repository": REPO, "query": {"type": "string"}, "since": {"type": "string", "format": "date-time"}}, ["repository"]),
        title="Search commits", read_only_hint=True, open_world_hint=False, handler="source_control:search_commits",
        collision_group="code-history", registry=_meta("code-read", "commit", ["search"], "READ_ONLY", ["source.read"], ["commit"]),
    ),
    ToolSpec(
        S, "get_deployment",
        "Get one release-pipeline deployment record by ID: service, environment, version, previous version, "
        "commit, change request, start/finish time and status.",
        schema({"deployment_id": {"type": "string", "pattern": "^DEP-[0-9]+$"}}, ["deployment_id"]),
        title="Get deployment record", read_only_hint=True, open_world_hint=False, handler="source_control:get_deployment",
        collision_group="deployment-lookup",
        registry=_meta("deployment-history", "service-deployment", ["get"], "READ_ONLY", ["source.read"], ["service-deployment"]),
    ),
    ToolSpec(
        S, "search_deployments",
        "List release-pipeline deployments, newest first, filtered by service, environment and start time. This is "
        "the system of record for what version was deployed where and when.",
        schema({"service": SERVICE, "environment": ENVIRONMENT, "since": {"type": "string", "format": "date-time"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, []),
        title="Search deployments", read_only_hint=True, open_world_hint=False, handler="source_control:search_deployments",
        collision_group="deployment-lookup",
        registry=_meta("deployment-history", "service-deployment", ["search"], "READ_ONLY", ["source.read"], ["service-deployment"]),
    ),
    ToolSpec(
        S, "get_diff",
        "Get the unified diff introduced by a commit.",
        schema({"sha": SHA, "repository": REPO}, ["sha"]),
        title="Get diff", read_only_hint=True, open_world_hint=False, handler="source_control:get_diff",
        collision_group="code-history", registry=_meta("code-read", "commit-diff", ["get"], "READ_ONLY", ["source.read"], ["commit"]),
    ),
    ToolSpec(
        S, "get_release",
        "Get a service release by version: release ID, commit and the commits included since the previous release.",
        schema({"service": SERVICE, "version": VERSION}, ["service", "version"]),
        title="Get release", read_only_hint=True, open_world_hint=False, handler="source_control:get_release",
        collision_group="release-lookup", registry=_meta("release-read", "service-release", ["get"], "READ_ONLY", ["source.read"], ["service-release"]),
    ),
    ToolSpec(
        S, "rollback_release",
        "Roll a service back to a previous release through the release pipeline: redeploys the earlier version to "
        "the environment, records a deployment and keeps GitOps state consistent.",
        schema({"service": SERVICE, "environment": ENVIRONMENT, "to_version": VERSION,
                "reason": {"type": "string", "description": "Why the rollback is needed; recorded on the deployment."}},
               ["service", "environment", "to_version"]),
        title="Roll back release", read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False,
        handler="source_control:rollback_release", collision_group="rollback",
        registry=_meta("deployment-rollback", "service-release", ["rollback"], "HIGH_RISK_WRITE", ["deploy.rollback"], ["service-release"]),
    ),
]
