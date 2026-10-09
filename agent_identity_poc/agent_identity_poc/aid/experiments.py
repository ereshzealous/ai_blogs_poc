"""The seven T1 experiments.  Deterministic: simulated clock, directory, workloads and tools; real exchange, delegation,
attestation checks, broker, gateway, approvals, audit chain and revocation.

    uv run aid experiments --run-id 2026-09-29-recorded      -> runs/<run-id>/{I1..I7.json, facts.json, summary.md, ...}

Every experiment builds fresh platforms and counts outcomes from the tools' own logs and effects, and from the platform
audit chain, never from what a component says it did.
"""

from __future__ import annotations

import copy
import hashlib
import json
import platform as pyplatform
import shutil
from pathlib import Path
from typing import Any

from aid.agents import IncidentIntel, ReleaseGuard, Remediation
from aid.baselines import user_credentials
from aid.config import CONFIG, MIN, load
from aid.contracts import CapabilityCall, EventProvenance
from aid.directory import AuthError
from aid.platform import Execution, Platform
from aid.trust import TrustError, TrustLayer

ROOT = Path(__file__).resolve().parents[1]
MODES = ("shared_sa", "impersonation", "chain")
QUESTIONS = ["who_is_the_agent", "who_invoked", "on_whose_behalf", "what_authority", "which_runtime", "which_credential",
             "what_action", "who_approved", "can_it_be_revoked"]
PROV = EventProvenance(source="datadog/monitors", event_id="dd-evt-771204", rule="monitor/payment-service-error-rate")
RUNTIME = "spiffe://prod.company.internal/agent-runtime"


# ---- the record of every scenario (runs/<id>/scenarios/, read by the Lab Console) ---------------------------------------
# Each experiment builds fresh platforms; after a scenario finishes, its platform audit chain, every tool's own log and
# what the scenario was for are kept here.  Recording reads state the platform already holds: it changes no outcome.
SCENARIOS: list[dict[str, Any]] = []
VARIANT = {"shared_sa": "A", "impersonation": "B", "chain": "C"}


def scenario(sid: str, exp: str, mode: str, use_case: str, inp: dict[str, Any], expected: str, observed: str, outcome: str,
             where: str | None, checks: list[str], measures: list[list[Any]], platforms: dict[str, Platform]) -> None:
    """outcome: 'held' (the identity property held), 'qualified' (held within a stated bound) or 'broken'."""
    SCENARIOS.append({
        "id": sid, "experiment": exp, "mode": mode, "variant": VARIANT[mode], "use_case": use_case, "input": inp,
        "expected": expected, "observed": observed, "outcome": outcome, "where": where, "checks": checks,
        "measures": [[k, v] for k, v in measures],
        "audit": {label: [json.loads(json.dumps(r, default=str)) for r in p.audit.rows] for label, p in platforms.items()},
        "tool_logs": {label: {s: list(t.log) for s, t in p.tools.items()} for label, p in platforms.items()},
        "effects": {label: {s: list(t.effects) for s, t in p.tools.items() if t.effects} for label, p in platforms.items()},
    })


def k8s_patches(p: Platform) -> int:
    return sum(e["verb"] == "deployments:patch" for e in p.tools["kubernetes"].effects)


def rollback_with_approval(p: Platform, ex: Execution, agent_call: CapabilityCall) -> tuple[Any, Any]:
    first = p.call(ex, agent_call)
    if first.effect != "REQUIRE_APPROVAL":
        return first, first
    p.approve(first.approval_id, "ic.dev")
    return first, p.call(ex, agent_call, approval_id=first.approval_id)


def maya_rollback(p: Platform) -> tuple[Execution, Any]:
    """Maya, on call, asks the incident agent through the web console; the IC approves the rollback it proposes."""
    ex = p.start("web", "cred-web", "agent.incident-intel", sso="sso-maya")
    agent = IncidentIntel()
    for c in agent.investigate():
        p.call(ex, c)
    p.clock.advance(3 * MIN)
    _, d = rollback_with_approval(p, ex, agent.remediate())
    return ex, d


# ---- the nine questions ----------------------------------------------------------------------------------------------
def platform_answers(rec: dict[str, Any], truth: dict[str, Any]) -> dict[str, bool]:
    return {
        "who_is_the_agent": rec.get("agent") == truth["agent"],
        "who_invoked": rec.get("invoker") == truth["invoker"],
        "on_whose_behalf": "on_behalf_of" in rec and rec["on_behalf_of"] == truth["on_behalf_of"],
        "what_authority": "scopes" in rec and sorted(rec["scopes"]) == truth["authority"],
        "which_runtime": rec.get("workload") == truth["runtime"],
        "which_credential": rec.get("tool_principal") == truth["principal"] and rec.get("credential_id") == truth["credential_id"],
        "what_action": rec.get("capability") == truth["capability"] and rec.get("arguments") == truth["arguments"],
        "who_approved": rec.get("authorized_by") == truth["approver"],
        "can_it_be_revoked": rec.get("revocation") == truth["revocation"] and truth["revocation"] is not None,
    }


def tool_answers(entry: dict[str, Any], truth: dict[str, Any], oidc: dict[str, str]) -> dict[str, bool]:
    user, imp = entry.get("user.username"), entry.get("impersonatedUser")
    human = oidc.get(truth["on_behalf_of"] or "", "\0")
    return {
        "who_is_the_agent": truth["agent"] in (user, imp),
        "who_invoked": truth["invoker"] in (user, imp),
        "on_whose_behalf": human in (user, imp),
        "what_authority": "scopes" in entry or "permissions" in entry,
        "which_runtime": truth["runtime"] in json.dumps(entry),
        "which_credential": user == truth["principal"],
        "what_action": entry.get("verb") == "patch" and entry.get("objectRef") == "deployments/payment-service",
        "who_approved": truth["approver"] in json.dumps(entry),
        "can_it_be_revoked": False,   # a tool's access log carries no revocation handles for the chain that reached it
    }


# ---- I1 · attribution ------------------------------------------------------------------------------------------------
def i1() -> dict[str, Any]:
    out: dict[str, Any] = {"questions": QUESTIONS, "modes": {}}
    oidc = {h: v["oidc"] for h, v in load("principals.yaml")["humans"].items()}
    ti = load("tool_identities.yaml")
    for mode in MODES:
        p = Platform(mode)
        ex, d = maya_rollback(p)
        rec = p.audit.calls("rollbackDeployment")[-1]
        entry = [e for e in p.tools["kubernetes"].log if e["verb"] == "patch"][-1]
        if mode == "chain":
            authority = sorted(ex.token.scopes)
            revocation = {"delegation": TrustLayer.grant_id("sre.maya"), "invoker_credential": "cred-web", "agent": "agent.incident-intel@1.3.0",
                          "workload": RUNTIME, "tool_identity": "incident-remediator@production"}
        else:
            k8s = p.tools["kubernetes"].grants[d.output["tool_principal"]]
            authority, revocation = sorted(k8s), None
        truth = {"agent": "agent.incident-intel@1.3.0", "invoker": "svc.web-portal", "on_behalf_of": "sre.maya", "authority": authority,
                 "runtime": RUNTIME, "principal": d.output["tool_principal"], "credential_id": d.output["credential_id"],
                 "capability": "rollbackDeployment", "arguments": IncidentIntel().remediate().arguments, "approver": "ic.dev",
                 "revocation": revocation}
        pa, ta = platform_answers(rec, truth), tool_answers(entry, truth, oidc)
        out["modes"][mode] = {"executed": d.effect, "tool_principal": d.output["tool_principal"], "kubernetes_entry": entry,
                              "platform_record": rec, "platform_answers": pa, "tool_answers": ta,
                              "platform_answered": sum(pa.values()), "tool_answered": sum(ta.values()),
                              "tool_authorized_permissions": len(p.tools["kubernetes"].grants[d.output["tool_principal"]])}

        # several agents touching Kubernetes: can anyone tell them apart afterwards?
        q = Platform(mode)
        e1 = q.start("event", "cred-monitoring", "agent.incident-intel", provenance=PROV)
        q.call(e1, IncidentIntel().investigate()[1])
        rollback_with_approval(q, e1, IncidentIntel().remediate())
        e3 = q.start("cicd", "cred-ci", "agent.release-guard")
        q.call(e3, ReleaseGuard().check()[0])
        e2 = q.start("web", "cred-web", "agent.incident-intel", sso="sso-maya")
        q.call(e2, IncidentIntel().investigate()[1])
        e5 = q.delegate(e2, "agent.remediation")
        q.call(e5, Remediation().plan()[0])
        k8s_ok = [e for e in q.tools["kubernetes"].log if (e.get("responseStatus") == 200)]
        k8s_caps = {c for c, v in q.caps.items() if v["system"] == "kubernetes"}
        recs = [r for r in q.audit.calls() if r["capability"] in k8s_caps and r["status"] == "ok"]
        scenario(f"I1-{mode}-rollback", "I1", mode, "Attribution: one rollback, nine questions",
                 {"invoker": "svc.web-portal (web console)", "on_behalf_of": "sre.maya", "agent": "agent.incident-intel@1.3.0",
                  "request": "roll back payment-service to v4.17.2 in production", "approver": "ic.dev", "identity_model": mode},
                 "the platform record answers all nine questions" if mode == "chain" else "the platform record cannot answer the identity questions",
                 f"platform record {sum(pa.values())}/9 · tool log {sum(ta.values())}/9 · Kubernetes saw {d.output['tool_principal']}",
                 "held" if sum(pa.values()) == 9 else "broken",
                 None if sum(pa.values()) == 9 else "capability.call rollbackDeployment: the record cannot answer "
                 + ", ".join(k.replace("_", " ") for k, v in pa.items() if not v),
                 ["the rollback executed once in every mode", "every mode: the tool log answers at most three"]
                 + (["chain: the platform record answers all nine questions", "audit chain intact; an edited approver breaks it at that row"] if mode == "chain" else []),
                 [["Platform record answers", f"{sum(pa.values())}/9"], ["Tool log answers", f"{sum(ta.values())}/9"],
                  ["Kubernetes saw", d.output["tool_principal"]], ["Tool permissions behind the call", len(p.tools["kubernetes"].grants[d.output["tool_principal"]])]],
                 {"platform": p})
        out["modes"][mode]["multi_agent"] = {
            "agents_acting": 3, "kubernetes_actions": len(k8s_ok),
            "distinct_kubernetes_principals": len({e["user.username"] for e in k8s_ok}),
            "kubernetes_principals": sorted({e["user.username"] for e in k8s_ok}),
            "agents_attributable_from_platform_audit": len({r["agent"] for r in recs if r.get("agent")}),
            "impersonation_fallbacks": sum(1 for r in recs if r.get("fallback")),
        }
        ma = out["modes"][mode]["multi_agent"]
        scenario(f"I1-{mode}-three-agents", "I1", mode, "Attribution: three agents touch Kubernetes",
                 {"executions": "event -> incident-intel (rollback) · ci -> release-guard (read) · maya -> incident-intel -> remediation (restart plan)",
                  "identity_model": mode},
                 "every agent attributable from the platform record" if mode == "chain" else "the agents cannot be told apart afterwards",
                 f"{ma['agents_attributable_from_platform_audit']} of 3 agents attributable · Kubernetes saw {ma['distinct_kubernetes_principals']} principal(s)",
                 "held" if ma["agents_attributable_from_platform_audit"] == 3 else "broken",
                 None if ma["agents_attributable_from_platform_audit"] == 3 else "capability.call: the records name no agent",
                 ["shared account: Kubernetes sees one principal for three agents", "shared account: no agent attributable from the platform record"]
                 if mode == "shared_sa" else (["chain: all three agents attributable from the platform record"] if mode == "chain" else []),
                 [["Agents acting", 3], ["Attributable from the platform record", ma["agents_attributable_from_platform_audit"]],
                  ["Kubernetes actions", ma["kubernetes_actions"]], ["Distinct Kubernetes principals", ma["distinct_kubernetes_principals"]]],
                 {"platform": q})
        if mode == "chain":   # tamper evidence on the chain run
            rows = copy.deepcopy(p.audit.rows)
            target = next(r for r in rows if r["kind"] == "capability.call" and r["record"]["capability"] == "rollbackDeployment")
            target["record"]["authorized_by"] = "sre.maya"
            out["tamper"] = {"intact_before": p.audit.verify()[0], "intact_after": p.audit.verify(rows)[0],
                             "broken_at": p.audit.verify(rows)[1], "edited_row": target["n"], "rows": len(rows)}
            out["chain_audit_jsonl"] = p.audit.jsonl()
            out["chain_tool_logs"] = {s: t.log for s, t in p.tools.items()}
    out["tool_identities"] = len(ti["tool_identities"])
    return out


# ---- I2 · confused deputy ---------------------------------------------------------------------------------------------
def i2() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mode in MODES:
        p = Platform(mode)
        rg = p.start("cicd", "cred-ci", "agent.release-guard")
        callee = p.delegate(rg, "agent.incident-intel")
        first, final = rollback_with_approval(p, callee, ReleaseGuard().ask_incident_intel_to_roll_back())
        recs = [r for r in p.audit.rows if r["kind"] in ("capability.call", "capability.denied", "approval.requested")]
        row = {"first_decision": first.effect, "rule": first.rule, "final": final.effect, "rollbacks": k8s_patches(p),
               "originator_visible_in_audit": any("agent.release-guard" in json.dumps(r["record"]) for r in recs),
               "approver_saw_requester": p.approvals.items[first.approval_id]["requested_by"] if first.approval_id else None}
        if mode == "chain":
            row["caller_scopes"], row["callee_scopes"] = list(rg.token.scopes), list(callee.token.scopes)
            row["narrowed"] = set(callee.token.scopes) <= set(rg.token.scopes)
            row["act_chain"] = callee.token.act.chain()
            row["subject"] = callee.token.sub
            try:
                p.delegate(p.start("web", "cred-web", "agent.incident-intel", sso="sso-maya"), "agent.release-guard")
                row["undeclared_edge_refused"] = False
            except TrustError:
                row["undeclared_edge_refused"] = True
            # narrowing on every hop of the one chain in the scenario that goes two deep
            e2 = p.start("web", "cred-web", "agent.incident-intel", sso="sso-maya")
            e5 = p.delegate(e2, "agent.remediation")
            row["maya_hop_scopes"] = {"incident-intel": list(e2.token.scopes), "remediation": list(e5.token.scopes)}
            row["maya_hop_narrowed"] = set(e5.token.scopes) <= set(e2.token.scopes)
        scenario(f"I2-{mode}-deputy", "I2", mode, "Confused deputy: a read-only agent asks for a rollback",
                 {"invoker": "svc.ci-pipeline (CI)", "caller": "agent.release-guard (read only)", "callee": "agent.incident-intel",
                  "request": "roll back payment-service in production", "approver": "ic.dev", "identity_model": mode},
                 "denied before any approval; no rollback" if mode == "chain" else "the rollback runs and the originator disappears",
                 f"first decision {first.effect} ({first.rule}) · final {final.effect} · rollbacks {k8s_patches(p)}"
                 + ("" if row["originator_visible_in_audit"] else " · originator not in the record"),
                 "held" if k8s_patches(p) == 0 else "broken",
                 None if k8s_patches(p) == 0 else f"approval.requested: the approver saw {row['approver_saw_requester']}, not release-guard",
                 ["chain: the deputy request is denied before any approval", "chain: the callee's scopes narrowed", "chain: an undeclared agent -> agent edge is refused"]
                 if mode == "chain" else (["shared account: the deputy rollback executes and hides its originator"] if mode == "shared_sa" else []),
                 [["First decision", first.effect], ["Rule", first.rule], ["Final", final.effect], ["Rollbacks", k8s_patches(p)],
                  ["Originator visible", "yes" if row["originator_visible_in_audit"] else "no"]],
                 {"platform": p})
        out[mode] = row
    return out


# ---- I3 · revocation drill ---------------------------------------------------------------------------------------------
HEARTBEAT = {
    "E1": [CapabilityCall(capability="getErrorRate", arguments={"service": "payment-service"}),
           CapabilityCall(capability="postMessage", arguments={"channel": "#inc-payments", "text": "status"})],
    "E2": [CapabilityCall(capability="getErrorRate", arguments={"service": "payment-service"}),
           CapabilityCall(capability="updateIncident", arguments={"incident": "INC-4102", "note": "status"})],
    "E3": [CapabilityCall(capability="getDeployments", arguments={"service": "payment-service"}),
           CapabilityCall(capability="getErrorRate", arguments={"service": "payment-service"})],
    "E4": [CapabilityCall(capability="getErrorRate", arguments={"service": "payment-service"}),
           CapabilityCall(capability="postMessage", arguments={"channel": "#inc-payments", "text": "workflow status"})],
    "E5": [CapabilityCall(capability="getErrorRate", arguments={"service": "payment-service"}),
           CapabilityCall(capability="restartPods", arguments={"service": "payment-service", "environment": "production"})],
}
LABEL = {"E1": "event -> incident-intel", "E2": "maya (web) -> incident-intel", "E3": "ci -> release-guard (release-runtime)",
         "E4": "workflow -> incident-intel", "E5": "maya (web) -> incident-intel -> remediation"}
REVOKE_AT, MINUTES = 5, 30


def fleet(p: Platform) -> dict[str, Execution]:
    e = {"E1": p.start("event", "cred-monitoring", "agent.incident-intel", provenance=PROV),
         "E2": p.start("web", "cred-web", "agent.incident-intel", sso="sso-maya"),
         "E3": p.start("cicd", "cred-ci", "agent.release-guard"),
         "E4": p.start("workflow", "cred-workflow", "agent.incident-intel")}
    e["E5"] = p.delegate(e["E2"], "agent.remediation")
    return e


def drill(mode: str, layer: str | None, lever) -> dict[str, Any]:
    p = Platform(mode)
    ex = fleet(p)
    t0 = p.clock.now()
    first: dict[str, dict[str, Any]] = {}
    refused_calls: dict[str, set[str]] = {k: set() for k in ex}
    new_start = None
    for minute in range(1, MINUTES + 1):
        p.clock.advance(MIN)
        if minute == REVOKE_AT and lever:
            lever(p)
            try:
                p.start("event", "cred-monitoring", "agent.incident-intel", provenance=PROV)
                new_start = "accepted"
            except (AuthError, TrustError) as err:
                new_start = f"refused: {err}"
        for k, e in ex.items():
            for c in HEARTBEAT[k]:
                d = p.call(e, c)
                if d.effect != "EXECUTED":
                    refused_calls[k].add(c.capability)
                    first.setdefault(k, {"minute": minute, "reason": d.reason})
    affected = sorted(first)
    return {"layer": layer, "affected": affected, "affected_labels": [LABEL[k] for k in affected], "unaffected": sorted(set(ex) - set(first)),
            "minutes_to_effect": {k: v["minute"] - REVOKE_AT for k, v in first.items()}, "reasons": {k: v["reason"] for k, v in first.items()},
            "refused_capabilities": {k: sorted(v) for k, v in refused_calls.items() if v},
            "partially_working": sorted(k for k in affected if len(refused_calls[k]) < len(HEARTBEAT[k])),
            "new_event_execution_after_revocation": new_start, "t0": t0, "_platform": p}


def i3() -> dict[str, Any]:
    levers = {
        "delegation": lambda p: p.revoke_delegation("sre.maya"),
        "invoker_credential": lambda p: p.revoke_invoker_credential("cred-monitoring"),
        "agent": lambda p: p.disable_agent("agent.incident-intel"),
        "workload": lambda p: p.quarantine_runtime("svc.hai-runtime"),
        "tool_identity": lambda p: p.disable_tool_identity("incident-remediator@production"),
    }
    out = {"executions": LABEL, "revoke_at_minute": REVOKE_AT, "minutes": MINUTES, "token_ttl_min": Platform().d.ttl / MIN,
           "control": drill("chain", None, None), "chain": {k: drill("chain", k, f) for k, f in levers.items()},
           "shared_sa": {"rotate_shared_account": drill("shared_sa", "shared_account", lambda p: p.rotate_shared_account())}}
    ttl = out["token_ttl_min"]
    for name, mode, r in ([("control", "chain", out["control"])] + [(k, "chain", v) for k, v in out["chain"].items()]
                          + [("rotate_shared_account", "shared_sa", out["shared_sa"]["rotate_shared_account"])]):
        worst = max(r["minutes_to_effect"].values()) if r["minutes_to_effect"] else 0
        outcome = "broken" if len(r["affected"]) == len(LABEL) else ("qualified" if worst > 0 else "held")
        check = {"control": "control: nothing stops without a revocation", "delegation": "delegation: only Maya's executions stop, within one token lifetime",
                 "invoker_credential": "invoker credential: new executions from that head refused",
                 "agent": "agent: every execution running that agent stops at its next call", "workload": "workload: executions on the other runtime keep running",
                 "tool_identity": "tool identity: one capability of one execution stops", "rotate_shared_account": "shared account rotation stops all five executions"}[name]
        scenario(f"I3-{mode}-{name.replace('_', '-')}", "I3", mode, "Revocation: " + ("no lever pulled (control)" if name == "control" else f"pull the {name.replace('_', ' ')} lever"),
                 {"executions": " · ".join(f"{k} {v}" for k, v in LABEL.items()), "lever": name.replace("_", " "), "pulled_at_minute": REVOKE_AT,
                  "window_minutes": MINUTES, "identity_model": mode},
                 "nothing stops" if name == "control" else ("everything stops" if mode == "shared_sa" else "only the executions that depend on the lever stop"),
                 f"stopped {', '.join(r['affected']) or 'none'} · kept running {', '.join(r['unaffected']) or 'none'} · slowest effect {worst} min",
                 outcome,
                 None if outcome == "held" else ("revoked: one lever stops every execution" if outcome == "broken"
                                                 else f"token.refreshed: effect waits for the next re-exchange, up to {worst} of {ttl:g} min"),
                 [check], [["Stopped", len(r["affected"])], ["Kept running", len(r["unaffected"])], ["Slowest effect (min)", worst],
                           ["New start afterwards", r["new_event_execution_after_revocation"] or "-"]],
                 {"platform": r.pop("_platform")})
    return out


# ---- I4 · replay ------------------------------------------------------------------------------------------------------
def i4() -> dict[str, Any]:
    p = Platform("chain")
    e1 = p.start("event", "cred-monitoring", "agent.incident-intel", provenance=PROV)
    read = IncidentIntel().investigate()[1]
    legit = p.call(e1, read)
    batch = p.att.current("spiffe://prod.company.internal/batch-runner")
    replay = p.call(e1, read, presenter_svid=batch)
    e5 = p.delegate(p.start("web", "cred-web", "agent.incident-intel", sso="sso-maya"), "agent.remediation")
    p.call(e5, Remediation().plan()[0])
    stolen = next(c for c in reversed(p.broker.minted) if c.tool_identity == "incident-remediator@production")
    at_jira = p.tools["jira"].call(stolen, "issue:comment", {"incident": "INC-4102"})
    at_k8s_within = p.tools["kubernetes"].call(stolen, "deployments:get", {"service": "payment-service"})
    p.clock.advance(16 * MIN)
    expired = p.call(e1, read, presenter_svid=p.svid(e1))
    at_k8s_after = p.tools["kubernetes"].call(stolen, "deployments:get", {"service": "payment-service"})
    # the privileged variant: Maya's approved rollback, its execution token copied to another workload
    pw = Platform("chain")
    ew = pw.start("web", "cred-web", "agent.incident-intel", sso="sso-maya")
    rb = IncidentIntel().remediate()
    first = pw.call(ew, rb)
    pw.approve(first.approval_id, "ic.dev")
    wreplay = pw.call(ew, rb, approval_id=first.approval_id, presenter_svid=pw.att.current("spiffe://prod.company.internal/batch-runner"))
    replay_patches = k8s_patches(pw)
    wlegit = pw.call(ew, rb, approval_id=first.approval_id)
    s = Platform("shared_sa")
    s.clock.advance(24 * 60 * MIN)
    sa_replay = s.tools["kubernetes"].call(s.shared["kubernetes"], "deployments:patch", {"service": "payment-service"})
    base = {"invoker": "svc.monitoring-webhook (Datadog event)", "agent": "agent.incident-intel", "identity_model": "chain"}
    for sid, mode, case, attack, exp_, obs, outcome, where, check in (
        ("legitimate-call", "chain", "Replay: the legitimate call", "none: the call from its own workload", "executed", legit.effect, "held", None, None),
        ("other-workload-write", "chain", "Replay: an approved rollback's execution token from another workload",
         "Maya's approved rollback, token and approval id copied to spiffe://…/batch-runner", "rejected, no rollback",
         f"{wreplay.effect}: {wreplay.reason} · rollbacks {replay_patches} · then the real workload: {wlegit.effect}",
         "held" if wreplay.effect == "REJECTED" and replay_patches == 0 else "broken", None,
         "privileged write replayed from another workload is rejected with no side effect"),
        ("other-workload", "chain", "Replay: execution token from another workload", "token copied to spiffe://…/batch-runner", "rejected",
         f"{replay.effect}: {replay.reason}", "held" if replay.effect == "REJECTED" else "broken", None, "execution token replayed from another workload is rejected"),
        ("expired-token", "chain", "Replay: expired execution token", "token presented after 16 minutes", "rejected", f"{expired.effect}: {expired.reason}",
         "held" if expired.effect == "REJECTED" else "broken", None, "expired execution token is rejected"),
        ("wrong-audience", "chain", "Theft: tool credential at the wrong system", "incident-remediator credential presented to Jira", "rejected",
         f"HTTP {at_jira[0]}: {at_jira[1]}", "held" if at_jira[0] == 401 else "broken", None, "tool credential rejected by a system it was not minted for"),
        ("stolen-within-ttl", "chain", "Theft: stolen tool credential inside its lifetime", "incident-remediator credential used at Kubernetes within its minutes",
         "works until it expires, at its one audience", f"HTTP {at_k8s_within[0]}: {at_k8s_within[1]}", "qualified",
         f"tool call: a bearer credential works for its remaining {p.broker.ttl / MIN:g} minutes", None),
        ("stolen-after-ttl", "chain", "Theft: stolen tool credential after expiry", "the same credential after 16 minutes", "rejected",
         f"HTTP {at_k8s_after[0]}: {at_k8s_after[1]}", "held" if at_k8s_after[0] == 401 else "broken", None, "stolen tool credential dies with its ten minutes"),
        ("shared-secret", "shared_sa", "Theft: the shared account's secret a day later", "ai-automation secret used from anywhere after 24 hours", "still works",
         f"HTTP {sa_replay[0]}: {sa_replay[1]}", "broken", "tool call: a long-lived shared secret works from anywhere", "shared secret still works from anywhere a day later")):
        scenario(f"I4-{mode}-{sid}", "I4", mode, case, {**base, "identity_model": mode, "attack": attack}, exp_, obs, outcome, where,
                 [check] if check else [], [["Outcome", obs.split(":")[0]]],
                 {"platform": s} if mode == "shared_sa" else ({"platform": pw} if sid == "other-workload-write" else {"platform": p}))
    return {
        "legitimate_call": legit.effect,
        "execution_token_from_other_workload": {"effect": replay.effect, "reason": replay.reason},
        "approved_write_from_other_workload": {"effect": wreplay.effect, "reason": wreplay.reason, "rollbacks": replay_patches,
                                               "legitimate_workload_after": wlegit.effect},
        "expired_execution_token": {"effect": expired.effect, "reason": expired.reason},
        "tool_credential_wrong_audience": {"status": at_jira[0], "reason": at_jira[1]},
        "stolen_tool_credential_within_ttl": {"status": at_k8s_within[0], "reason": at_k8s_within[1], "ttl_min": p.broker.ttl / MIN},
        "stolen_tool_credential_after_ttl": {"status": at_k8s_after[0], "reason": at_k8s_after[1]},
        "shared_secret_from_anywhere_a_day_later": {"status": sa_replay[0], "reason": sa_replay[1]},
    }


# ---- I5 · impersonation vs delegation -----------------------------------------------------------------------------------
def i5() -> dict[str, Any]:
    runs = {}
    for mode in ("impersonation", "chain"):
        p = Platform(mode)
        maya_rollback(p)
        agent_entry = [e for e in p.tools["kubernetes"].log if e["verb"] == "patch"][-1]
        # Maya does the same thing herself, by hand, a minute later
        p.clock.advance(MIN)
        manual = user_credentials(p.clock, "maya@company.com", "exe-manual000000")["kubernetes"]
        p.tools["kubernetes"].call(manual, "deployments:patch", {"service": "payment-service", "to_version": "v4.17.2"})
        manual_entry = p.tools["kubernetes"].log[-1]
        strip = lambda e: {k: v for k, v in e.items() if k != "ts"}   # noqa: E731
        rec = p.audit.calls("rollbackDeployment")[-1]
        runs[mode] = {"kubernetes_entry": agent_entry, "manual_entry": manual_entry,
                      "agent_indistinguishable_from_human_in_tool_log": strip(agent_entry) == strip(manual_entry),
                      "platform_record_fields": sorted(rec), "agent_recorded": "agent" in rec, "actor_chain_recorded": "act_chain" in rec,
                      "tool_permissions_behind_the_call": sorted(p.tools["kubernetes"].grants[agent_entry["user.username"]])}
        same = runs[mode]["agent_indistinguishable_from_human_in_tool_log"]
        scenario(f"I5-{mode}-vs-manual", "I5", mode, "Impersonation vs delegation: the agent's rollback beside Maya's own",
                 {"invoker": "svc.web-portal (web console)", "on_behalf_of": "sre.maya", "agent": "agent.incident-intel",
                  "comparison": "Maya rolls back by hand a minute later", "identity_model": mode},
                 "the agent's action is distinguishable from Maya's" if mode == "chain" else "the agent's action looks exactly like Maya's",
                 f"agent recorded: {'yes' if 'agent' in rec else 'no'} · actor chain recorded: {'yes' if 'act_chain' in rec else 'no'} · "
                 f"indistinguishable in Kubernetes' log: {'yes' if same else 'no'}",
                 "broken" if same else "held", "Kubernetes log: the agent's patch is identical to Maya's manual patch" if same else None,
                 ["impersonation: agent action identical to Maya's own in Kubernetes' log", "impersonation loses the agent and the actor chain"]
                 if mode == "impersonation" else ["delegation: agent action distinguishable from Maya's own"],
                 [["Platform record fields", len(rec)], ["Tool permissions behind the call", len(runs[mode]["tool_permissions_behind_the_call"])]],
                 {"platform": p})
    identity = {"event_source", "event_id", "event_rule", "invoker", "invoker_credential", "on_behalf_of", "grant_id", "agent", "act_chain",
                "workload", "scopes", "token_id", "tool_identity", "tool_principal", "credential_id", "revocation"}
    runs["identity_fields_recorded"] = {m: sorted(identity & set(runs[m]["platform_record_fields"])) for m in ("impersonation", "chain")}
    runs["fields_lost_by_impersonation"] = sorted((identity & set(runs["chain"]["platform_record_fields"])) - set(runs["impersonation"]["platform_record_fields"]))
    return runs


# ---- I6 · privilege accumulation (derived from configuration) -----------------------------------------------------------
def i6() -> dict[str, Any]:
    sa, ti, caps = load("shared_sa.yaml"), load("tool_identities.yaml"), load("capabilities.yaml")["capabilities"]
    union = {(g["system"], perm) for g in sa["grants"] for perm in g["permissions"]}
    retired_only = {(g["system"], perm) for g in sa["grants"] if g.get("retired") for perm in g["permissions"]} - \
                   {(g["system"], perm) for g in sa["grants"] if not g.get("retired") for perm in g["permissions"]}
    needed = {(c["system"], c["verb"]) for c in caps.values()}
    per_identity = {k: len(v["permissions"]) for k, v in ti["tool_identities"].items()}
    inp = {"source": "config/shared_sa.yaml, config/tool_identities.yaml, config/capabilities.yaml (derived, not run)"}
    scenario("I6-shared_sa-accumulation", "I6", "shared_sa", "Privilege build-up: what the shared account holds", {**inp, "identity_model": "shared_sa"},
             "holds only what the platform needs", f"{len(union)} permissions held, {len(needed)} needed, {len(union - needed)} excess",
             "broken", "config/shared_sa.yaml: grants added for agents and never removed", ["shared account holds more than any tool identity"],
             [["Permissions held", len(union)], ["Needed", len(needed)], ["Excess", len(union - needed)],
              ["Grants for retired agents", sum(1 for g in sa["grants"] if g.get("retired"))]], {})
    scenario("I6-chain-tool-identities", "I6", "chain", "Privilege build-up: what each tool identity holds", {**inp, "identity_model": "chain"},
             "each tool identity holds only its capability class", f"{len(per_identity)} tool identities, at most {max(per_identity.values())} permissions each",
             "held", None, ["shared account holds more than any tool identity"],
             [["Tool identities", len(per_identity)], ["Most permissions on one identity", max(per_identity.values())]], {})
    return {"shared_account_permissions": len(union), "shared_account_grants": len(sa["grants"]),
            "grants_for_retired_agents": sum(1 for g in sa["grants"] if g.get("retired")), "permissions_only_retired_agents_needed": len(retired_only),
            "permissions_the_platform_needs": len(needed), "excess_permissions": len(union - needed),
            "tool_identities": len(per_identity), "max_permissions_per_tool_identity": max(per_identity.values()), "per_identity": per_identity,
            "every_agent_holds_via_shared_account": len(union)}


# ---- I7 · pause and re-exchange ---------------------------------------------------------------------------------------
def i7() -> dict[str, Any]:
    out = {}
    for label, mode, refresh in (("chain_reexchange", "chain", "reexchange"), ("chain_extend", "chain", "extend"), ("shared_sa", "shared_sa", None)):
        p = Platform(mode)
        ex = p.start("web", "cred-web", "agent.incident-intel", sso="sso-maya")
        if refresh:
            ex.refresh = refresh
        agent = IncidentIntel()
        for c in agent.investigate():
            p.call(ex, c)
        p.clock.advance(3 * MIN)
        first = p.call(ex, agent.remediate())
        p.clock.advance(7 * MIN)              # minute 10: Maya goes off call, her delegation is revoked
        p.revoke_delegation("sre.maya")
        p.clock.advance(30 * MIN)             # minute 40: the incident commander approves
        ok, _ = p.approve(first.approval_id, "ic.dev")
        final = p.call(ex, agent.remediate(), approval_id=first.approval_id)
        out[label] = {"approval_requested": first.effect, "approved": ok, "final": final.effect, "reason": final.reason, "rollbacks": k8s_patches(p),
                      "pause_min": 37, "revoked_at_min": 10}
        held = final.effect != "EXECUTED"
        scenario(f"I7-{mode}-{refresh or 'shared'}", "I7", mode, "The pause: " + {"reexchange": "re-exchange after approval", "extend": "extend the old token",
                                                                                   None: "shared account"}[refresh],
                 {"invoker": "svc.web-portal (web console)", "on_behalf_of": "sre.maya", "agent": "agent.incident-intel", "approval_wait_minutes": 37,
                  "revoked": "Maya's delegation at minute 10", "resume": refresh or "no token to refresh", "identity_model": mode},
                 "the revoked delegation stays revoked" if refresh == "reexchange" else "the rollback runs on stale authority",
                 f"approval {first.effect} · approved {'yes' if ok else 'no'} · final {final.effect} · rollbacks {k8s_patches(p)}",
                 "held" if held else "broken", None if held else "capability.call after the pause: executed on authority revoked at minute 10",
                 {"reexchange": ["re-exchange after the pause: revoked delegation stays revoked"], "extend": ["extending instead of re-exchanging lets the rollback through"],
                  None: []}[refresh], [["Final", final.effect], ["Rollbacks", k8s_patches(p)]], {"platform": p})
    return out


# ---- run -------------------------------------------------------------------------------------------------------------------
def run(run_id: str) -> Path:
    import datetime as dt

    from aid.freeze import check as freeze_check, declared
    fz = freeze_check()
    if not fz["ok"]:
        raise SystemExit(f"refusing to run: frozen files changed {fz['changed_guarded']} (log a deviation, then `aid freeze`)")
    started = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = ROOT / "runs" / run_id
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True)
    SCENARIOS.clear()
    res = {"I1": i1(), "I2": i2(), "I3": i3(), "I4": i4(), "I5": i5(), "I6": i6(), "I7": i7()}
    (base / "audit.jsonl").write_text(res["I1"].pop("chain_audit_jsonl"))
    (base / "tool-logs.json").write_text(json.dumps(res["I1"].pop("chain_tool_logs"), indent=1, sort_keys=True))
    for k, v in res.items():
        (base / f"{k}.json").write_text(json.dumps(v, indent=1, sort_keys=True, default=str))
    checks = checks_for(res)
    want = [{k: c[k] for k in ("id", "experiment", "arm", "kind", "check")} for c in declared()]
    got = [{k: c[k] for k in ("id", "experiment", "arm", "kind", "check")} for c in checks]
    if want != got:
        raise SystemExit("refusing to publish: the evaluated checks differ from proof/preregistration.toml")
    (base / "checks.json").write_text(json.dumps(checks, indent=1))
    facts = facts_for(res, checks)
    (base / "facts.json").write_text(json.dumps(facts, indent=1, sort_keys=True))
    sha = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(CONFIG.glob("*.yaml"))}
    (base / "manifest.json").write_text(json.dumps({
        "run_id": run_id, "python": pyplatform.python_version(), "source_commit": "unknown (not a git repository)",
        "randomness": "none: simulated clock, directory, attestation and tools; deterministic agent plans",
        "identity_models": {"A": "shared service account", "B": "user token (impersonation)", "C": "delegation chain"},
        "variable": "identity propagation and credential architecture",
        "tests": collected_tests(),
        "checks": len(checks), "experiment_checks": sum(c["experiment"] != "GA" for c in checks), "global_assertions": sum(c["experiment"] == "GA" for c in checks),
        "scenarios": len(SCENARIOS),
        "preregistration": {"file": "proof/preregistration.toml", "freeze": "proof/FREEZE.json", "deviations": "proof/DEVIATIONS.md",
                            "guarded_sha256": fz.get("guarded", {})},
        "policy_fixture_sha256": sha["policies.yaml"], "identity_fixture_sha256": {k: sha[k] for k in ("principals.yaml", "tool_identities.yaml", "shared_sa.yaml")},
        "scenario_fixture_sha256": hashlib.sha256(json.dumps({"provenance": PROV.model_dump() if hasattr(PROV, "model_dump") else str(PROV), "runtime": RUNTIME,
                                                              "capabilities": sha["capabilities.yaml"]}, sort_keys=True).encode()).hexdigest(),
        "config_sha256": sha,
        "agents": "deterministic plans (aid/agents.py); no model",
        "simulated": ["directory and identity provider (config/principals.yaml)", "workload attestation (SVIDs)",
                      "Kubernetes, Jira, Slack, telemetry and their audit logs (aid/tools.py)", "clock"],
        "real": ["token exchange, delegation and narrowing (aid/trust.py)", "attestation checks at the gateway", "token broker",
                 "capability gateway", "approvals", "hash-chained audit", "revocation levers"]}, indent=1))
    (base / "summary.md").write_text(summary_md(run_id, res, checks))
    write_scenarios(base, checks)
    # the one file that is not reproducible byte for byte: when this run was recorded, under which freeze (verify ignores it)
    (base / "recorded.json").write_text(json.dumps({"run_id": run_id, "recorded_at": started, "frozen_at": fz.get("frozen_at"),
                                                    "freeze_note": fz.get("note"), "code_changed_since_freeze": fz.get("changed_code", [])}, indent=1))
    from aid.story import story
    (base / "story.json").write_text(json.dumps(story(), indent=1, sort_keys=True, default=str))
    return base


def collected_tests() -> int:
    """pytest's own count of the test cases (parametrized cases included), read without running them."""
    import re
    import subprocess
    import sys
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"], cwd=ROOT, capture_output=True, text=True).stdout
    counts = [int(n) for n in re.findall(r"^tests/\S+\.py: (\d+)$", out, re.M)]     # `-q` prints one "file: N" line per file
    return sum(counts) if counts else -1


def write_scenarios(base: Path, checks: list[dict[str, Any]]) -> None:
    """runs/<id>/scenarios/<scenario>/{scenario.json, audit.jsonl, tool-logs.json, effects.json}: one folder per scenario."""
    known = {c["check"]: c["passed"] for c in checks}
    for sc in SCENARIOS:
        d = base / "scenarios" / sc["id"]
        d.mkdir(parents=True)
        unknown = [c for c in sc["checks"] if c not in known]
        assert not unknown, f"{sc['id']}: unknown checks {unknown}"
        meta = {k: v for k, v in sc.items() if k not in ("audit", "tool_logs", "effects")}
        meta["checks"] = [{"check": c, "passed": known[c]} for c in sc["checks"]]
        (d / "scenario.json").write_text(json.dumps(meta, indent=1, sort_keys=True, default=str))
        (d / "audit.jsonl").write_text("".join(json.dumps({"platform": label, **r}, sort_keys=True, default=str) + "\n"
                                               for label, rows in sc["audit"].items() for r in rows))
        (d / "tool-logs.json").write_text(json.dumps(sc["tool_logs"], indent=1, sort_keys=True, default=str))
        (d / "effects.json").write_text(json.dumps(sc["effects"], indent=1, sort_keys=True, default=str))


# kind: invariant (a property the delegation chain must hold) · control (the weak model is predicted to lose the property:
# passing means it did) · qualified (holds only within a stated bound).  arm: A shared account · B user token · C chain.
def checks_for(r: dict[str, Any]) -> list[dict[str, Any]]:
    I1, I2, I3, I4, I5, I6, I7 = (r[k] for k in ("I1", "I2", "I3", "I4", "I5", "I6", "I7"))
    m, ch = I1["modes"], I3["chain"]
    c = [
        ("I1", "ABC", "invariant", "the rollback executed once in every mode", all(v["executed"] == "EXECUTED" for v in m.values())),
        ("I1", "C", "invariant", "chain: the platform record answers all nine questions", m["chain"]["platform_answered"] == 9),
        ("I1", "ABC", "invariant", "every mode: the tool log answers at most three", all(v["tool_answered"] <= 3 for v in m.values())),
        ("I1", "A", "control", "shared account: Kubernetes sees one principal for three agents", m["shared_sa"]["multi_agent"]["distinct_kubernetes_principals"] == 1),
        ("I1", "A", "control", "shared account: no agent attributable from the platform record", m["shared_sa"]["multi_agent"]["agents_attributable_from_platform_audit"] == 0),
        ("I1", "C", "invariant", "chain: all three agents attributable from the platform record", m["chain"]["multi_agent"]["agents_attributable_from_platform_audit"] == 3),
        ("I1", "C", "invariant", "audit chain intact; an edited approver breaks it at that row", I1["tamper"]["intact_before"] and not I1["tamper"]["intact_after"]
         and I1["tamper"]["broken_at"] == I1["tamper"]["edited_row"]),
        ("I2", "C", "invariant", "chain: the deputy request is denied before any approval", I2["chain"]["first_decision"] == "DENY" and I2["chain"]["rollbacks"] == 0),
        ("I2", "C", "invariant", "chain: the callee's scopes narrowed", I2["chain"]["narrowed"] and I2["chain"]["maya_hop_narrowed"]),
        ("I2", "C", "invariant", "chain: an undeclared agent -> agent edge is refused", I2["chain"]["undeclared_edge_refused"]),
        ("I2", "A", "control", "shared account: the deputy rollback executes and hides its originator",
         I2["shared_sa"]["rollbacks"] == 1 and not I2["shared_sa"]["originator_visible_in_audit"]),
        ("I3", "C", "invariant", "control: nothing stops without a revocation", I3["control"]["affected"] == []),
        ("I3", "C", "qualified", "delegation: only Maya's executions stop, within one token lifetime",
         ch["delegation"]["affected"] == ["E2", "E5"] and max(ch["delegation"]["minutes_to_effect"].values()) <= I3["token_ttl_min"]),
        ("I3", "C", "invariant", "invoker credential: new executions from that head refused", str(ch["invoker_credential"]["new_event_execution_after_revocation"]).startswith("refused")),
        ("I3", "C", "invariant", "agent: every execution running that agent stops at its next call",
         ch["agent"]["affected"] == ["E1", "E2", "E4", "E5"] and max(ch["agent"]["minutes_to_effect"].values()) == 0),
        ("I3", "C", "invariant", "workload: executions on the other runtime keep running", "E3" in ch["workload"]["unaffected"] and len(ch["workload"]["affected"]) == 4),
        ("I3", "C", "invariant", "tool identity: one capability of one execution stops", ch["tool_identity"]["affected"] == ["E5"] and ch["tool_identity"]["partially_working"] == ["E5"]),
        ("I3", "A", "control", "shared account rotation stops all five executions", len(I3["shared_sa"]["rotate_shared_account"]["affected"]) == 5),
        ("I4", "C", "invariant", "execution token replayed from another workload is rejected", I4["execution_token_from_other_workload"]["effect"] == "REJECTED"),
        ("I4", "C", "invariant", "privileged write replayed from another workload is rejected with no side effect",
         I4["approved_write_from_other_workload"]["effect"] == "REJECTED" and I4["approved_write_from_other_workload"]["rollbacks"] == 0),
        ("I4", "C", "invariant", "expired execution token is rejected", I4["expired_execution_token"]["effect"] == "REJECTED"),
        ("I4", "C", "invariant", "tool credential rejected by a system it was not minted for", I4["tool_credential_wrong_audience"]["status"] == 401),
        ("I4", "C", "qualified", "stolen tool credential dies with its ten minutes", I4["stolen_tool_credential_after_ttl"]["status"] == 401),
        ("I4", "A", "control", "shared secret still works from anywhere a day later", I4["shared_secret_from_anywhere_a_day_later"]["status"] == 200),
        ("I5", "B", "control", "impersonation: agent action identical to Maya's own in Kubernetes' log", I5["impersonation"]["agent_indistinguishable_from_human_in_tool_log"]),
        ("I5", "C", "invariant", "delegation: agent action distinguishable from Maya's own", not I5["chain"]["agent_indistinguishable_from_human_in_tool_log"]),
        ("I5", "BC", "invariant", "impersonation loses the agent and the actor chain", not I5["impersonation"]["agent_recorded"] and I5["chain"]["actor_chain_recorded"]),
        ("I6", "AC", "invariant", "shared account holds more than any tool identity", I6["shared_account_permissions"] > I6["max_permissions_per_tool_identity"]),
        ("I7", "C", "invariant", "re-exchange after the pause: revoked delegation stays revoked", I7["chain_reexchange"]["final"] == "REJECTED" and I7["chain_reexchange"]["rollbacks"] == 0),
        ("I7", "C", "control", "extending instead of re-exchanging lets the rollback through", I7["chain_extend"]["rollbacks"] == 1),
    ]
    out, n = [], {}
    for e, arm, kind, t, ok in c:
        n[e] = n.get(e, 0) + 1
        out.append({"id": f"{e}-{n[e]:02d}", "experiment": e, "arm": arm, "kind": kind, "check": t, "passed": bool(ok)})
    return out + global_assertions(r)


def global_assertions(r: dict[str, Any]) -> list[dict[str, Any]]:
    """The fixed identity invariants (G01–G11), each computed from the experiments' own results.  Arm C unless stated."""
    I1, I2, I3, I4, I5, I7 = (r[k] for k in ("I1", "I2", "I3", "I4", "I5", "I7"))
    ch, rec = I3["chain"], I1["modes"]["chain"]["platform_record"]
    targeted = {k: v for k, v in ch.items()}
    g = [
        ("G01", "delegation never widens authority (the callee's scopes are within the caller's after every hop)",
         set(I2["chain"]["callee_scopes"]) <= set(I2["chain"]["caller_scopes"]) and I2["chain"]["narrowed"] and I2["chain"]["maya_hop_narrowed"]),
        ("G02", "a delegated write whose originator lacks the authority is denied, not silently executed",
         I2["chain"]["first_decision"] == "DENY" and I2["chain"]["rollbacks"] == 0 and I2["chain"]["originator_visible_in_audit"]),
        ("G03", "a credential replayed from the wrong workload causes no privileged side effect",
         I4["approved_write_from_other_workload"]["effect"] == "REJECTED" and I4["approved_write_from_other_workload"]["rollbacks"] == 0),
        ("G04", "a revoked identity cannot mint new execution authority",
         str(ch["invoker_credential"]["new_event_execution_after_revocation"]).startswith("refused") and I7["chain_reexchange"]["final"] == "REJECTED"),
        ("G05", "unrelated executions survive every targeted revocation", all(len(v["unaffected"]) >= 1 for v in targeted.values())),
        ("G06", "rotating the shared account stops more executions than any targeted lever",
         len(I3["shared_sa"]["rotate_shared_account"]["affected"]) > max(len(v["affected"]) for v in targeted.values())),
        ("G07", "agent identity and runtime identity stay distinct in the record", bool(rec.get("agent")) and bool(rec.get("workload")) and rec["agent"] != rec["workload"]),
        ("G08", "impersonation does not pass for delegation provenance",
         not I5["impersonation"]["agent_recorded"] and not I5["impersonation"]["actor_chain_recorded"] and I5["chain"]["actor_chain_recorded"]),
        ("G09", "no tool log is complete upstream provenance (every tool log answers fewer than nine questions)",
         all(v["tool_answered"] < 9 for v in I1["modes"].values())),
        ("G10", "the platform record reconstructs the whole identity chain (nine of nine)", I1["modes"]["chain"]["platform_answered"] == 9),
        ("G11", "tampering with the platform audit is detected at the edited row", I1["tamper"]["intact_before"] and not I1["tamper"]["intact_after"]
         and I1["tamper"]["broken_at"] == I1["tamper"]["edited_row"]),
    ]
    return [{"id": gid, "experiment": "GA", "arm": "C" if gid not in ("G06", "G09") else ("AC" if gid == "G06" else "ABC"), "kind": "invariant",
             "check": t, "passed": bool(ok)} for gid, t, ok in g]


def facts_for(r: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    f: dict[str, Any] = {}

    def put(k: str, v: Any, src: str) -> None:
        f[k] = {"value": v, "source": src}

    put("checks.passed", sum(c["passed"] for c in checks), "checks.json")
    put("checks.total", len(checks), "checks.json")
    put("checks.failed", sum(not c["passed"] for c in checks), "checks.json")
    put("checks.experiment", sum(c["experiment"] != "GA" for c in checks), "checks.json")
    put("checks.global", sum(c["experiment"] == "GA" for c in checks), "checks.json")
    put("checks.global_passed", sum(c["passed"] for c in checks if c["experiment"] == "GA"), "checks.json")
    put("checks.qualified", sum(c["kind"] == "qualified" for c in checks), "checks.json")
    put("checks.control", sum(c["kind"] == "control" for c in checks), "checks.json")
    for mode, v in r["I1"]["modes"].items():
        put(f"i1.{mode}.platform_answers", v["platform_answered"], "I1.json")
        put(f"i1.{mode}.tool_log_answers", v["tool_answered"], "I1.json")
        put(f"i1.{mode}.tool_principal", v["tool_principal"], "I1.json")
        put(f"i1.{mode}.tool_permissions", v["tool_authorized_permissions"], "I1.json")
        put(f"i1.{mode}.k8s_principals", v["multi_agent"]["distinct_kubernetes_principals"], "I1.json")
        put(f"i1.{mode}.agents_attributable", v["multi_agent"]["agents_attributable_from_platform_audit"], "I1.json")
        put(f"i1.{mode}.k8s_actions", v["multi_agent"]["kubernetes_actions"], "I1.json")
    put("i1.impersonation.fallbacks", r["I1"]["modes"]["impersonation"]["multi_agent"]["impersonation_fallbacks"], "I1.json")
    put("i1.questions", len(QUESTIONS), "I1.json")
    put("i1.tamper.rows", r["I1"]["tamper"]["rows"], "I1.json")
    put("i1.tamper.broken_at", r["I1"]["tamper"]["broken_at"], "I1.json")
    for mode, v in r["I2"].items():
        put(f"i2.{mode}.first_decision", v["first_decision"], "I2.json")
        put(f"i2.{mode}.rollbacks", v["rollbacks"], "I2.json")
    put("i2.chain.rule", r["I2"]["chain"]["rule"], "I2.json")
    put("i2.chain.callee_scopes", ", ".join(r["I2"]["chain"]["callee_scopes"]), "I2.json")
    put("i2.chain.caller_scopes", ", ".join(r["I2"]["chain"]["caller_scopes"]), "I2.json")
    for layer, v in r["I3"]["chain"].items():
        put(f"i3.{layer}.affected", len(v["affected"]), "I3.json")
        put(f"i3.{layer}.max_minutes", max(v["minutes_to_effect"].values()) if v["minutes_to_effect"] else 0, "I3.json")
    put("i3.shared_sa.affected", len(r["I3"]["shared_sa"]["rotate_shared_account"]["affected"]), "I3.json")
    put("i3.executions", len(r["I3"]["executions"]), "I3.json")
    put("i3.token_ttl_min", r["I3"]["token_ttl_min"], "I3.json")
    put("i3.invoker_credential.new_start", r["I3"]["chain"]["invoker_credential"]["new_event_execution_after_revocation"], "I3.json")
    I4 = r["I4"]
    put("i4.replay_status", I4["execution_token_from_other_workload"]["effect"], "I4.json")
    put("i4.write_replay_status", I4["approved_write_from_other_workload"]["effect"], "I4.json")
    put("i4.write_replay_rollbacks", I4["approved_write_from_other_workload"]["rollbacks"], "I4.json")
    put("i4.write_replay_legit_after", I4["approved_write_from_other_workload"]["legitimate_workload_after"], "I4.json")
    put("i4.replay_reason", I4["execution_token_from_other_workload"]["reason"], "I4.json")
    put("i4.wrong_audience_status", I4["tool_credential_wrong_audience"]["status"], "I4.json")
    put("i4.stolen_within_ttl_status", I4["stolen_tool_credential_within_ttl"]["status"], "I4.json")
    put("i4.stolen_after_ttl_status", I4["stolen_tool_credential_after_ttl"]["status"], "I4.json")
    put("i4.shared_secret_day_later_status", I4["shared_secret_from_anywhere_a_day_later"]["status"], "I4.json")
    put("i4.tool_credential_ttl_min", I4["stolen_tool_credential_within_ttl"]["ttl_min"], "I4.json")
    I5 = r["I5"]
    put("i5.impersonation.indistinguishable", I5["impersonation"]["agent_indistinguishable_from_human_in_tool_log"], "I5.json")
    put("i5.chain.indistinguishable", I5["chain"]["agent_indistinguishable_from_human_in_tool_log"], "I5.json")
    put("i5.fields_lost", len(I5["fields_lost_by_impersonation"]), "I5.json")
    put("i5.impersonation.permissions", len(I5["impersonation"]["tool_permissions_behind_the_call"]), "I5.json")
    put("i5.chain.permissions", len(I5["chain"]["tool_permissions_behind_the_call"]), "I5.json")
    for k in ("shared_account_permissions", "shared_account_grants", "grants_for_retired_agents", "permissions_only_retired_agents_needed",
              "permissions_the_platform_needs", "excess_permissions", "tool_identities", "max_permissions_per_tool_identity"):
        put(f"i6.{k}", r["I6"][k], "I6.json")
    for k, v in r["I7"].items():
        put(f"i7.{k}.final", v["final"], "I7.json")
        put(f"i7.{k}.rollbacks", v["rollbacks"], "I7.json")
    put("i7.pause_min", r["I7"]["chain_reexchange"]["pause_min"], "I7.json")
    put("i7.revoked_at_min", r["I7"]["chain_reexchange"]["revoked_at_min"], "I7.json")
    for mode in ("shared_sa", "impersonation"):
        put(f"i2.{mode}.approver_saw", r["I2"][mode]["approver_saw_requester"], "I2.json")
        put(f"i2.{mode}.originator_visible", r["I2"][mode]["originator_visible_in_audit"], "I2.json")
    put("i2.chain.originator_visible", r["I2"]["chain"]["originator_visible_in_audit"], "I2.json")
    put("i2.chain.undeclared_edge_refused", r["I2"]["chain"]["undeclared_edge_refused"], "I2.json")
    for layer, v in r["I3"]["chain"].items():
        put(f"i3.{layer}.unaffected", len(v["unaffected"]), "I3.json")
    put("i3.agent.new_start", r["I3"]["chain"]["agent"]["new_event_execution_after_revocation"], "I3.json")
    put("i5.platform_record_fields", len(I5["chain"]["platform_record_fields"]), "I5.json")
    rec = r["I1"]["modes"]["chain"]["platform_record"]
    put("i1.chain.scopes", ", ".join(rec["scopes"]), "I1.json")
    put("i1.chain.invoker", rec["invoker"], "I1.json")
    put("i1.chain.on_behalf_of", rec["on_behalf_of"], "I1.json")
    put("i1.chain.approver", rec["authorized_by"], "I1.json")
    put("i1.chain.credential_ttl_min", round((rec["credential_exp"] - r["I1"]["modes"]["chain"]["kubernetes_entry"]["ts"]) / 60), "I1.json")
    return f


def summary_md(run_id: str, r: dict[str, Any], checks: list[dict[str, Any]]) -> str:
    passed = sum(c["passed"] for c in checks)
    m = r["I1"]["modes"]
    lines = [f"# T1 run {run_id}", "", f"**{passed}/{len(checks)} checks passed.** Deterministic run: simulated directory, workloads, "
             "tools and clock; real token exchange, delegation, attestation checks, broker, gateway, approvals, audit chain and revocation.", "",
             "## The nine questions, answered from each record", "", "| Mode | Platform record | Tool's own log | Kubernetes saw |", "|---|---|---|---|"]
    lines += [f"| {k} | {v['platform_answered']}/9 | {v['tool_answered']}/9 | `{v['tool_principal']}` |" for k, v in m.items()]
    lines += ["", "## Revocation drill (5 concurrent executions, revoked at minute 5)", "", "| Layer | Executions affected | Max minutes to effect |", "|---|---|---|"]
    for k, v in r["I3"]["chain"].items():
        lines.append(f"| {k} | {', '.join(v['affected']) or 'none'} | {max(v['minutes_to_effect'].values()) if v['minutes_to_effect'] else '-'} |")
    sa = r["I3"]["shared_sa"]["rotate_shared_account"]
    lines += [f"| shared account rotation | {', '.join(sa['affected'])} | {max(sa['minutes_to_effect'].values())} |", "",
              "## Checks", "", "| Id | Check | Result |", "|---|---|---|"]
    lines += [f"| {c['id']} | {c['check']} ({c['kind']}, arm {c['arm']}) | {'pass' if c['passed'] else '**FAIL**'} |" for c in checks]
    return "\n".join(lines) + "\n"
