"""The decision function every enforcement point calls. Pure: (desired state, request, usage) -> decision.

It holds no policy of its own. Every answer is read from the bundle the runtime received from the control plane, and
every decision names the rule that produced it, so the audit record can say which version decided what.

Order of evaluation (first match wins):
  1 registration and identity binding   5 tool registered, MCP server enabled
  2 lifecycle status                    6 the agent's grant for the tool (allow / approval_required / deny, with conditions)
  3 emergency controls                  7 budgets and quotas
  4 (model calls) model governance
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

ALLOW, APPROVAL, DENY = "allow", "approval_required", "deny"


@dataclass(frozen=True)
class Decision:
    effect: str
    reason: str
    rule: str

    def to(self) -> dict:
        return asdict(self)


def _agent(state: dict, agent: str) -> dict | None:
    return state.get("agents", {}).get(agent)


def check_agent(state: dict, agent: str, workload: str, mutation: bool) -> Decision | None:
    a = _agent(state, agent)
    if a is None:
        return Decision(DENY, "AGENT_NOT_REGISTERED", f"agents.{agent}")
    if a["workload"] != workload:
        return Decision(DENY, "IDENTITY_MISMATCH", f"agents.{agent}.workload")
    status = a["status"]
    if status in ("suspended", "disabled", "paused"):
        return Decision(DENY, f"AGENT_{status.upper()}", f"agents.{agent}.status")
    if status == "quarantined" and mutation:
        return Decision(DENY, "AGENT_QUARANTINED", f"agents.{agent}.status")
    if mutation and state.get("emergency", {}).get("deny_all_mutations"):
        return Decision(DENY, "EMERGENCY_MUTATION_FREEZE", "emergency.deny_all_mutations")
    return None


def matches(when: dict, args: dict) -> bool:
    for key, want in when.items():
        field, _, op = key.rpartition("_") if key.endswith(("_gt", "_lte", "_lt", "_gte")) else (key, "", "eq")
        have = args.get(field)
        if have is None:
            return False
        if op == "eq" and have != want:
            return False
        if op == "gt" and not have > want:
            return False
        if op == "gte" and not have >= want:
            return False
        if op == "lt" and not have < want:
            return False
        if op == "lte" and not have <= want:
            return False
    return True


def decide_start(state: dict, agent: str, workload: str, spent_today: float) -> Decision:
    d = check_agent(state, agent, workload, mutation=False)
    if d:
        return d
    budget = _agent(state, agent)["limits"]["daily_budget"]
    if spent_today >= budget:
        return Decision(DENY, "DAILY_BUDGET_EXHAUSTED", f"agents.{agent}.limits.daily_budget")
    return Decision(ALLOW, "AGENT_ACTIVE", f"agents.{agent}.status")


def decide_tool(state: dict, agent: str, workload: str, tool: str, args: dict, tool_calls_so_far: int) -> Decision:
    meta = state.get("tools", {}).get(tool)
    d = check_agent(state, agent, workload, mutation=bool(meta and meta["mutation"]))
    if d:
        return d
    if meta is None:
        return Decision(DENY, "TOOL_NOT_REGISTERED", f"tools.{tool}")
    server = state["mcp_servers"][meta["server"]]
    if server["status"] == "disabled":
        return Decision(DENY, "MCP_SERVER_DISABLED", f"mcp_servers.{meta['server']}.status")
    a = _agent(state, agent)
    grant = a["tools"].get(tool)
    if grant is None:
        return Decision(DENY, "TOOL_NOT_GRANTED", f"agents.{agent}.tools")
    if tool_calls_so_far >= a["limits"]["max_tool_calls"]:
        return Decision(DENY, "TOOL_CALL_BUDGET_EXCEEDED", f"agents.{agent}.limits.max_tool_calls")
    if isinstance(grant, str):
        return Decision(grant, f"POLICY_{grant.upper()}", f"agents.{agent}.tools.{tool}")
    for i, rule in enumerate(grant):
        if matches(rule["when"], args):
            return Decision(rule["effect"], f"POLICY_{rule['effect'].upper()}", f"agents.{agent}.tools.{tool}[{i}]")
    return Decision(DENY, "NO_MATCHING_RULE", f"agents.{agent}.tools.{tool}")


def decide_model(state: dict, agent: str, workload: str, data_class: str, est_cost_fn, run_cost: float) -> tuple[Decision, str | None]:
    """Resolve the model for a call from the agent's profile, the catalog and the data class. Agents never name a model."""
    d = check_agent(state, agent, workload, mutation=False)
    if d:
        return d, None
    a = _agent(state, agent)
    profile = state["models"]["profiles"][a["model_profile"]]
    catalog = state["models"]["catalog"]
    wanted = [profile["confidential"]] if data_class == "confidential" else [profile["default"], *profile.get("fallback", [])]
    for m in wanted:
        meta = catalog.get(m)
        if meta and meta["status"] == "active" and data_class in meta["data_classes"]:
            if run_cost + est_cost_fn(meta) > a["limits"]["max_cost_per_run"]:
                return Decision(DENY, "COST_BUDGET_EXCEEDED", f"agents.{agent}.limits.max_cost_per_run"), None
            rule = "models.profiles." + a["model_profile"] + (".confidential" if data_class == "confidential" else ".default")
            return Decision(ALLOW, "MODEL_RESOLVED", rule), m
    return Decision(DENY, "NO_ALLOWED_MODEL_FOR_DATA_CLASS", f"models.profiles.{a['model_profile']}"), None
