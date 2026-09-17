"""Model-written search queries for discovery v4.

Before retrieval, one small model call (no tool definitions) turns the request into the concrete first step, whether
that step reads or writes, and which kind of system it runs on. Retrieval then searches with that step as well as the
request, and the router uses the model's read/write judgement and system. The call is cached per request text; its
token cost is reported with every decision that uses it.

Discovery stays probabilistic; authorization does not change: whatever discovery shows, the gateway still applies
policy to the call the model makes.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

ENVIRONMENTS = ("production", "staging", "development")

# system name -> (registry domain, what it covers); the descriptions keep look-alike systems apart
SYSTEMS: dict[str, tuple[str | None, str]] = {
    "monitoring": ("observability", "service metrics, latency, error rates, throughput, dashboards, alerts, traces, "
                                    "application log search, service health"),
    "kubernetes": ("runtime", "pods, Kubernetes deployments and their rollout history, pod logs, cluster events, "
                              "restarting, scaling or rolling back Kubernetes workloads"),
    "release pipeline and code": ("delivery", "releases and deploy history of services, rolling a service back to a "
                                              "previous release, commits, diffs, CI/CD pipelines and builds"),
    "cloud": ("cloud", "VM instances, cloud tasks and other cloud resources, their status and logs, rebooting or "
                       "terminating them"),
    "incident management": ("itsm", "incident records, tickets, incident notes and comments, incident status, "
                                    "severity and resolution, past incidents, change requests"),
    "chat": ("collaboration", "chat channels and their messages, incident war rooms, posting or searching messages, "
                              "telling people something in a channel"),
    "database": ("database", "connection pools, slow queries, database sessions, database failover"),
    "feature flags": ("feature-flags", "feature flags, toggles, switching a feature on or off, rollout percentages"),
    "service catalog": ("service-catalog", "service owners and service dependencies"),
    "on-call and paging": ("incident-response", "who is on call, schedules, paging someone"),
    "status page": ("incident-communication", "public status page components and notices"),
    "runbooks and postmortems": ("knowledge", "runbook documents and postmortem documents"),
    "network": ("network", "load balancers, CDN, DNS"),
    "security": ("security", "vulnerabilities, access and security findings"),
    "business application": (None, "anything outside operations, such as CRM, HR, finance or e-commerce"),
}

_SYSTEM_LINES = "\n".join(f"  - {name}: {what}" for name, (_, what) in SYSTEMS.items())
PROMPT = f"""You turn an on-call engineer's request into a search query for a catalog of operations tools.
Do not answer the request and do not call any tool. Reply with one JSON object and nothing else:
{{"first_step": "...", "operation": "read" or "write", "system": "...", "environment": "..." or null}}

- first_step: the concrete first action the agent should take, as a short verb phrase with its object, in plain,
  standard operations terms rather than product names, slang or CLI syntax.
- operation: "write" if the first step changes anything or sends anything: restarting, scaling, rolling back,
  terminating, changing a flag, creating or updating a record, adding a note or comment, posting a message.
  Otherwise "read". When the request asks to check, investigate or decide something before acting, the first step
  is a read.
- environment: "production", "staging" or "development" if the request names or clearly implies the environment the
  first step acts on (which may differ from where the incident is); otherwise null.
- system: the system the first step runs on, exactly one of these names:
{_SYSTEM_LINES}"""


@dataclass(frozen=True)
class Rewrite:
    first_step: str
    operation: str
    system: str
    domain: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: float
    environment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QueryRewriter:
    def __init__(self, llm: Any):
        self.llm = llm
        self._cache: dict[str, Rewrite | None] = {}
        self._usage: dict[str, dict[str, Any]] = {}

    def rewrite(self, request: str) -> Rewrite | None:
        if request not in self._cache:
            self._cache[request] = self._ask(request)
        return self._cache[request]

    def usage(self, request: str) -> dict[str, Any]:
        """Tokens and time of the (cached) rewrite call for `request`, whether or not its reply was usable."""
        self.rewrite(request)
        return self._usage[request]

    def _ask(self, request: str) -> Rewrite | None:
        resp = self.llm.chat([{"role": "system", "content": PROMPT}, {"role": "user", "content": request}])
        rewrite = None if getattr(resp, "error", None) else self._parse(resp)
        self._usage[request] = {"prompt_tokens": resp.prompt_tokens, "completion_tokens": resp.completion_tokens,
                                "latency_ms": round(resp.latency_ms, 1), "usable": rewrite is not None}
        return rewrite

    @staticmethod
    def _parse(resp: Any) -> Rewrite | None:
        match = re.search(r"\{.*\}", resp.content or "", re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        first_step = str(data.get("first_step") or "").strip()
        operation = str(data.get("operation") or "").strip().lower()
        system = str(data.get("system") or "").strip().lower()
        if not first_step or operation not in ("read", "write"):
            return None
        domain = SYSTEMS[system][0] if system in SYSTEMS else None
        environment = str(data.get("environment") or "").strip().lower()
        return Rewrite(first_step, operation, system, domain, resp.prompt_tokens, resp.completion_tokens,
                       round(resp.latency_ms, 1), environment if environment in ENVIRONMENTS else None)
