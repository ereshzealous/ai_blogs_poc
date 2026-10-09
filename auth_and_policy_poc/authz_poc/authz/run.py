"""Run the incident scenario, the context sweep and the invariants; write the evidence the articles quote.

    python3 -m authz.run [--out runs/2026-09-29-recorded]

Outputs: decisions.jsonl (hash-chained decision log), facts.json (every number the articles use), timeline.json/.md,
sweep.json/.md, invariants.json, expectations.json, receipt.json and transcript.txt.
Deterministic: same config and code, same bytes (the clock is the scenario's, ids are digests, no network).
"""

from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from .evidence import WEIGHTS, fixed
from .model import Request
from .world import ROOT, scenario, world

RUN_ID = "2026-09-29-recorded"
ENFORCED = {"ALLOW": "executed", "ALLOW_WITH_CONSTRAINTS": "executed", "ALLOW_WITH_APPROVAL": "pending_approval", "DENY": "denied"}


def step_request(scn: dict, step: dict, **over) -> Request:
    acting_for = over.get("acting_for", scn["agent"]["acting_for"]) or None
    return Request(scn["agent"]["principal"], acting_for, step["action"], over.get("resource", step["resource"]),
                   over.get("environment", step.get("environment")),
                   {"time": over.get("time", step["time"]), "incident_id": scn["incident"]["id"]},
                   dict(step.get("arguments", {})))


def last_decision(gw) -> dict:
    return next(r["record"] for r in reversed(gw.audit.records) if r["kind"] == "policy.decision")


def sweep_cases(scn: dict) -> list[tuple[dict, Any]]:
    """The context sweep: one production rollback re-asked under each [[sweep.case]] of scenario.toml. The same table
    drives sweep.json, the expectations and AUTHZ-INV-10, so the published table and the tested table cannot drift."""
    base_step = {"time": scn["step"][-1]["time"], **scn["sweep"]}
    out = []
    for case in scn["sweep"]["case"]:
        g = world({k: case[k] for k in ("severity", "state") if k in case}, evidence=fixed(case.get("evidence", list(WEIGHTS))))
        req = step_request(scn, base_step, **{k: case[k] for k in ("environment", "time", "resource", "acting_for") if k in case})
        out.append((case, g.pdp.evaluate(req)))
    return out


def simulate() -> dict[str, Any]:
    """The incident, in memory: the ten proposed calls, both approval attempts, the re-submitted call, and the sweep."""
    scn = scenario()
    gw = world()
    pip = gw.pdp.pip
    inc = scn["incident"]
    lines, rows = [], []

    gw.audit.write("event.received", inc["opened"], {
        "source": inc["source"], "incident_id": inc["id"], "service": inc["service"], "severity": inc["severity"],
        "error_rate": inc["error_rate"], "slo": inc["slo"], "annotation": inc["annotation"]})
    gw.audit.write("identity.established", inc["opened"], {
        "principal": scn["agent"]["principal"], "registered_as": pip.principals["agents"][scn["agent"]["principal"]]["registered_as"],
        "acting_for": scn["agent"]["acting_for"], "delegation": pip.relationships["delegation"][0]["id"],
        "invoker": "svc.monitoring-webhook"})

    approval_id, parked = None, None
    for i, step in enumerate(scn["step"], 1):
        req = step_request(scn, step)
        res = gw.invoke(req)
        dec = last_decision(gw)
        a = dec["attributes"]
        rows.append({"n": i, "time": step["time"][11:16], "at": step["time"], "why": step["why"], "action": req.action,
                     "resource": req.resource, "environment": req.environment,
                     "evidence": a.get("evidence_score"), "evidence_signals": a.get("evidence_signals"),
                     "decision": dec["decision"], "reason": dec["reason"], "matched_rules": dec["matched_rules"],
                     "agent_view": dec["agent_view"], "status": res["status"],
                     "constraints_applied": res.get("constraints_applied", [])})
        ev = f"  evidence {a['evidence_score']}" if "evidence_score" in a else ""
        lines.append(f"{step['time'][11:19]}  {req.action:<32} {req.environment:<10} -> {res['status']}  [{dec['decision']}]{ev}")
        if res["status"] == "pending_approval":
            approval_id, parked = res["approval_id"], req

    approvals = []
    for a in scn["approval"]:
        r = gw.approve(approval_id, a["approver"], a["time"])
        approvals.append({"approver": a["approver"], "at": a["time"], "outcome": "approved" if r["approved"] else "rejected",
                          "reason": r["reason"], "expect": a.get("expect")})
        lines.append(f"{a['time'][11:19]}  approval {approval_id} by {a['approver']:<20} -> {r['reason']}")
    resubmitted = replace(parked, context={**parked.context, "time": scn["resume"]["time"]})
    final = gw.execute_approved(approval_id, resubmitted)
    lines.append(f"{scn['resume']['time'][11:19]}  agent re-submits the approved call: binding ok, policy re-check "
                 f"-> {final['status']} {final.get('output', '')}")
    return {"scn": scn, "gw": gw, "rows": rows, "lines": lines, "approvals": approvals, "final": final,
            "approval_id": approval_id, "sweep": sweep_cases(scn)}


def receipt(gw, approval_id: str) -> dict[str, Any]:
    """The production rollback's receipt, assembled from the log: every record from the decision that required approval
    to the execution, and the answers an auditor needs, each read from a record (never restated by hand)."""
    recs = gw.audit.records
    req_rec = next(r for r in recs if r["kind"] == "approval.requested" and r["record"]["approval_id"] == approval_id)
    first = next(r for r in recs if r["kind"] == "policy.decision" and r["record"]["decision_id"] == req_rec["record"]["decision_id"])
    recheck = next(r for r in recs if r["kind"] == "policy.decision" and r["record"]["recheck_of"] == first["record"]["decision_id"])
    exe = next(r for r in recs if r["kind"] == "tool.executed" and r["record"]["decision_id"] == recheck["record"]["decision_id"])
    attempts = [r for r in recs if r["kind"] in ("approval.granted", "approval.rejected") and r["record"]["approval_id"] == approval_id]
    d, x = first["record"], exe["record"]
    return {
        "reconstruction": {
            "who": d["principal"], "acting_for": d["acting_for"], "delegation_chain": d["delegation_chain"],
            "requested": d["action"], "against": d["resource"], "environment": d["environment"], "arguments": d["arguments"],
            "request_fingerprint": d["request_fingerprint"],
            "context": {k: d["attributes"][k] for k in ("severity", "incident_state", "change_window", "risk", "tier",
                                                          "evidence_score", "evidence_signals") if k in d["attributes"]},
            "context_sources": {k: d["attribute_sources"][k] for k in ("severity", "incident_state", "change_window",
                                                                        "evidence_score") if k in d["attribute_sources"]},
            "policy_version": d["policy_version"], "grants": d["grants"], "matched_rules": d["matched_rules"],
            "decision": d["decision"], "audit_reason": d["reason"], "caller_view": d["agent_view"],
            "constraints": d["constraints"],
            "approval": {"approval_id": approval_id, "approver_role": req_rec["record"]["approver_role"],
                         "expires_at": req_rec["record"]["expires_at"],
                         "attempts": [{"approver": r["record"]["approver"], "time": r["time"], "result": r["record"]["result"]} for r in attempts]},
            "recheck": {"decision_id": recheck["record"]["decision_id"], "time": recheck["time"], "decision": recheck["record"]["decision"]},
            "execution": {"time": exe["time"], "credential": x["credential"], "approved_by": x["approved_by"], "output": x["output"]},
        },
        "records": [r for r in recs if first["seq"] <= r["seq"] <= exe["seq"] and (
            r is first or r is exe or r is recheck or r is req_rec or r in attempts)],
    }


def run(out: Path) -> dict:
    from .invariants import check_all  # imported here: the invariants replay simulate()

    sim = simulate()
    scn, gw, rows, lines, approvals, final = sim["scn"], sim["gw"], sim["rows"], sim["lines"], sim["approvals"], sim["final"]
    out.mkdir(parents=True, exist_ok=True)

    sweep = [{"context": c["label"], "decision": d.decision, "rule": ", ".join(d.matched) or "-", "reason": d.reason,
              "evidence": d.attributes.get("evidence_score")} for c, d in sim["sweep"]]
    invariants = check_all()

    ok = gw.audit.verify()
    tampered = copy.deepcopy(gw.audit)
    for r in tampered.records:
        if r["kind"] == "policy.decision" and r["record"]["decision"] == "DENY":
            r["record"]["decision"] = "ALLOW"
            break
    tamper_detected = not tampered.verify()

    decisions = [r["record"] for r in gw.audit.records if r["kind"] == "policy.decision"]
    first_pass = [r for r in decisions if not r["recheck_of"]]
    rollbacks = [r for r in rows if r["action"] == "kubernetes.rollbackDeployment" and r["resource"] == "deployment/payment-service"
                 and r["environment"] == "production"]
    executed = [r for r in gw.audit.records if r["kind"] == "tool.executed"]
    facts = {
        "run_id": out.name,
        "policy_version": decisions[0]["policy_version"],
        "tool_calls_proposed": len(scn["step"]),
        "decisions_total": len(decisions),
        "decisions_by_type": dict(Counter(r["decision"] for r in first_pass)),
        "executed": len(executed),
        "blocked": sum(1 for r in first_pass if r["decision"] == "DENY"),
        "credentials_issued": sum(1 for r in executed if r["record"].get("credential")),
        "approvals_requested": sum(1 for r in gw.audit.records if r["kind"] == "approval.requested"),
        "approvals_rejected": sum(1 for r in gw.audit.records if r["kind"] == "approval.rejected"),
        "approvals_granted": sum(1 for r in gw.audit.records if r["kind"] == "approval.granted"),
        "evidence_weights": WEIGHTS,
        "production_rollback_attempts": [{"time": r["at"], "evidence": r["evidence"], "signals": r["evidence_signals"],
                                          "decision": r["decision"]} for r in rollbacks],
        "audit_records": len(gw.audit.records),
        "audit_chain_valid": ok,
        "tamper_detected": tamper_detected,
        "sweep_cases": len(sweep),
        "sweep_decisions": dict(Counter(s["decision"] for s in sweep)),
        "invariants_total": len(invariants),
        "invariants_passed": sum(1 for i in invariants if i["passed"]),
        "namespaces_after_run": sorted(gw.tools["_k8s"].namespaces),
        "payment_service_production_version": gw.tools["_k8s"].deployments[("payment-service", "production")]["version"],
    }

    # expectations: every recorded outcome against the scenario's intended one (expect / expect_rule)
    def check(kind, cid, label, expect, rule, actual, matched, status=None):
        ok_dec = expect is None or actual == expect
        ok_rule = rule is None or rule in matched
        ok_enf = status is None or ENFORCED.get(actual) == status
        return {"kind": kind, "id": cid, "label": label, "expect": expect, "expect_rule": rule, "actual": actual,
                "matched_rules": matched, "status": status, "decision_ok": ok_dec, "rule_ok": ok_rule, "enforced_ok": ok_enf,
                "passed": ok_dec and ok_rule and ok_enf}

    exp = [check("step", f"step-{r['n']:02d}", f"{r['time']} {r['action']} {r['resource'].split('/')[1]} ({r['environment']})",
                 st.get("expect"), st.get("expect_rule"), r["decision"], r["matched_rules"], r["status"])
           for r, st in zip(rows, scn["step"])]
    exp += [check("approval", f"approval-{i}", f"{a['at'][11:16]} approval by {a['approver']}", a["expect"], None, a["outcome"], [])
            for i, a in enumerate(approvals, 1)]
    exp.append(check("resume", "resume", f"{scn['resume']['time'][11:16]} re-submitted approved call", scn["resume"].get("expect"), None,
                     final["status"], []))
    exp += [check("sweep", f"sweep-{i}", c["label"], c.get("expect"), c.get("expect_rule"), d.decision, list(d.matched))
            for i, (c, d) in enumerate(sim["sweep"], 1)]

    gw.audit.dump(out / "decisions.jsonl")
    (out / "facts.json").write_text(json.dumps(facts, indent=2) + "\n")
    (out / "transcript.txt").write_text("\n".join(lines) + "\n")
    (out / "timeline.json").write_text(json.dumps(rows, indent=2) + "\n")
    (out / "sweep.json").write_text(json.dumps(sweep, indent=2) + "\n")
    (out / "invariants.json").write_text(json.dumps(invariants, indent=2) + "\n")
    (out / "expectations.json").write_text(json.dumps({"checks": len(exp), "passed": sum(e["passed"] for e in exp),
                                                       "approvals": approvals, "results": exp}, indent=2) + "\n")
    (out / "receipt.json").write_text(json.dumps(receipt(gw, sim["approval_id"]), indent=2) + "\n")
    md = ["| # | Time | Agent proposes | Environment | Evidence | Decision | Why (audit view) |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['n']} | {r['time']} | `{r['action']}` {r['resource'].split('/')[1]} | {r['environment']} | "
                  f"{r['evidence'] if r['evidence'] is not None else '–'} | **{r['decision']}** | {r['reason']} |")
    (out / "timeline.md").write_text("\n".join(md) + "\n")
    md = ["| Context | Decision | Rule | Reason |", "|---|---|---|---|"]
    md += [f"| {s['context']} | **{s['decision']}** | `{s['rule']}` | {s['reason']} |" for s in sweep]
    (out / "sweep.md").write_text("\n".join(md) + "\n")
    return facts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "runs" / RUN_ID))
    out = Path(ap.parse_args().out)
    facts = run(out)
    print((out / "transcript.txt").read_text())
    print(json.dumps(facts, indent=2))


if __name__ == "__main__":
    main()
