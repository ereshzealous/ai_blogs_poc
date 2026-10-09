"""The agents.  Deterministic stand-ins for model-driven reasoning: each proposes capability calls and nothing else.

An agent holds no credential, imports no tool, and never sees a token.  It proposes; the platform carries identity.
F3 showed the reasoning side; T1 is about the identity side, so the plans are fixed on purpose.
"""

from __future__ import annotations

from aid.contracts import CapabilityCall

ROLLBACK = CapabilityCall(capability="rollbackDeployment",
                          arguments={"service": "payment-service", "environment": "production", "to_version": "v4.17.2"})


class IncidentIntel:
    name = "agent.incident-intel"

    def investigate(self) -> list[CapabilityCall]:
        return [CapabilityCall(capability="getErrorRate", arguments={"service": "payment-service"}),
                CapabilityCall(capability="getDeployments", arguments={"service": "payment-service"}),
                CapabilityCall(capability="updateIncident", arguments={"incident": "INC-4102", "note": "v4.18.0 suspected"}),
                CapabilityCall(capability="postMessage", arguments={"channel": "#inc-payments", "text": "rollback proposed"})]

    def remediate(self) -> CapabilityCall:
        return ROLLBACK


class Remediation:
    name = "agent.remediation"

    def plan(self) -> list[CapabilityCall]:
        return [CapabilityCall(capability="restartPods", arguments={"service": "payment-service", "environment": "production"})]


class ReleaseGuard:
    name = "agent.release-guard"

    def check(self) -> list[CapabilityCall]:
        return [CapabilityCall(capability="getDeployments", arguments={"service": "payment-service"}),
                CapabilityCall(capability="getErrorRate", arguments={"service": "payment-service"})]

    def ask_incident_intel_to_roll_back(self) -> CapabilityCall:
        return ROLLBACK
