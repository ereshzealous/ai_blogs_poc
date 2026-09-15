"""itsm-mcp: incidents and change records in the IT service management system."""

from servers.common.meta import registry_record
from servers.common.toolspec import ENVIRONMENT, SERVICE, ToolSpec, schema

S = "itsm"
OWNER = "it-service-management"
INCIDENT_ID = {"type": "string", "pattern": "^INC-[0-9]{4,6}$", "description": "Incident number, e.g. INC-4917."}


def _meta(capability: str, ops: list[str], risk: str, scopes: list[str], authoritative: list[str] | None = None) -> dict:
    return registry_record(domain="itsm", capability=capability, resource_type="incident" if "change" not in capability else "change-request",
                           operations=ops, risk=risk, owner=OWNER, scopes=scopes, authoritative_for=authoritative)


TOOLS = [
    ToolSpec(
        S, "get_incident",
        "Get an incident record by number: title, severity, status, affected service, timeline, linked alerts, "
        "linked changes, comments and updates.",
        schema({"incident_id": INCIDENT_ID}, ["incident_id"]),
        title="Get incident", read_only_hint=True, open_world_hint=False, handler="itsm:get_incident",
        collision_group="incident-lookup", registry=_meta("incident-read", ["get"], "READ_ONLY", ["itsm.incident.read"], ["incident"]),
    ),
    ToolSpec(
        S, "search_incidents",
        "Search incidents by free text, affected service, status and severity. Returns incident numbers with "
        "titles and status, newest first.",
        schema({"query": {"type": "string"}, "service": SERVICE,
                "status": {"type": "string", "enum": ["open", "investigating", "resolved", "closed", "any"]},
                "severity": {"type": "string", "enum": ["SEV1", "SEV2", "SEV3", "SEV4"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, []),
        title="Search incidents", read_only_hint=True, open_world_hint=False, handler="itsm:search_incidents",
        collision_group="incident-lookup", registry=_meta("incident-search", ["search"], "READ_ONLY", ["itsm.incident.read"], ["incident"]),
    ),
    ToolSpec(
        S, "update_incident",
        "Update fields on an existing incident: status, severity, summary, suspected root cause and "
        "resolution notes. Changes are visible to everyone following the incident.",
        schema({"incident_id": INCIDENT_ID,
                "status": {"type": "string", "enum": ["investigating", "identified", "monitoring", "resolved"]},
                "severity": {"type": "string", "enum": ["SEV1", "SEV2", "SEV3", "SEV4"]},
                "summary": {"type": "string"}, "root_cause": {"type": "string"}, "resolution_notes": {"type": "string"}},
               ["incident_id"]),
        title="Update incident", read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False,
        handler="itsm:update_incident", collision_group="incident-update",
        registry=_meta("incident-update", ["update"], "LOW_RISK_WRITE", ["itsm.incident.write"], ["incident"]),
    ),
    ToolSpec(
        S, "add_incident_comment",
        "Add a work note or customer-visible comment to an incident's activity stream without changing its fields.",
        schema({"incident_id": INCIDENT_ID, "comment": {"type": "string", "minLength": 1},
                "visibility": {"type": "string", "enum": ["work_note", "customer_visible"]}}, ["incident_id", "comment"]),
        title="Add incident comment", read_only_hint=False, destructive_hint=False, open_world_hint=False,
        handler="itsm:add_incident_comment", collision_group="incident-update",
        registry=_meta("incident-comment", ["comment"], "LOW_RISK_WRITE", ["itsm.incident.write"], ["incident"]),
    ),
    ToolSpec(
        S, "create_change",
        "Create a change request (standard, normal or emergency) for a service and environment, optionally "
        "linked to an incident. Required before planned production changes.",
        schema({"service": SERVICE, "environment": ENVIRONMENT,
                "change_type": {"type": "string", "enum": ["standard", "normal", "emergency"]},
                "summary": {"type": "string"}, "linked_incident": INCIDENT_ID}, ["service", "environment", "change_type", "summary"]),
        title="Create change request", read_only_hint=False, destructive_hint=False, open_world_hint=False,
        handler="itsm:create_change", collision_group="change-management",
        registry=_meta("change-create", ["create"], "LOW_RISK_WRITE", ["itsm.change.write"], ["change-request"]),
    ),
    ToolSpec(
        S, "close_incident",
        "Close an incident with a resolution code and resolution notes. Closed incidents leave the active queue "
        "and trigger the post-incident review workflow.",
        schema({"incident_id": INCIDENT_ID,
                "resolution_code": {"type": "string", "enum": ["fixed", "rolled_back", "workaround", "no_action", "duplicate"]},
                "resolution_notes": {"type": "string"}}, ["incident_id", "resolution_code"]),
        title="Close incident", read_only_hint=False, destructive_hint=False, open_world_hint=False,
        handler="itsm:close_incident", collision_group="incident-update",
        registry=_meta("incident-close", ["close"], "LOW_RISK_WRITE", ["itsm.incident.close"], ["incident"]),
    ),
]
