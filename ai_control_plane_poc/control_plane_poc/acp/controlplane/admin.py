"""Governing the control plane itself: who may publish which change, and when a second person is required.

A change is classified by comparing the old and new desired state at every path it sets:

  restricting   only makes behaviour stricter (suspend an agent, disable a tool, server or model, lower a limit,
                move a tool effect towards deny). Speed matters here: an in-scope admin may publish it alone.
  widening      loosens or rewrites behaviour (restore an agent, raise a limit, switch the default model, allow more).
                It needs a second, different approver whose scope also covers the change.

An emergency (break-glass) change must be restricting and published by a principal with break_glass.
"""

from __future__ import annotations

from dataclasses import dataclass

from acp.common import get_path

AGENT_STATUS = {"active": 0, "paused": 1, "quarantined": 1, "suspended": 2, "disabled": 3}
RESOURCE_STATUS = {"enabled": 0, "active": 0, "deprecated": 1, "disabled": 2}
EFFECT = {"allow": 0, "approval_required": 1, "deny": 2}


@dataclass(frozen=True)
class AdminDecision:
    allowed: bool
    reason: str
    kind: str  # restricting | widening
    scopes: tuple[str, ...]


def scope_of(path: str) -> str:
    parts = path.split(".")
    if parts[0] == "agents":
        return parts[1]
    if parts[0] == "models":
        return "models"
    return "*"


def _grant_rules(v) -> dict[str, int]:
    if isinstance(v, str):
        return {"*": EFFECT[v]}
    return {repr(sorted(r["when"].items())): EFFECT[r["effect"]] for r in v or []}


def is_restricting(path: str, old, new) -> bool:
    leaf = path.split(".")[-1]
    if leaf == "status":
        table = AGENT_STATUS if path.startswith("agents.") else RESOURCE_STATUS
        return table.get(new, 99) >= table.get(old, 0)
    if path.startswith("agents.") and ".limits." in path:
        return old is not None and new <= old
    if path.startswith("agents.") and ".tools." in path:
        if old is None:
            return False
        o, n = _grant_rules(old), _grant_rules(new)
        return set(n) == set(o) and all(n[k] >= o[k] for k in o)
    if path == "emergency.deny_all_mutations":
        return bool(new)
    return False


def covers(scopes: list[str], scope: str) -> bool:
    return "*" in scopes or scope in scopes


def authorize_change(admins: dict, state: dict, sets: dict, author: str, second_approver: str | None, emergency: bool) -> AdminDecision:
    scopes = tuple(sorted({scope_of(p) for p in sets}))
    restricting = all(is_restricting(p, get_path(state, p), v) for p, v in sets.items())
    kind = "restricting" if restricting else "widening"
    who = admins.get("admins", {}).get(author)
    if who is None:
        return AdminDecision(False, f"{author} is not a control-plane administrator", kind, scopes)
    for s in scopes:
        if not covers(who["scope"], s):
            return AdminDecision(False, f"{author} has no scope over {s}", kind, scopes)
    if emergency:
        if not who.get("break_glass"):
            return AdminDecision(False, f"{author} may not publish break-glass changes", kind, scopes)
        if not restricting:
            return AdminDecision(False, "a break-glass change may only restrict behaviour", kind, scopes)
        return AdminDecision(True, "break-glass restriction by an in-scope administrator", kind, scopes)
    if restricting:
        return AdminDecision(True, "restricting change by an in-scope administrator", kind, scopes)
    if not second_approver:
        return AdminDecision(False, "a widening change needs a second approver", kind, scopes)
    if second_approver == author:
        return AdminDecision(False, "the second approver must be a different person", kind, scopes)
    sec = admins.get("admins", {}).get(second_approver)
    if sec is None or not sec.get("can_approve"):
        return AdminDecision(False, f"{second_approver} may not approve control-plane changes", kind, scopes)
    for s in scopes:
        if not covers(sec["scope"], s):
            return AdminDecision(False, f"second approver {second_approver} has no scope over {s}", kind, scopes)
    return AdminDecision(True, "widening change with an in-scope second approver", kind, scopes)
