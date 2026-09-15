"""kubernetes-mcp: workloads on the company's Kubernetes clusters (one server, all environments)."""

from servers.common.meta import registry_record
from servers.common.toolspec import ENVIRONMENT, SERVICE, ToolSpec, schema

S = "kubernetes"
OWNER = "platform-engineering"
POD = {"type": "string", "description": "Pod name, e.g. checkout-api-7d9f8c6b5-2kq8x."}


def _meta(capability, resource, ops, risk, scopes, authoritative=None, destructive=False, notes=None):
    return registry_record(domain="runtime", capability=capability, resource_type=resource, operations=ops, risk=risk,
                           owner=OWNER, scopes=scopes, authoritative_for=authoritative, destructive=destructive, notes=notes)


TOOLS = [
    ToolSpec(
        S, "get_pods",
        "List the pods backing a service's Kubernetes deployment with phase, readiness, restart count, node, "
        "image and current CPU/memory utilisation.",
        schema({"service": SERVICE, "environment": ENVIRONMENT}, ["service", "environment"]),
        title="Get pods", read_only_hint=True, open_world_hint=False, handler="kubernetes:get_pods",
        collision_group="runtime-state", registry=_meta("workload-read", "kubernetes-pod", ["list"], "READ_ONLY", ["k8s.read"], ["kubernetes-pod"]),
    ),
    ToolSpec(
        S, "get_deployment",
        "Get the Kubernetes Deployment object for a service: desired/ready replicas, container image, rollout "
        "revision, strategy and conditions.",
        schema({"service": SERVICE, "environment": ENVIRONMENT}, ["service", "environment"]),
        title="Get Kubernetes deployment", read_only_hint=True, open_world_hint=False, handler="kubernetes:get_deployment",
        collision_group="deployment-lookup",
        registry=_meta("workload-read", "kubernetes-deployment", ["get"], "READ_ONLY", ["k8s.read"], ["kubernetes-deployment"]),
    ),
    ToolSpec(
        S, "get_events",
        "List recent Kubernetes events (scaling, rollouts, probe failures, OOM kills, evictions) for a service's workloads.",
        schema({"service": SERVICE, "environment": ENVIRONMENT}, ["service", "environment"]),
        title="Get Kubernetes events", read_only_hint=True, open_world_hint=False, handler="kubernetes:get_events",
        collision_group="runtime-state", registry=_meta("workload-read", "kubernetes-event", ["list"], "READ_ONLY", ["k8s.read"], ["kubernetes-event"]),
    ),
    ToolSpec(
        S, "get_pod_logs",
        "Read the most recent stdout/stderr lines of a single pod's container, like kubectl logs.",
        schema({"pod": POD, "environment": ENVIRONMENT, "tail_lines": {"type": "integer", "minimum": 1, "maximum": 500}},
               ["pod", "environment"]),
        title="Get pod logs", read_only_hint=True, open_world_hint=False, handler="kubernetes:get_pod_logs",
        collision_group="logs", registry=_meta("workload-read", "container-logs", ["get"], "READ_ONLY", ["k8s.read"]),
    ),
    ToolSpec(
        S, "restart_pod",
        "Delete one pod so its ReplicaSet recreates it. Use to recover a single stuck or unhealthy pod.",
        schema({"pod": POD, "environment": ENVIRONMENT}, ["pod", "environment"]),
        title="Restart pod", read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False,
        handler="kubernetes:restart_pod", collision_group="restart",
        registry=_meta("workload-restart", "kubernetes-pod", ["restart"], "HIGH_RISK_WRITE", ["k8s.workload.write"]),
    ),
    ToolSpec(
        S, "restart_deployment",
        "Trigger a rolling restart of every pod in a service's deployment (kubectl rollout restart). Pods are "
        "replaced gradually with the same image and configuration.",
        schema({"service": SERVICE, "environment": ENVIRONMENT}, ["service", "environment"]),
        title="Restart deployment", read_only_hint=False, destructive_hint=False, open_world_hint=False,
        handler="kubernetes:restart_deployment", collision_group="restart",
        registry=_meta("workload-restart", "kubernetes-deployment", ["restart"], "HIGH_RISK_WRITE", ["k8s.workload.write"]),
    ),
    ToolSpec(
        S, "rollback_deployment",
        "Roll a Kubernetes deployment back to a previous ReplicaSet revision (kubectl rollout undo). Acts on the "
        "cluster object directly, outside the release pipeline.",
        schema({"service": SERVICE, "environment": ENVIRONMENT,
                "to_revision": {"type": "integer", "minimum": 1, "description": "Revision number; defaults to the previous revision."}},
               ["service", "environment"]),
        title="Roll back Kubernetes deployment", read_only_hint=False, destructive_hint=False, open_world_hint=False,
        handler="kubernetes:rollback_deployment", collision_group="rollback",
        registry=_meta("deployment-rollback", "kubernetes-deployment", ["rollback"], "HIGH_RISK_WRITE", ["k8s.deployment.write"],
                       notes="Break-glass only. Bypasses the release pipeline; GitOps re-applies the pipeline's version on next sync."),
    ),
    ToolSpec(
        S, "scale_deployment",
        "Change the number of replicas of a service's deployment.",
        schema({"service": SERVICE, "environment": ENVIRONMENT, "replicas": {"type": "integer", "minimum": 0, "maximum": 100}},
               ["service", "environment", "replicas"]),
        title="Scale deployment", read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False,
        handler="kubernetes:scale_deployment", collision_group="scale",
        registry=_meta("workload-scale", "kubernetes-deployment", ["scale"], "HIGH_RISK_WRITE", ["k8s.workload.write"]),
    ),
]
