"""Head adapters: translate each consumer's native payload into the one InvocationEnvelope.

Channels translate; they never reason.  This module imports only the contracts (an architecture test enforces it),
so a head cannot reach a model, a capability, the state store or the world.  The invoker is always the principal
ingress authenticated, never a name taken from the payload.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from hai.contracts import InvocationEnvelope, Subject

SVC = re.compile(r"\b([a-z][a-z0-9]*(?:-[a-z0-9]+)*-service|payment[- ]?service|paymentservice)\b", re.I)


def _fp(service: str, environment: str) -> str:
    """The situation key: every head that asks about the same degradation lands on the same fingerprint."""
    return f"degradation:{service}:{environment}"


def _norm_service(s: str) -> str:
    s = s.lower().replace(" ", "-")
    return "payment-service" if s in ("paymentservice", "payment-service", "payment-service") else s


def event(p: dict[str, Any], principal: str, corr: Callable[[str], str]) -> InvocationEnvelope:
    """A monitoring webhook (Datadog-style monitor alert)."""
    tags = dict(t.split(":", 1) for t in p["tags"])
    svc, env = tags["service"], tags["env"]
    return InvocationEnvelope(event_id=p["id"], source=f"monitoring/{p.get('source', 'monitor')}", channel="event", intent="investigate_incident",
                              subject=Subject(service=svc, environment=env, signal={p["metric"]: p["value"], "monitor_id": p["monitor_id"]}),
                              fingerprint=_fp(svc, env), invoker=principal, correlation_id=corr(_fp(svc, env)), causation_id=p["id"],
                              reply_to="#payments-incidents")


def chat(p: dict[str, Any], principal: str, corr: Callable[[str], str]) -> InvocationEnvelope:
    """A chat message (Slack-style).  The question is kept; the service is parsed from it."""
    m = SVC.search(p["text"])
    svc = _norm_service(m.group(1)) if m else p.get("service", "unknown-service")
    env = "staging" if "staging" in p["text"].lower() else "production"
    return InvocationEnvelope(event_id=p["event_id"], source=f"chat/{p.get('workspace', 'slack')}", channel="chat", intent="investigate_incident",
                              subject=Subject(service=svc, environment=env), fingerprint=_fp(svc, env), invoker=principal,
                              correlation_id=corr(_fp(svc, env)), causation_id=p["event_id"], reply_to=f"{p['channel']}:{p['ts']}", question=p["text"])


def web(p: dict[str, Any], principal: str, corr: Callable[[str], str]) -> InvocationEnvelope:
    """The web console: the portal is the authenticated workload; the signed-in user is the human it acts for."""
    return InvocationEnvelope(event_id=p["request_id"], source="web/console", channel="web", intent="investigate_incident",
                              subject=Subject(service=p["service"], environment=p["environment"]), fingerprint=_fp(p["service"], p["environment"]),
                              invoker=principal, on_behalf_of=p["session_user"], correlation_id=corr(_fp(p["service"], p["environment"])),
                              causation_id=p["request_id"], reply_to="page")


def api(p: dict[str, Any], principal: str, corr: Callable[[str], str]) -> InvocationEnvelope:
    return InvocationEnvelope(event_id=p["request_id"], source="api/v1", channel="api", intent="investigate_incident",
                              subject=Subject(service=p["service"], environment=p["environment"]), fingerprint=_fp(p["service"], p["environment"]),
                              invoker=principal, correlation_id=corr(_fp(p["service"], p["environment"])), causation_id=p["request_id"],
                              question=p.get("question"))


def workflow(p: dict[str, Any], principal: str, corr: Callable[[str], str]) -> InvocationEnvelope:
    return InvocationEnvelope(event_id=f"{p['workflow_run_id']}:{p['step']}", source="workflow/engine", channel="workflow", intent="investigate_incident",
                              subject=Subject(service=p["service"], environment=p["environment"]), fingerprint=_fp(p["service"], p["environment"]),
                              invoker=principal, correlation_id=corr(_fp(p["service"], p["environment"])), causation_id=p["workflow_run_id"],
                              reply_to=p.get("callback"))


def scheduler(p: dict[str, Any], principal: str, corr: Callable[[str], str]) -> InvocationEnvelope:
    fp = f"sweep:{p['service']}:{p['environment']}:{p['tick']}"
    return InvocationEnvelope(event_id=f"{p['schedule']}:{p['tick']}", source="scheduler/cron", channel="scheduler", intent="health_sweep",
                              subject=Subject(service=p["service"], environment=p["environment"]), fingerprint=fp, invoker=principal,
                              correlation_id=corr(fp), causation_id=p["schedule"])


def cicd(p: dict[str, Any], principal: str, corr: Callable[[str], str]) -> InvocationEnvelope:
    fp = f"release:{p['service']}:{p['environment']}:{p['candidate']}"
    return InvocationEnvelope(event_id=p["pipeline_id"], source="cicd/pipeline", channel="cicd", intent="release_check",
                              subject=Subject(service=p["service"], environment=p["environment"], signal={"candidate": p["candidate"]}),
                              fingerprint=fp, invoker=principal, correlation_id=corr(fp), causation_id=p["pipeline_id"])


def agent(p: dict[str, Any], principal: str, corr: Callable[[str], str]) -> InvocationEnvelope:
    """Agent-to-agent: another agent asks for a skill.  It is a consumer with its own identity, like any other head."""
    i = p["input"]
    fp = f"release:{i['service']}:{i['environment']}:{i['candidate']}"
    return InvocationEnvelope(event_id=p["task_id"], source=f"agent/{principal}", channel="agent", intent="release_check",
                              subject=Subject(service=i["service"], environment=i["environment"], signal={"candidate": i["candidate"]}),
                              fingerprint=fp, invoker=principal, correlation_id=corr(fp), causation_id=p.get("parent_task_id") or p["task_id"])


ADAPTERS: dict[str, Callable[[dict[str, Any], str, Callable[[str], str]], InvocationEnvelope]] = {
    "event": event, "chat": chat, "web": web, "api": api, "workflow": workflow, "scheduler": scheduler, "cicd": cicd, "agent": agent,
}
