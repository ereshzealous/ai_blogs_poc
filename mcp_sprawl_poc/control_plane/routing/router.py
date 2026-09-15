"""Intent / domain router: a transparent lexicon + rules classifier.

It answers four questions about a request before any tool is retrieved: which domains are involved,
is the operation a read or a write, which environment, which service. It is deliberately simple and
inspectable; every decision lists the terms that caused it. The lexicon was written from the domain
definitions before the benchmark cases, and may only be tuned on the `dev` split.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DOMAIN_LEXICON: dict[str, list[str]] = {
    "observability": ["latency", "p50", "p95", "p99", "percentile", "slow", "error rate", "errors", "5xx", "timeout", "metric",
                      "metrics", "log", "logs", "trace", "traces", "span", "alert", "alerts", "dashboard", "throughput",
                      "cpu", "memory", "health", "healthy", "degraded", "slo", "exception", "requests per second"],
    "itsm": ["incident", "inc-", "ticket", "severity", "sev1", "sev2", "sev3", "change request", "resolution",
             "work note", "postmortem", "close the incident", "incident record"],
    "runtime": ["pod", "pods", "kubernetes", "k8s", "container", "replica", "replicas", "namespace", "node", "cluster",
                "kubectl", "rollout", "oomkilled", "crashloop", "scale"],
    "delivery": ["deploy", "deployed", "deployment", "deployments", "release", "releases", "rollback", "roll back",
                 "commit", "commits", "diff", "version", "pipeline", "changed in", "code change", "shipped"],
    "cloud": ["instance", "vm", "virtual machine", "task", "cloud", "provider", "region", "managed database",
              "orders-db", "resource", "reboot", "terminate"],
    "collaboration": ["channel", "slack", "chat", "message", "post", "announce", "notify the team", "tell the team"],
    "database": ["connection pool", "pool", "connections", "database", "db", "query", "queries", "session", "failover", "sql"],
    "feature-flags": ["flag", "flags", "feature flag", "toggle", "rollout percentage", "kill switch", "feature"],
    "service-catalog": ["owner", "owns", "ownership", "owning team", "dependencies", "depends on", "cmdb", "configuration item"],
}

WRITE_PATTERNS = [
    r"\broll(?:ing)? ?back\b", r"\brollback\b", r"\brevert\b", r"\brestart\b", r"\breboot\b", r"\bscale\b", r"\bupdate\b",
    r"\bclose\b", r"\bcreate\b", r"\bopen a\b", r"\bpost\b", r"\bset\b", r"\benable\b", r"\bdisable\b", r"\btoggle\b",
    r"\bturn (?:on|off)\b", r"\bterminate\b", r"\bkill\b", r"\bfail ?over\b", r"\bdelete\b", r"\badd (?:a )?(?:comment|note)\b",
    r"\bpage\b", r"\bflush\b", r"\bredeploy\b", r"\bmark\b", r"\bresolve\b", r"\bnotify\b", r"\bannounce\b", r"\btell\b",
    r"\bbump\b", r"\bincrease\b", r"\braise\b", r"\bsilence\b", r"\backnowledge\b", r"\bchange the\b", r"\bdrain\b",
]

ENVIRONMENTS = {"production": [r"\bprod(?:uction)?\b", r"\blive\b"], "staging": [r"\bstag(?:e|ing)\b"],
                "development": [r"\bdev(?:elopment)?\b"]}
SERVICE_RE = re.compile(r"\b([a-z]+(?:-[a-z]+)*-(?:api|gateway|service|worker))\b")


@dataclass(frozen=True)
class Route:
    domains: list[str]
    domain_scores: dict[str, float]
    operation: str  # read | write
    environment: str | None
    service: str | None
    matched: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"domains": self.domains, "domain_scores": self.domain_scores, "operation": self.operation,
                "environment": self.environment, "service": self.service, "matched": self.matched}


class IntentRouter:
    def __init__(self, lexicon: dict[str, list[str]] | None = None, max_domains: int = 3):
        self.lexicon = lexicon or DOMAIN_LEXICON
        self.max_domains = max_domains
        self._patterns = {d: [(t, re.compile(r"(?<![a-z0-9])" + re.escape(t) + (r"(?![a-z0-9])" if t[-1].isalnum() else ""))) for t in terms]
                          for d, terms in self.lexicon.items()}

    def route(self, request: str, default_environment: str | None = None) -> Route:
        text = request.lower()
        scores: dict[str, float] = {}
        matched: dict[str, list[str]] = {}
        for domain, patterns in self._patterns.items():
            hits = [term for term, pat in patterns if pat.search(text)]
            if hits:
                # multi-word phrases are stronger evidence than single words
                scores[domain] = round(sum(1.5 if " " in h else 1.0 for h in hits), 2)
                matched[domain] = hits
        domains = [d for d, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))][: self.max_domains]
        write_hits = [p for p in WRITE_PATTERNS if re.search(p, text)]
        if write_hits:
            matched["_write"] = write_hits
        environment = default_environment
        for env, pats in ENVIRONMENTS.items():
            if any(re.search(p, text) for p in pats):
                environment = env
                break
        m = SERVICE_RE.search(text)
        return Route(domains, scores, "write" if write_hits else "read", environment, m.group(1) if m else None, matched)
