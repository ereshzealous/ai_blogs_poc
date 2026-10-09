"""Policy information point: resolves the attributes a decision needs from the systems that own them.

The agent asserts nothing about itself. Everything is looked up: roles from the directory, ownership and delegations
from the relationship store, severity and state from the incident system, the change window from the change calendar,
data classification and risk from the resource catalog, and diagnosis evidence from the evidence evaluator
(authz/evidence.py), which scores only what the platform itself observed.
"""

from __future__ import annotations

import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any

from .model import Request

CONFIG = Path(__file__).resolve().parents[1] / "config"

# Where each attribute comes from. Recorded on every decision, so an auditor can tell a bad rule from a bad fact.
# Nothing here is supplied by the agent: "request" means the execution identity and the proposed call itself.
SOURCES = {
    "principal": "request", "principal.roles": "directory", "acting_for": "request", "action": "request",
    "kind": "action catalog", "risk": "action catalog", "resource": "request", "service": "resource catalog",
    "tier": "resource catalog", "data_classification": "resource catalog", "environment": "request",
    "severity": "incident system", "incident_state": "incident system", "incident_service": "incident system",
    "change_window": "change calendar", "tenant_in_scope": "incident system", "time": "platform clock",
    "evidence_score": "evidence evaluator", "evidence_signals": "evidence evaluator",
}


def load(name: str) -> dict[str, Any]:
    return tomllib.loads((CONFIG / f"{name}.toml").read_text())


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class PIP:
    def __init__(self, incidents: dict[str, dict], calendar: list[dict] | None, evidence=None):
        self.evidence = evidence  # callable(service, arguments, now) -> (score, signals); None fails closed
        self.principals = load("principals")
        self.catalog = load("catalog")
        self.relationships = load("relationships")
        self.incidents = incidents
        self.calendar = calendar

    # -- directory ------------------------------------------------------------------------------------------------
    def roles_of(self, principal: str) -> list[str]:
        p = self.principals["agents"].get(principal) or self.principals["humans"].get(principal) or {}
        return list(p.get("roles", []))

    def role_actions(self, role: str) -> list[str]:
        return self.principals["roles"].get(role, {}).get("actions", [])

    def is_human(self, principal: str) -> bool:
        return principal in self.principals["humans"]

    def principal_known(self, principal: str) -> bool:
        return principal in self.principals["agents"] or principal in self.principals["humans"]

    # -- relationships --------------------------------------------------------------------------------------------
    def related(self, subject: str, relation: str, obj: str) -> bool:
        return any(r["subject"] == subject and r["relation"] == relation and r["object"] == obj
                   for r in self.relationships["relation"])

    def delegation(self, frm: str, to: str, action: str, now: datetime) -> dict | None:
        for d in self.relationships["delegation"]:
            if d["from"] == frm and d["to"] == to and action in d["actions"] and now < ts(d["expires"]) \
                    and not d.get("revoked", False):
                return d
        return None

    # -- catalog, incidents, calendar -----------------------------------------------------------------------------
    def service_of(self, resource: str) -> str:
        kind, name = resource.split("/", 1)
        if kind == "namespace":
            return self.catalog["namespaces"].get(name, {}).get("service", "unknown")
        return name

    def resource_known(self, resource: str) -> bool:
        kind, _, name = resource.partition("/")
        if kind == "namespace":
            return name in self.catalog["namespaces"]
        return kind in self.catalog["services"].get(name, {}).get("data_classification", {})

    def environment_known(self, environment: str) -> bool:
        return environment in self.catalog["context"]["environments"]

    def severity_known(self, severity: str | None) -> bool:
        return severity in self.catalog["context"]["severities"]

    def change_window(self, environment: str, now: datetime) -> str | None:
        if self.calendar is None:  # calendar unavailable: unknown, so restrictive rules apply
            return None
        for w in self.calendar:
            if w["environment"] == environment and ts(w["start"]) <= now < ts(w["end"]):
                return "freeze"
        return "normal"

    @staticmethod
    def tenant_in_scope(incident: dict, tenant: str | None) -> bool | None:
        """None when there is no incident to compare against: the rule then fails closed."""
        scope = incident.get("tenants")
        if scope is None:
            return None
        if scope == "*":
            return True
        return tenant is not None and tenant in scope  # an unscoped query against a tenant-scoped incident crosses the boundary

    def attributes(self, req: Request) -> dict[str, Any]:
        now = ts(req.context["time"])
        kind, _ = req.resource.split("/", 1)
        service = self.service_of(req.resource)
        svc = self.catalog["services"].get(service, {})
        action = self.catalog["actions"].get(req.action)
        incident = self.incidents.get(req.context.get("incident_id", ""), {})
        tenant = req.arguments.get("tenant")
        a: dict[str, Any] = {
            "principal": req.principal,
            "principal.roles": self.roles_of(req.principal),
            "acting_for": req.acting_for,
            "action": req.action,
            "kind": action["kind"] if action else None,
            "risk": action.get("risk") if action else None,
            "resource": req.resource,
            "service": service,
            "tier": svc.get("tier"),
            "data_classification": svc.get("data_classification", {}).get(kind),
            "environment": req.environment,
            "severity": incident.get("severity"),
            "incident_state": incident.get("state"),
            "incident_service": incident.get("service"),
            "change_window": self.change_window(req.environment, now),
            "tenant_in_scope": self.tenant_in_scope(incident, tenant),
            "time": req.context["time"],
        }
        if a["risk"] == "high" and self.evidence:  # evidence gates high-risk writes only
            a["evidence_score"], a["evidence_signals"] = self.evidence(service, req.arguments, now)
        return {k: v for k, v in a.items() if v is not None or k in ("acting_for",)}
