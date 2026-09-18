"""The capability vocabulary: systems, resources and actions, and the plain-language labels used in questions.

The same values describe a capability in `benchmark/catalogs/capabilities.json` and a user's hidden intent in held-out
set 3 (docs/CAPABILITY_RESOLUTION_V5.md, section 4). Labels never name a tool.
"""

from __future__ import annotations

# the nine systems a core tool runs on (the intent vocabulary)
CORE_SYSTEMS = ("monitoring", "kubernetes", "release pipeline", "cloud", "incident management", "chat", "database",
                "feature flags", "service catalog")

# registry domain -> system; generated tools outside the core systems keep a system of their own
DOMAIN_SYSTEM = {
    "observability": "monitoring", "runtime": "kubernetes", "delivery": "release pipeline", "cloud": "cloud",
    "itsm": "incident management", "collaboration": "chat", "database": "database", "feature-flags": "feature flags",
    "service-catalog": "service catalog", "incident-response": "on-call", "incident-communication": "status page",
    "knowledge": "runbooks", "network": "network", "security": "security", "analytics": "data warehouse",
    "finops": "cost management",
}
BUSINESS_SYSTEM = "business application"
SYSTEM_DOMAIN = {system: domain for domain, system in DOMAIN_SYSTEM.items()}

RESOURCES = (
    "incident", "change request", "chat message", "chat channel", "service release", "deployment record",
    "kubernetes deployment", "kubernetes pod", "pod logs", "kubernetes events", "application logs", "trace", "metric",
    "latency", "error rate", "alert", "dashboard", "service health", "commit", "code diff", "connection pool",
    "database query", "database session", "database cluster", "cloud resource", "cloud instance", "container task",
    "cloud logs", "provider status", "feature flag", "flag change", "service record", "service dependencies",
)

ACTIONS = ("read", "search", "restart", "scale", "roll back", "change", "create", "update", "comment", "close", "post",
           "terminate", "fail over", "cancel")
READ_ACTIONS = frozenset({"read", "search"})

ENVIRONMENTS = ("production", "staging", "development")

SYSTEM_LABELS = {
    "monitoring": "the monitoring system", "kubernetes": "Kubernetes", "release pipeline": "the release pipeline",
    "cloud": "the cloud provider", "incident management": "the incident record", "chat": "the team chat",
    "database": "the database", "feature flags": "the feature-flag service", "service catalog": "the service catalog",
}

RESOURCE_LABELS = {
    "incident": "the incident", "change request": "a change request", "chat message": "a chat message",
    "chat channel": "a chat channel", "service release": "the service's release", "deployment record": "the deployment history",
    "kubernetes deployment": "the whole Kubernetes deployment", "kubernetes pod": "a single pod", "pod logs": "one pod's logs",
    "kubernetes events": "the cluster events", "application logs": "the service's application logs", "trace": "request traces",
    "metric": "a metric time series", "latency": "latency percentiles", "error rate": "the error rate", "alert": "alerts",
    "dashboard": "the service dashboard", "service health": "the overall service health", "commit": "a commit",
    "code diff": "the code diff", "connection pool": "the connection pool", "database query": "database queries",
    "database session": "a database session", "database cluster": "the database cluster", "cloud resource": "a cloud resource",
    "cloud instance": "a virtual machine", "container task": "a container task", "cloud logs": "the provider-side logs",
    "provider status": "the cloud provider's own status", "feature flag": "a feature flag", "flag change": "recent flag changes",
    "service record": "the service's catalog entry", "service dependencies": "the service's dependencies",
}

ACTION_LABELS = {
    "read": "look it up", "search": "search for it", "restart": "restart it", "scale": "scale it",
    "roll back": "roll it back to an earlier version", "change": "change its setting", "create": "create a new one",
    "update": "update its fields", "comment": "add a note", "close": "close it", "post": "post a message",
    "terminate": "terminate it", "fail over": "fail it over", "cancel": "cancel or kill it",
}


def system_label(system: str) -> str:
    return SYSTEM_LABELS.get(system, f"the {system}")


def resource_label(resource: str) -> str:
    return RESOURCE_LABELS.get(resource, resource.replace("-", " "))


def action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action.replace("_", " "))
