"""Diagnosis evidence, computed by the platform from independent, observed signals.

The agent is never asked how confident it is. Self-reported model confidence moves with phrasing and calibration, and
an agent that grades its own homework could talk a production write into eligibility. Instead, each signal below is
something the platform itself observed, in a system of record, before the moment of the decision:

    release_correlation  0.35  production changed shortly before the incident, and the call reverts exactly that change
    error_signature      0.27  logs the platform returned (via the gateway) name the suspect release
    staging_validation   0.22  the same fix was applied in staging, through the gateway
    staging_recovery     0.10  staging health recovered afterwards, per the monitoring system

diagnosis_evidence_score is the sum of the weights of the signals present.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .pip import ts

WEIGHTS = {"release_correlation": 0.35, "error_signature": 0.27, "staging_validation": 0.22, "staging_recovery": 0.10}
RELEASE_WINDOW = timedelta(minutes=30)


class Evidence:
    def __init__(self, k8s, dashboards, audit, incident: dict[str, Any]):
        self.k8s, self.dashboards, self.audit, self.incident = k8s, dashboards, audit, incident

    def __call__(self, service: str, arguments: dict[str, Any], now) -> tuple[float, list[str]]:
        target = arguments.get("to_version")
        prod = self.k8s.deployments.get((service, "production"))
        opened = ts(self.incident["opened"])
        observed = [r["record"] for r in self.audit.records if r["kind"] == "tool.executed" and ts(r["time"]) <= now]
        signals = {
            "release_correlation": bool(prod) and opened - RELEASE_WINDOW <= ts(prod["deployed_at"]) <= opened
                                   and (target is None or target == prod["previous"]),
            "error_signature": bool(prod) and any(
                r["action"] == "logs.query" and r["resource"] == f"logs/{service}"
                and any(prod["version"] in line for line in r["output"]["lines"]) for r in observed),
            "staging_validation": target is not None and any(
                r["action"] == "kubernetes.rollbackDeployment" and r["environment"] == "staging"
                and r["resource"] == f"deployment/{service}" and r["arguments"].get("to_version") == target for r in observed),
        }
        signals["staging_recovery"] = signals["staging_validation"] and self.dashboards.healthy(service, "staging")
        present = [k for k, v in signals.items() if v]
        return round(sum(WEIGHTS[k] for k in present), 2), present


def fixed(signals: list[str]):
    """A stand-in evaluator for counterfactuals (the context sweep): the listed signals, regardless of the log."""
    return lambda service, arguments, now: (round(sum(WEIGHTS[k] for k in signals), 2), list(signals))
