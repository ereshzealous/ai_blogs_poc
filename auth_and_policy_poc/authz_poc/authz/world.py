"""Build the incident world: tools, credential broker, audit log, evidence evaluator, PIP, PDP, approval gate, gateway.

Everything is deterministic: the clock is the scenario's, ids are content digests, the broker key is fixed.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from .approvals import ApprovalGate
from .audit import AuditLog
from .broker import CredentialBroker
from .evidence import Evidence
from .model import Request
from .pdp import PDP
from .pep import Gateway
from .pip import PIP
from .tools import registry

ROOT = Path(__file__).resolve().parents[1]
T = "2026-09-29T14:07:30Z"


def scenario() -> dict:
    return tomllib.loads((ROOT / "scenario.toml").read_text())


def world(incident_overrides: dict | None = None, evidence=None, no_evidence: bool = False, calendar="scenario") -> Gateway:
    """incident_overrides patches the incident record; a value of None removes the field (unknown context).
    calendar=None models an unavailable change calendar."""
    scn = scenario()
    inc = {**scn["incident"], **(incident_overrides or {})}
    inc = {k: v for k, v in inc.items() if v is not None}
    audit, broker = AuditLog(), CredentialBroker()
    pip_holder: list[PIP] = []
    tools = registry(broker, lambda resource: pip_holder[0].service_of(resource))
    ev = None if no_evidence else evidence or Evidence(tools["_k8s"], tools["_dashboards"], audit, inc)
    pip = PIP({inc["id"]: inc}, scn["freeze"] if calendar == "scenario" else calendar, ev)
    pip_holder.append(pip)
    return Gateway(PDP(pip), ApprovalGate(pip), tools, audit, broker)


def request(action: str, resource: str, env: str = "production", acting_for: str | None = "sre-team",
            principal: str = "incident-agent-prod", time: str = T, context: dict | None = None, **arguments) -> Request:
    """context adds keys to the runtime-bound context (time, incident id); tests use it to inject agent assertions."""
    return Request(principal, acting_for, action, resource, env,
                   {"time": time, "incident_id": "INC-4471", **(context or {})}, arguments)
