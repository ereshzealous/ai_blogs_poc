"""Validate a desired state before it becomes a version: policy-as-code is only useful if a bad change cannot ship.

Returns a list of problems (empty = valid). The checks are structural, the kind a CI gate would run on every change.
"""

from __future__ import annotations

EFFECTS = {"allow", "approval_required", "deny"}
AGENT_STATUSES = {"active", "paused", "quarantined", "suspended", "disabled"}
RESOURCE_STATUSES = {"enabled", "active", "deprecated", "disabled"}
REQUIRED_AGENT_FIELDS = ("owner", "team", "purpose", "environment", "risk_level", "identity", "workload", "status", "model_profile", "tools", "limits")


def validate(s: dict) -> list[str]:
    p: list[str] = []
    tools, servers, models = s.get("tools", {}), s.get("mcp_servers", {}), s.get("models", {})
    for name, a in s.get("agents", {}).items():
        for f in REQUIRED_AGENT_FIELDS:
            if f not in a:
                p.append(f"agent {name}: missing {f} (every agent must be registered with an owner, identity and limits)")
        if a.get("status") not in AGENT_STATUSES:
            p.append(f"agent {name}: unknown status {a.get('status')!r}")
        if a.get("model_profile") not in models.get("profiles", {}):
            p.append(f"agent {name}: unknown model profile {a.get('model_profile')!r}")
        for tool, grant in (a.get("tools") or {}).items():
            if tool not in tools:
                p.append(f"agent {name}: grant for unregistered tool {tool!r}")
            rules = [{"effect": grant}] if isinstance(grant, str) else grant
            for r in rules:
                if r.get("effect") not in EFFECTS:
                    p.append(f"agent {name}: tool {tool}: unknown effect {r.get('effect')!r}")
    for tool, t in tools.items():
        if t.get("server") not in servers:
            p.append(f"tool {tool}: unknown MCP server {t.get('server')!r}")
        if not str(t.get("credential", "")).startswith("secret://"):
            p.append(f"tool {tool}: credential must be a secret:// reference, never a value")
    for name, srv in servers.items():
        if srv.get("status") not in RESOURCE_STATUSES:
            p.append(f"server {name}: unknown status {srv.get('status')!r}")
    for name, m in models.get("catalog", {}).items():
        if m.get("status") not in RESOURCE_STATUSES:
            p.append(f"model {name}: unknown status {m.get('status')!r}")
    for prof, pr in models.get("profiles", {}).items():
        for ref in [pr.get("default"), pr.get("confidential"), *pr.get("fallback", [])]:
            if ref and ref not in models.get("catalog", {}):
                p.append(f"profile {prof}: unknown model {ref!r}")
    return p
