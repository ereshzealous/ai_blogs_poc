"""Runtime budgets: counters the runtime enforces before each model call, tool call and workflow step.

The envelope comes from the control plane (budgets/<agent>.yaml).  Usage is persisted per workflow in platform.db, so a
restart does not reset it.  Exceeding a limit raises BUDGET_EXCEEDED before the resource is consumed.  No prompt is
involved.
"""

from __future__ import annotations

from typing import Any

from agentic_platform.store import Store

KINDS = {"model_call": "max_model_calls", "tool_call": "max_tool_calls", "workflow_step": "max_workflow_steps", "cost_units": "max_cost_units"}


class BudgetExceeded(Exception):
    code = "BUDGET_EXCEEDED"

    def __init__(self, limit: str, used: float, cap: float, attempted: str):
        super().__init__(f"BUDGET_EXCEEDED: {limit} ({used:g} used of {cap:g}) on {attempted}")
        self.limit, self.used, self.cap, self.attempted = limit, used, cap, attempted


class Budget:
    def __init__(self, store: Store, workflow_id: str, limits: dict[str, Any]):
        self.s, self.wf, self.limits = store, workflow_id, limits

    def usage(self) -> dict[str, float]:
        u = self.s.usage(self.wf)
        return {k: u.get(k, 0) for k in KINDS}

    def state(self) -> dict[str, Any]:
        u = self.usage()
        hit = [KINDS[k] for k in KINDS if u[k] >= self.limits[KINDS[k]]]
        return {"usage": u, "limits": self.limits, "exhausted": bool(hit), "limit_hit": ",".join(hit) or None}

    def charge(self, kind: str, units: float = 1, detail: str = "", cost_units: float = 0) -> None:
        """Check first, then record.  A charge that would cross a limit is refused and nothing is consumed."""
        u = self.usage()
        if u[kind] + units > self.limits[KINDS[kind]]:
            raise BudgetExceeded(KINDS[kind], u[kind], self.limits[KINDS[kind]], detail or kind)
        if cost_units and u["cost_units"] + cost_units > self.limits["max_cost_units"]:
            raise BudgetExceeded("max_cost_units", u["cost_units"], self.limits["max_cost_units"], detail or kind)
        self.s.charge(self.wf, kind, units, detail)
        if cost_units:
            self.s.charge(self.wf, "cost_units", cost_units, detail)
