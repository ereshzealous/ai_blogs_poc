"""Mock ITSM backend: incidents and change requests; writes are recorded as world events."""

from __future__ import annotations

from typing import Any

from servers.common.handlers import Ctx, handler


def _incident(ctx: Ctx, incident_id: str) -> dict[str, Any]:
    for inc in ctx.scenario.incidents:
        if inc["id"] == incident_id:
            record = dict(inc)
            break
    else:
        raise LookupError(f"Incident {incident_id} not found.")
    record["comments"] = []
    for e in ctx.world.events(ctx.run_id):
        p = e["payload"]
        if p.get("incident_id") != incident_id:
            continue
        if e["kind"] == "incident_update":
            record.update({k: v for k, v in p["fields"].items() if v is not None})
            record["updated_at"] = e["at"]
        elif e["kind"] == "incident_comment":
            record["comments"].append({"at": e["at"], "visibility": p["visibility"], "comment": p["comment"]})
        elif e["kind"] == "incident_close":
            record.update(status="closed", resolution_code=p["resolution_code"], closed_at=e["at"])
        elif e["kind"] == "change_create":
            record["linked_changes"] = [*record.get("linked_changes", []), p["change_id"]]
    return record


@handler("itsm:get_incident")
def get_incident(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    return _incident(ctx, args["incident_id"])


@handler("itsm:search_incidents")
def search_incidents(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    query = (args.get("query") or "").lower()
    status = args.get("status", "any")
    hits = []
    for inc in ctx.scenario.incidents:
        rec = _incident(ctx, inc["id"])
        text = f"{rec['title']} {rec['description']} {rec['service']}".lower()
        if query and not any(tok in text for tok in query.split()):
            continue
        if args.get("service") and rec["service"] != args["service"]:
            continue
        if args.get("severity") and rec["severity"] != args["severity"]:
            continue
        if status != "any" and not (rec["status"] == status or (status == "open" and rec["status"] in ("open", "investigating"))):
            continue
        hits.append({k: rec[k] for k in ("id", "title", "severity", "status", "service", "opened_at")})
    hits.sort(key=lambda r: r["opened_at"], reverse=True)
    return {"incidents": hits[: int(args.get("limit", 10))]}


@handler("itsm:update_incident")
def update_incident(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    _incident(ctx, args["incident_id"])
    fields = {k: args.get(k) for k in ("status", "severity", "summary", "root_cause", "resolution_notes")}
    ev = ctx.record("incident_update", {"incident_id": args["incident_id"], "fields": fields})
    return {"incident_id": args["incident_id"], "updated": {k: v for k, v in fields.items() if v is not None}, "at": ev["at"]}


@handler("itsm:add_incident_comment")
def add_incident_comment(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    _incident(ctx, args["incident_id"])
    ev = ctx.record("incident_comment", {"incident_id": args["incident_id"], "comment": args["comment"],
                                         "visibility": args.get("visibility", "work_note")})
    return {"incident_id": args["incident_id"], "comment_added": True, "at": ev["at"]}


@handler("itsm:create_change")
def create_change(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    seq = len(ctx.world.events(ctx.run_id, "change_create"))
    change_id = f"CHG-{30120 + seq}"
    ctx.record("change_create", {"change_id": change_id, "incident_id": args.get("linked_incident"), **args})
    return {"change_id": change_id, "state": "assess" if args["change_type"] != "emergency" else "authorize", "service": args["service"]}


@handler("itsm:close_incident")
def close_incident(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    _incident(ctx, args["incident_id"])
    ev = ctx.record("incident_close", {"incident_id": args["incident_id"], "resolution_code": args["resolution_code"],
                                       "resolution_notes": args.get("resolution_notes")})
    return {"incident_id": args["incident_id"], "status": "closed", "at": ev["at"]}
