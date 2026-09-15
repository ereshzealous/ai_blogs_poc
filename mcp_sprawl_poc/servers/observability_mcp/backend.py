"""Mock observability backend: deterministic metrics, logs, traces and alerts for INC-4917."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from servers.common.handlers import Ctx, handler, require_service
from servers.common.scenario import metric_value, parse_window, series, summarize

MAX_POINTS = 12


def _env(args: dict[str, Any]) -> str:
    return args.get("environment", "production")


def _downsample(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(points) <= MAX_POINTS:
        return points
    step = -(-len(points) // MAX_POINTS)
    return points[::step]


def _metric(ctx: Ctx, service: str, env: str, metric: str, time_range: str | None) -> dict[str, Any]:
    require_service(ctx, service)
    window = parse_window(time_range)
    recovered = ctx.world.recovered_at(ctx.run_id, service, env)
    pts = series(ctx.scenario, service, env, metric, ctx.now, window, recovered)
    out: dict[str, Any] = {
        "service": service,
        "environment": env,
        "metric": metric,
        "window": time_range or "15m",
        "end": ctx.now_iso,
    }
    if not pts:
        out["note"] = f"No data for {metric} on {service} in {env}."
        return out
    out["summary"] = summarize(pts)
    out["series"] = _downsample(pts)
    return out


def _in_incident(ctx: Ctx, service: str, env: str, minute) -> bool:
    shape = ctx.scenario.metrics.get(service, {}).get(env, {})
    start = shape.get("incident_start")
    if not start or minute < ctx.scenario.at(start):
        return False
    recovered = ctx.world.recovered_at(ctx.run_id, service, env)
    return recovered is None or minute < recovered


@handler("observability:query_metrics")
def query_metrics(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    return _metric(ctx, args["service"], _env(args), args["metric"], args.get("time_range"))


@handler("observability:query_latency")
def query_latency(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    service, env, pct = args["service"], _env(args), args["percentile"]
    base = "latency_p50_ms" if pct == "p50" else "latency_p95_ms"
    out = _metric(ctx, service, env, base, args.get("time_range"))
    if pct == "p99" and "series" in out:  # p99 is modelled as 1.4x p95 in this scenario
        for p in out["series"]:
            p["value"] = round(p["value"] * 1.4)
        out["summary"] = {k: (round(v * 1.4) if k != "points" else v) for k, v in out["summary"].items()}
    out["metric"] = f"latency_{pct}_ms"
    out["slo_p95_ms"] = ctx.scenario.services[service]["slo"]["p95_latency_ms"]
    return out


@handler("observability:query_error_rate")
def query_error_rate(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    return _metric(ctx, args["service"], _env(args), "error_rate_pct", args.get("time_range"))


@handler("observability:search_logs")
def search_logs(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    service, env = args["service"], _env(args)
    require_service(ctx, service)
    templates = ctx.scenario.logs.get(service, {}).get(env)
    window = parse_window(args.get("time_range"))
    out: dict[str, Any] = {"service": service, "environment": env, "window": args.get("time_range", "15m"), "end": ctx.now_iso}
    if not templates:
        return out | {"total_matches": 0, "patterns": []}
    counts: dict[tuple[str, str], int] = {}
    samples: list[dict[str, Any]] = []
    t = (ctx.now - window).replace(second=0)
    while t <= ctx.now:
        bucket = "incident" if _in_incident(ctx, service, env, t) and "incident" in templates else "normal"
        latency = metric_value(ctx.scenario, service, env, "latency_p50_ms", t, ctx.world.recovered_at(ctx.run_id, service, env)) or 0
        for i, tpl in enumerate(templates[bucket]):
            msg = tpl["message"].replace("{latency}", str(int(latency)))
            n = (40 if tpl["level"] == "ERROR" else 25) if bucket == "incident" else 60 - 10 * i
            counts[(tpl["level"], tpl["message"].replace("{latency}", "<n>"))] = counts.get((tpl["level"], tpl["message"].replace("{latency}", "<n>")), 0) + n
            if len(samples) < 60:
                samples.append({"t": t.strftime("%H:%M:%S"), "level": tpl["level"], "pod": _pod(ctx, service, env, i), "message": msg})
        t += timedelta(minutes=1)
    level, query = args.get("level"), (args.get("query") or "").lower()

    def keep(lvl: str, msg: str) -> bool:
        if level and lvl != level:
            return False
        return not query or any(tok in msg.lower() for tok in query.split())

    patterns = sorted(
        ({"level": lvl, "message": msg, "count": n} for (lvl, msg), n in counts.items() if keep(lvl, msg)),
        key=lambda p: -p["count"],
    )
    return out | {
        "total_matches": sum(p["count"] for p in patterns),
        "patterns": patterns[:5],
        "samples": [s for s in samples if keep(s["level"], s["message"])][-4:],
    }


def _pod(ctx: Ctx, service: str, env: str, i: int) -> str:
    pods = ctx.scenario.kubernetes.get(service, {}).get(env, {}).get("pods", [])
    return pods[i % len(pods)]["name"] if pods else f"{service}-0"


@handler("observability:get_trace")
def get_trace(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    for trace in ctx.scenario.traces.values():
        if trace["trace_id"] == args["trace_id"]:
            return trace
    raise LookupError(f"Trace {args['trace_id']} not found (traces are retained for 7 days).")


@handler("observability:search_traces")
def search_traces(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    service, env = args["service"], _env(args)
    require_service(ctx, service)
    min_ms = int(args.get("min_duration_ms", 0))
    found = []
    if service == "checkout-api" and env == "production":
        slow_active = _in_incident(ctx, service, env, ctx.now - timedelta(minutes=1))
        candidates = [ctx.scenario.traces["slow_example"]] if slow_active else []
        candidates.append(ctx.scenario.traces["baseline_example"])
        for tr in candidates:
            if tr["duration_ms"] >= min_ms:
                slowest = max(tr["spans"], key=lambda s: s["duration_ms"])
                found.append({"trace_id": tr["trace_id"], "root": tr["root"], "started_at": tr["started_at"],
                              "duration_ms": tr["duration_ms"], "slowest_span": slowest})
    return {"service": service, "environment": env, "min_duration_ms": min_ms, "traces": found}


def _firing(ctx: Ctx) -> list[dict[str, Any]]:
    alerts = []
    for a in ctx.scenario.alerts:
        a = dict(a)
        if a["state"] == "firing":
            rec = ctx.world.recovered_at(ctx.run_id, a["service"], a["environment"])
            if rec is not None and rec + timedelta(minutes=2) <= ctx.now:
                a["state"], a["resolved_at"] = "resolved", (rec + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        alerts.append(a)
    return alerts


@handler("observability:get_alerts")
def get_alerts(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    state = args.get("state", "any")
    alerts = [
        a for a in _firing(ctx)
        if (not args.get("service") or a["service"] == args["service"])
        and (not args.get("environment") or a["environment"] == args["environment"])
        and (state == "any" or a["state"] == state)
    ]
    return {"alerts": alerts, "as_of": ctx.now_iso}


@handler("observability:get_service_health")
def get_service_health(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    service, env = args["service"], _env(args)
    svc = require_service(ctx, service)
    recovered = ctx.world.recovered_at(ctx.run_id, service, env)
    minute = ctx.now.replace(second=0)
    p95 = metric_value(ctx.scenario, service, env, "latency_p95_ms", minute, recovered)
    err = metric_value(ctx.scenario, service, env, "error_rate_pct", minute, recovered)
    firing = [a["name"] for a in _firing(ctx) if a["service"] == service and a["environment"] == env and a["state"] == "firing"]
    slo = svc["slo"]
    if p95 is None:
        return {"service": service, "environment": env, "status": "unknown", "note": "no telemetry"}
    status = "healthy" if p95 <= slo["p95_latency_ms"] and err < 1 else "degraded"
    return {"service": service, "environment": env, "status": status, "latency_p95_ms": p95,
            "slo_p95_ms": slo["p95_latency_ms"], "error_rate_pct": err, "firing_alerts": firing, "as_of": ctx.now_iso}


@handler("observability:get_dashboard")
def get_dashboard(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    service, env = args["service"], _env(args)
    require_service(ctx, service)
    recovered = ctx.world.recovered_at(ctx.run_id, service, env)
    minute = ctx.now.replace(second=0)
    panels = {}
    for m in ["latency_p95_ms", "error_rate_pct", "requests_per_second", "cpu_utilization_pct", "db_pool_acquire_wait_p95_ms"]:
        v = metric_value(ctx.scenario, service, env, m, minute, recovered)
        if v is not None:
            panels[m] = v
    return {"dashboard": f"{service} / golden signals", "environment": env, "as_of": ctx.now_iso, "panels": panels}
