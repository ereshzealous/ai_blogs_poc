"""Mock Kubernetes backend: pods, deployments and events; mutations are recorded as world events."""

from __future__ import annotations

from typing import Any

from servers.common.handlers import Ctx, handler, require_service
from servers.common.scenario import metric_value


def _workload(ctx: Ctx, service: str, env: str) -> dict[str, Any]:
    require_service(ctx, service)
    wl = ctx.scenario.kubernetes.get(service, {}).get(env)
    if not wl:
        raise LookupError(f"No Kubernetes deployment for {service} in {env}.")
    return wl


def _rolled_back(ctx: Ctx, service: str, env: str) -> bool:
    return any(e["payload"]["service"] == service and e["payload"]["environment"] == env
               for e in ctx.world.events(ctx.run_id, "rollback"))


def _image(ctx: Ctx, service: str, env: str, wl: dict[str, Any]) -> tuple[str, int]:
    if _rolled_back(ctx, service, env):
        version = ctx.world.current_version(ctx.run_id, service, env)
        return wl["image"].rsplit(":", 1)[0] + f":{version}", wl["revision"] + 1
    return wl["image"], wl["revision"]


@handler("kubernetes:get_pods")
def get_pods(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    service, env = args["service"], args["environment"]
    wl = _workload(ctx, service, env)
    image, revision = _image(ctx, service, env, wl)
    recovered = ctx.world.recovered_at(ctx.run_id, service, env)
    minute = ctx.now.replace(second=0)
    cpu = metric_value(ctx.scenario, service, env, "cpu_utilization_pct", minute, recovered)
    mem = metric_value(ctx.scenario, service, env, "memory_utilization_pct", minute, recovered)
    suffix = "-rb" if revision != wl["revision"] else ""
    pods = [{"name": p["name"] + suffix, "phase": "Running", "ready": True, "restarts": p["restarts"], "node": p["node"],
             "image": image, "cpu_pct": cpu, "memory_pct": mem} for p in wl["pods"]]
    return {"service": service, "environment": env, "cluster": wl["cluster"], "namespace": wl["namespace"], "pods": pods}


@handler("kubernetes:get_deployment")
def get_deployment(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    service, env = args["service"], args["environment"]
    wl = _workload(ctx, service, env)
    image, revision = _image(ctx, service, env, wl)
    replicas = len(wl["pods"])
    for e in ctx.world.events(ctx.run_id, "scale"):
        if e["payload"]["service"] == service and e["payload"]["environment"] == env:
            replicas = e["payload"]["replicas"]
    return {"name": service, "namespace": wl["namespace"], "cluster": wl["cluster"], "environment": env,
            "replicas": {"desired": replicas, "ready": replicas, "available": replicas}, "image": image, "revision": revision,
            "strategy": "RollingUpdate", "managed_by": wl["managed_by"],
            "conditions": [{"type": "Available", "status": "True"}, {"type": "Progressing", "status": "True", "reason": "NewReplicaSetAvailable"}]}


@handler("kubernetes:get_events")
def get_events(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    service, env = args["service"], args["environment"]
    wl = _workload(ctx, service, env)
    events = list(wl.get("events", []))
    for e in ctx.world.events(ctx.run_id):
        p = e["payload"]
        if p.get("service") == service and p.get("environment") == env and e["kind"] in ("rollback", "deployment_restart", "scale"):
            reason = {"rollback": "RolloutComplete", "deployment_restart": "RolloutRestart", "scale": "ScalingReplicaSet"}[e["kind"]]
            events.append({"at": e["at"], "type": "Normal", "reason": reason, "message": f"{e['kind']} via {e['server']}.{e['tool']}"})
    return {"service": service, "environment": env, "events": events}


@handler("kubernetes:get_pod_logs")
def get_pod_logs(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    env, pod = args["environment"], args["pod"]
    for service, envs in ctx.scenario.kubernetes.items():
        wl = envs.get(env)
        if wl and any(p["name"] == pod for p in wl["pods"]):
            templates = ctx.scenario.logs.get(service, {}).get(env, {})
            shape = ctx.scenario.metrics.get(service, {}).get(env, {})
            start = shape.get("incident_start")
            recovered = ctx.world.recovered_at(ctx.run_id, service, env)
            incident = bool(start) and ctx.now >= ctx.scenario.at(start) and (recovered is None or ctx.now < recovered)
            bucket = templates.get("incident" if incident else "normal", templates.get("normal", []))
            n = min(int(args.get("tail_lines", 20)), 20)
            lines = [f"{tpl['level']} {tpl['message'].replace('{latency}', '92')}" for tpl in bucket] * 10
            return {"pod": pod, "environment": env, "container": service, "lines": lines[:n]}
    raise LookupError(f"Pod {pod} not found in {env}.")


@handler("kubernetes:restart_pod")
def restart_pod(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    get_pod_logs(ctx, {"pod": args["pod"], "environment": args["environment"], "tail_lines": 1})
    ev = ctx.record("pod_restart", {"pod": args["pod"], "environment": args["environment"]}, advance_minutes=1)
    return {"pod": args["pod"], "status": "deleted; replacement scheduled", "at": ev["at"]}


@handler("kubernetes:restart_deployment")
def restart_deployment(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    _workload(ctx, args["service"], args["environment"])
    ev = ctx.record("deployment_restart", {"service": args["service"], "environment": args["environment"]}, advance_minutes=3)
    return {"service": args["service"], "environment": args["environment"], "status": "rolling restart completed", "at": ev["at"],
            "note": "Pods were replaced with the same image and configuration."}


@handler("kubernetes:rollback_deployment")
def rollback_deployment(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    service, env = args["service"], args["environment"]
    wl = _workload(ctx, service, env)
    to_version = wl["previous_image"].rsplit(":", 1)[1]
    ev = ctx.record("rollback", {"service": service, "environment": env, "to_version": to_version, "authoritative": False,
                                 "via": "kubernetes"}, advance_minutes=ctx.scenario.rollback_observe_minutes)
    return {"service": service, "environment": env, "rolled_back_to_revision": args.get("to_revision", wl["previous_revision"]),
            "image": wl["previous_image"], "at": ev["at"],
            "warning": f"Deployment is managed by {wl['managed_by']}; the next GitOps sync will re-apply the pipeline's version."}


@handler("kubernetes:scale_deployment")
def scale_deployment(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    _workload(ctx, args["service"], args["environment"])
    ev = ctx.record("scale", {"service": args["service"], "environment": args["environment"], "replicas": args["replicas"]}, advance_minutes=2)
    return {"service": args["service"], "environment": args["environment"], "replicas": args["replicas"], "at": ev["at"]}
