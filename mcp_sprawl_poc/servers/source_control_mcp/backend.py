"""Mock source-control and release-pipeline backend."""

from __future__ import annotations

from typing import Any

from servers.common.handlers import Ctx, handler, require_service


def _deployments(ctx: Ctx) -> list[dict[str, Any]]:
    deps = [dict(d) for d in ctx.scenario.deployments]
    for e in ctx.world.events(ctx.run_id, "rollback"):
        p = e["payload"]
        if p.get("via") != "release-pipeline":
            continue
        deps.append({"id": p["deployment_id"], "service": p["service"], "environment": p["environment"], "version": p["to_version"],
                     "previous_version": p["from_version"], "commit": p["commit"], "release": p["release"], "change": None,
                     "strategy": "rolling", "status": "succeeded", "triggered_by": "rollback", "reason": p.get("reason"),
                     "started_at": e["at"], "finished_at": e["at"]})
    return deps


def _commit(ctx: Ctx, sha: str) -> tuple[str, dict[str, Any]]:
    for full, c in ctx.scenario.commits.items():
        if full.startswith(sha) or sha.startswith(full):
            return full, c
    raise LookupError(f"Commit {sha} not found.")


@handler("source_control:get_commit")
def get_commit(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    sha, c = _commit(ctx, args["sha"])
    return {"sha": sha, **{k: v for k, v in c.items() if k != "diff"}}


@handler("source_control:search_commits")
def search_commits(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    query = (args.get("query") or "").lower()
    hits = []
    for sha, c in ctx.scenario.commits.items():
        if c["repository"] != args["repository"]:
            continue
        if query and not any(tok in c["message"].lower() for tok in query.split()):
            continue
        if args.get("since") and c["committed_at"] < args["since"]:
            continue
        hits.append({"sha": sha, "message": c["message"], "author": c["author"], "committed_at": c["committed_at"]})
    return {"repository": args["repository"], "commits": sorted(hits, key=lambda h: h["committed_at"], reverse=True)}


@handler("source_control:get_deployment")
def get_deployment(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    for d in _deployments(ctx):
        if d["id"] == args["deployment_id"]:
            return d
    raise LookupError(f"Deployment {args['deployment_id']} not found.")


@handler("source_control:search_deployments")
def search_deployments(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    hits = [
        d for d in _deployments(ctx)
        if (not args.get("service") or d["service"] == args["service"])
        and (not args.get("environment") or d["environment"] == args["environment"])
        and (not args.get("since") or d["started_at"] >= args["since"])
    ]
    hits.sort(key=lambda d: d["started_at"], reverse=True)
    fields = ("id", "service", "environment", "version", "previous_version", "commit", "status", "started_at", "finished_at")
    return {"deployments": [{k: d[k] for k in fields} for d in hits[: int(args.get("limit", 10))]]}


@handler("source_control:get_diff")
def get_diff(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    sha, c = _commit(ctx, args["sha"])
    return {"sha": sha, "repository": c["repository"], "message": c["message"], "diff": c["diff"]}


@handler("source_control:get_release")
def get_release(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    for r in ctx.scenario.releases:
        if r["service"] == args["service"] and r["version"] == args["version"]:
            return r
    raise LookupError(f"No release {args['version']} for {args['service']}.")


@handler("source_control:rollback_release")
def rollback_release(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    service, env, to_version = args["service"], args["environment"], args["to_version"]
    require_service(ctx, service)
    current = ctx.world.current_version(ctx.run_id, service, env)
    release = next((r for r in ctx.scenario.releases if r["service"] == service and r["version"] == to_version), None)
    if release is None:
        raise LookupError(f"No release {to_version} for {service}; cannot roll back to it.")
    if current == to_version:
        raise LookupError(f"{service} in {env} is already running {to_version}.")
    seq = len(ctx.world.events(ctx.run_id, "rollback"))
    dep_id = f"DEP-{88240 + seq}"
    ev = ctx.record("rollback", {"service": service, "environment": env, "to_version": to_version, "from_version": current,
                                 "commit": release["commit"], "release": release["id"], "deployment_id": dep_id,
                                 "authoritative": True, "via": "release-pipeline", "reason": args.get("reason")},
                    advance_minutes=ctx.scenario.rollback_observe_minutes)
    return {"deployment_id": dep_id, "service": service, "environment": env, "from_version": current, "to_version": to_version,
            "status": "succeeded", "started_at": ev["at"], "observed_until": ctx.now_iso}
