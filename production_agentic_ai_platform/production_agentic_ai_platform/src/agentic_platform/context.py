"""Context gateway: identity-aware, policy-aware retrieval and context assembly.

    identity -> tenant / environment / classification / ACL / expiry predicates -> retrieval -> ranking
             -> freshness and provenance -> context guard -> assembly (with a model-visible manifest)

The policy predicates are part of the retrieval query.  Content the requester may not see is never selected, so it cannot
be ranked, summarised, cached or leaked by the model; filtering after inference would already be too late.  For evidence,
the gateway also reads the metadata (never the text) of excluded items, to record which rule excluded them.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from agentic_platform.guardrails import ContextGuard
from agentic_platform.store import Store


def _ts(s: str | None) -> float | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp() if s else None


class ContextGateway:
    def __init__(self, store: Store, data_policy: dict[str, Any], guard: ContextGuard):
        self.s, self.order, self.guard = store, data_policy["classification_order"], guard

    def retrieve(self, *, tenant: str, environment: str, groups: list[str], clearance: str, query: str, now: float | None = None,
                 k: int = 4) -> dict[str, Any]:
        now = now or time.time()
        allowed = self.order[: self.order.index(clearance) + 1]
        marks = ",".join("?" * len(allowed))
        gmarks = ",".join("?" * len(groups))
        sql = (f"SELECT id, kind, source, updated_at, text FROM knowledge WHERE tenant=? AND environment=? AND classification IN ({marks}) "
               f"AND EXISTS (SELECT 1 FROM json_each(knowledge.acl_json) WHERE value IN ({gmarks})) "
               f"AND (expires_at IS NULL OR expires_at > ?)")
        rows = self.s.q(sql, tenant, environment, *allowed, *groups, datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        ranked = sorted(rows, key=lambda r: (-len(terms & set(re.findall(r"[a-z0-9]+", r[4].lower()))), r[0]))[:k]
        items = []
        for r in ranked:
            g = self.guard.scan(r[0], r[4])
            items.append({"id": r[0], "kind": r[1], "source": r[2], "updated_at": r[3], "age_days": round((now - _ts(r[3])) / 86400, 1),
                          "text": g["text"], "guard": g["action"]})
        # Evidence only: metadata of everything that was NOT eligible, with the reason.  The text column is not read.
        excluded = []
        for (iid, ten, env, cls, acl, exp) in self.s.q("SELECT id, tenant, environment, classification, acl_json, expires_at FROM knowledge"):
            why = []
            if ten != tenant:
                why.append("tenant")
            if env != environment:
                why.append("environment")
            if cls not in allowed:
                why.append("classification")
            if not set(json.loads(acl)) & set(groups):
                why.append("acl")
            if exp and _ts(exp) <= now:
                why.append("expired")
            if why:
                excluded.append({"id": iid, "reasons": why})
        return {"query": query, "predicates": {"tenant": tenant, "environment": environment, "classifications": allowed, "groups": groups},
                "selected": items, "excluded": excluded, "eligible": len(rows)}

    def admit_observation(self, capability: str, result: Any) -> dict[str, Any]:
        """Tool results are data too.  Log lines are scanned one by one before they can reach the model."""
        guard_events = []
        if isinstance(result, dict) and isinstance(result.get("lines"), list):
            lines = []
            for ln in result["lines"]:
                g = self.guard.scan(ln["id"], ln["text"])
                if g["action"] != "passed":
                    guard_events.append({k: g[k] for k in ("id", "action", "patterns")})
                lines.append({"id": ln["id"], "text": g["text"]})
            result = {**result, "lines": lines}
        return {"capability": capability, "result": result, "guard": guard_events}
