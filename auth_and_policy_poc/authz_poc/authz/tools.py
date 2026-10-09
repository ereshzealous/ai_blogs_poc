"""Simulated execution tools. They know nothing about policy, on purpose: a tool can check a credential, not a context.

Each tool is exposed as a ProtectedTool: an endpoint that redeems a broker-issued, call-scoped credential before any
effect (authz/broker.py). Calling one without that credential, as an agent runtime trying to skip the gateway would,
fails before anything happens.
"""

from __future__ import annotations

import re
from typing import Any, Callable


class Kubernetes:
    def __init__(self) -> None:
        self.deployments = {
            ("payment-service", "production"): {"version": "v4.18.0", "previous": "v4.17.2", "replicas": 6,
                                                "deployed_at": "2026-09-29T13:49:00Z"},
            ("payment-service", "staging"): {"version": "v4.18.0", "previous": "v4.17.2", "replicas": 2,
                                             "deployed_at": "2026-09-29T13:31:00Z"},
            ("checkout-service", "production"): {"version": "v2.9.1", "previous": "v2.9.0", "replicas": 4,
                                                 "deployed_at": "2026-09-22T10:12:00Z"},
        }
        self.namespaces = {"payments", "payments-staging", "payments-canary"}
        self.restarted: list[str] = []

    def readDeployment(self, service: str, environment: str, **_: Any) -> dict:
        d = self.deployments[(service, environment)]
        return {"service": service, "environment": environment, "version": d["version"], "replicas": d["replicas"]}

    def readPods(self, service: str, environment: str, **_: Any) -> dict:
        n = self.deployments[(service, environment)]["replicas"]
        return {"pods": [f"{service}-7f9c-{i}" for i in range(1, n + 1)], "crashloop": 2 if environment == "production" else 0}

    def restartPod(self, service: str, environment: str, pods: list[str], **_: Any) -> dict:
        self.restarted += pods
        return {"restarted": pods}

    def rollbackDeployment(self, service: str, environment: str, to_version: str, **_: Any) -> dict:
        d = self.deployments[(service, environment)]
        d["version"], d["previous"] = to_version, d["version"]
        return {"rolled_back_to": to_version}

    def deleteNamespace(self, namespace: str, **_: Any) -> dict:
        self.namespaces.discard(namespace)
        return {"deleted": namespace}


class Logs:
    LINES = [
        "14:01:52 ERROR payment-service charge failed: upstream timeout card_number=4111111111111111 email=j.doe@example.com",
        "14:01:57 ERROR payment-service pool exhausted after v4.18.0 config change maxConnections=8",
        "14:02:03 WARN  payment-service retry storm tenant=acme card_number=5500005555555559",
    ]
    PATTERNS = {"card_number": r"card_number=\d+", "email": r"email=\S+"}

    def query(self, service: str, environment: str, redact: list[str] | None = None, **_: Any) -> dict:
        lines = list(self.LINES)
        for field in redact or []:
            lines = [re.sub(self.PATTERNS[field], f"{field}=[REDACTED]", l) for l in lines]
        return {"lines": lines}


class Dashboards:
    """Monitoring. Error rate follows the deployed version: v4.18.0 of payment-service is the bad release."""

    BAD = {("payment-service", "v4.18.0")}

    def __init__(self, k8s: Kubernetes):
        self.k8s = k8s

    def error_rate(self, service: str, environment: str) -> float:
        version = self.k8s.deployments[(service, environment)]["version"]
        return 14.0 if (service, version) in self.BAD else 0.4

    def healthy(self, service: str, environment: str) -> bool:
        return self.error_rate(service, environment) < 1.0  # the SLO

    def read(self, service: str, environment: str = "production", **_: Any) -> dict:
        return {"error_rate": f"{self.error_rate(service, environment)}%", "slo": "1%"}


class ProtectedTool:
    """A tool endpoint. It accepts a call only with a credential the broker issued for exactly that call."""

    def __init__(self, action: str, fn: Callable[..., dict], broker, service_of: Callable[[str], str]):
        self.action, self.fn, self.broker, self.service_of = action, fn, broker, service_of
        self.calls = 0  # effects actually performed

    def __call__(self, *, resource: str, environment: str, now: str, credential: dict | None = None, **arguments: Any) -> dict:
        self.broker.redeem(credential, self.action, resource, environment, arguments, now)  # raises before any effect
        self.calls += 1
        return self.fn(service=self.service_of(resource), environment=environment, **arguments)


def registry(broker, service_of: Callable[[str], str]) -> dict[str, Any]:
    """Protected endpoints by action name, plus the raw systems (underscored) that the platform itself observes:
    the evidence evaluator reads deployments and dashboards directly, as a monitoring system would. The agent gets
    neither: it only ever talks to the gateway."""
    k8s, logs = Kubernetes(), Logs()
    dash = Dashboards(k8s)
    raw = {
        "kubernetes.readDeployment": k8s.readDeployment,
        "kubernetes.readPods": k8s.readPods,
        "kubernetes.restartPod": k8s.restartPod,
        "kubernetes.rollbackDeployment": k8s.rollbackDeployment,
        "kubernetes.deleteNamespace": k8s.deleteNamespace,
        "logs.query": logs.query,
        "dashboards.read": dash.read,
    }
    tools: dict[str, Any] = {a: ProtectedTool(a, fn, broker, service_of) for a, fn in raw.items()}
    tools.update({"_k8s": k8s, "_dashboards": dash, "_logs": logs})
    return tools
