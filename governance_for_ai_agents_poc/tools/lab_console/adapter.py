"""Read T5's run directories for the Lab Console: runs, scenarios, recorded events from every layer, answers, data lineage.

Every value comes from observability_governance_poc/runs/<run>/scenarios/<scenario>/: result.json and reconstruction.json
(the scorer), truth.json (ground truth from the systems of record), evidence/audit-events.jsonl (L2), logs/*.log (L0/L1),
telemetry/spans-*.jsonl (L1), world/external-transactions.json (the deployment API's own request log), spec.json, procs/.
"""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POC = ROOT / "observability_governance_poc"
RUNS = POC / "runs"
PREREG = tomllib.loads((POC / "experiments" / "preregistration.toml").read_text())
CASES = {c["id"]: c for c in PREREG["case"]}
ORDER = [c["id"] for c in PREREG["case"]]
LAYERS = {"L0": "Application logs", "L1": "Logs + traces", "L2": "Execution lineage"}
STEPS = ["trigger", "context", "model", "policy", "approval", "tool", "deploy API", "verify", "complete"]
INC = "INC-4471"
QUESTIONS = {
    "Q1": "What triggered the execution?", "Q2": "Which principal initiated it (and for whom)?", "Q3": "Which agent and version acted?",
    "Q4": "Which model and configuration produced the proposal?", "Q5": "Which policy and version evaluated it?", "Q6": "Was approval required?",
    "Q7": "Who approved or rejected it?", "Q8": "Which capability and arguments reached production?", "Q9": "How many attempts reached the production API?",
    "Q10": "Did the side effect occur?", "Q11": "How many times did production change?", "Q12": "Was the incident actually mitigated?",
    "Q13": "Can the evidence's integrity be verified?"}


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def discover(primary: str) -> list[dict]:
    out = []
    names = [primary] + sorted(p.name for p in RUNS.iterdir() if p.is_dir() and p.name != primary and not p.name.startswith("_"))
    for name in names:
        d = RUNS / name
        if not (d / "scenarios").is_dir() or not any((d / "scenarios").glob("*/result.json")):
            continue
        man = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
        out.append({"id": name, "dir": d, "scen": d / "scenarios", "kind": man.get("kind", "recorded"), "manifest": man,
                    "label": f"{name} · {man.get('kind', 'recorded')} run"})
    return out


def scenarios(run: dict) -> list[tuple[Path, dict]]:
    sc = []
    for p in run["scen"].iterdir():
        if (p / "result.json").exists():
            sc.append((p, {"result": json.loads((p / "result.json").read_text()), "recon": json.loads((p / "reconstruction.json").read_text()),
                           "truth": json.loads((p / "truth.json").read_text()), "spec": json.loads((p / "spec.json").read_text())}))
    return sorted(sc, key=lambda x: ORDER.index(x[0].name))


def _s(v, n=110) -> str:
    s = v if isinstance(v, str) else json.dumps(v, sort_keys=True, default=str)
    return s if len(s) <= n else s[: n - 1] + "…"


def target(sd: Path) -> tuple[str | None, str | None]:
    for r in jl(sd / "evidence" / "audit-events.jsonl"):
        if r["event_type"] == "execution.started" and not json.loads(r["payload_json"])["background"]:
            return r["execution_id"], r["trace_id"]
    return None, None


EV_STEP = {"execution.started": "trigger", "workflow.resumed": "trigger", "context.accessed": "context", "model.invoked": "model",
           "decision.proposed": "model", "policy.evaluated": "policy", "approval.requested": "approval", "approval.decided": "approval",
           "gateway.denied": "tool", "action.authorized": "tool", "attempt.started": "tool", "attempt.finished": "tool", "attempt.reconciled": "tool",
           "effect.verified": "verify", "execution.completed": "complete"}


def _evidence_text(t: str, p: dict, r: dict) -> tuple[str, str]:
    tone = ""
    if t == "execution.started":
        s = f"**execution started** {p['incident']} {p['severity']} · invoker `{p['invoker']}` · for `{p['on_behalf_of']}` · agent {p['agent_version']} · policy `{p['pins']['policy']}` · config `{p['pins']['agent_config']}`"
    elif t == "workflow.resumed":
        s, tone = f"**workflow resumed** from `{p['from_step']}` · previous pid {p['previous_pid']} · in flight {p['in_flight'] or 'none'}", "warn"
    elif t == "context.accessed":
        s, tone = f"**context** `{p['dataset']}` ({p['classification']}) → {p['decision']}", "ok" if p["decision"] == "ALLOW" else "bad"
    elif t == "model.invoked":
        s = f"**model** {p['model']} `{p['model_digest'][:19]}…` · `{p['prompt_template']}` · `{p['agent_config']}` · {p['input_tokens']}+{p['output_tokens']} tokens · {'replayed' if p['replayed'] else 'live'}"
    elif t == "decision.proposed":
        s = f"**proposal** {p['capability']} `{p['target']}` {p['arguments'].get('to_version', '')} · source {p['source']} · “{_s(p['rationale_summary'], 90)}”"
    elif t == "policy.evaluated":
        s, tone = f"**policy** `{p['policy_id']}@{p['policy_version']}` → {p['decision']} · rule `{p['rule']}` · obligations {_s(p['obligations'], 90)}", \
            "bad" if p["decision"] == "DENY" else "warn"
    elif t == "approval.requested":
        s, tone = f"**approval requested** `{p['approval_id']}` · quorum {p['quorum']} · {', '.join(p['eligible_roles'])} · digest `{p['action_digest'][:19]}…`", "warn"
    elif t == "approval.decided":
        s, tone = f"**{p['approver']}** ({p['role']}) {p['decision']} · signature {'valid' if p['signature_valid'] else 'INVALID'} · digest {'matches' if p['digest_match'] else 'MISMATCH'}", \
            "ok" if p["decision"] == "APPROVED" else "bad"
    elif t == "gateway.denied":
        s, tone = f"**gateway refused** {p['capability']} · {p['reason']} · path: {p['path']}", "bad"
    elif t == "action.authorized":
        s = f"**action authorized** `{r['action_id']}` · idempotency key `{p['idempotency_key']}` · tool identity `{p['tool_identity'].split('/')[-1]}` · approvals {p['approval_ids'] or 'none'}"
    elif t == "attempt.started":
        s = f"**attempt {p['attempt']} started** `{r['attempt_id']}` · request `{p['request_id']}` · key `{p['idempotency_key']}`"
    elif t == "attempt.finished":
        bad = p["result"] in ("TIMEOUT", "UNAVAILABLE", "CONNECTION_ERROR", "REFUSED")
        s, tone = f"**attempt {p['attempt']} finished** {p['result']} · HTTP {p['http_status']} · txn `{p['external_transaction_id']}` · {round(p['latency_ms'])} ms" \
            + (f" · {p['error']}" if p.get("error") else ""), "bad" if bad else "ok"
    elif t == "attempt.reconciled":
        s, tone = f"**attempt {p['attempt']} reconciled** {p['result']} · txn `{p['external_transaction_id']}` · by {p['method']}", "ok"
    elif t == "effect.verified":
        s, tone = f"**effect verified = {p['verified']}** · revision {p['observed_before']['revision']} → {p['observed_after']['revision']} · version {p['observed_after']['version']} · healthy {p['health']['healthy']}", \
            "ok" if p["verified"] else "bad"
    elif t == "execution.completed":
        s, tone = f"**execution completed** {p['outcome']} · {p['reason']}", "ok" if p["mitigated"] else "bad"
    else:
        s = t
    return s, tone


def events(sd: Path) -> list[dict]:
    """The target execution's recorded events from every layer and the system of record, in wall-clock order."""
    xid, tid = target(sd)
    ev, o = [], 0

    def add(ts, step, text, tone, src, layer, pid=None):
        nonlocal o
        o += 1
        ev.append({"ts": ts, "o": o, "step": step, "text": text, "tone": tone, "src": src, "layer": layer, "pid": pid})

    for i, r in enumerate(jl(sd / "evidence" / "audit-events.jsonl")):
        if r["execution_id"] != xid:
            continue
        text, tone = _evidence_text(r["event_type"], json.loads(r["payload_json"]), r)
        add(r["occurred_at"], EV_STEP.get(r["event_type"], "trigger"), text, tone, f"evidence/audit-events.jsonl[{i}] (seq {r['seq']})", "L2")
    tool_rids = set()
    for comp in ("agent", "model-gateway", "policy-decisions", "approval-service", "tool-gateway", "deploy-api"):
        for i, r in enumerate(jl(sd / "logs" / f"{comp}.log")):
            mine = (r.get("incident") == INC or r.get("trace_id") == tid or (r.get("input") or {}).get("incident") == INC)
            if comp == "deploy-api":
                mine = r.get("trace_id") == tid or r.get("request_id") in tool_rids
            if not mine:
                continue
            if comp == "tool-gateway" and r.get("request_id"):
                tool_rids.add(r["request_id"])
            step = {"agent": "trigger", "model-gateway": "model", "policy-decisions": "policy", "approval-service": "approval",
                    "tool-gateway": "tool", "deploy-api": "deploy API"}[comp]
            if comp == "agent":
                step = {"model proposed action": "model", "policy decision": "policy", "waiting for approval": "approval", "approval received": "approval",
                        "executing": "tool", "data access denied": "context"}.get(r["msg"], "complete" if r.get("outcome") else "trigger")
            fields = {k: v for k, v in r.items() if k not in ("ts", "level", "component", "service.version", "msg", "trace_id", "span_id")}
            prof = r.get("profile")
            tone = "bad" if r["level"] in ("WARN", "ERROR") else ""
            tag = " · *governed runtime only (not in L0/L1)*" if prof == "governed" else (" · *what a runtime trusting the tool concludes*" if prof == "baseline" else "")
            add(r["ts"], step, f"log `{comp}` {r['level']} **{r['msg']}** · {_s(fields, 140)}{tag}", tone, f"logs/{comp}.log[{i}]", "L0/L1")
    for i, q in enumerate(json.loads((sd / "world" / "external-transactions.json").read_text())):
        if q["service"] != "payment-service" or q["method"] != "POST":
            continue
        tone = "ok" if q["outcome"] == "COMMITTED" else ("warn" if q["outcome"] in ("IDEMPOTENT_REPLAY",) else "bad")
        add(q["received_at"], "deploy API", f"**system of record** request `{q['request_id']}` · key `{q['idempotency_key'] or 'none'}` → {q['outcome']} · txn `{q['txn_id']}` · "
            f"response {'delivered' if q['response_delivered'] else 'NOT delivered'}" + (f" · fault `{q['fault']}` (SIMULATED)" if q.get("fault") else ""),
            tone, f"world/external-transactions.json[{i}]", "truth")
    ev.sort(key=lambda e: (e["ts"], e["o"]))
    return ev


def spans(sd: Path) -> list[dict]:
    _, tid = target(sd)
    return [s for p in sorted((sd / "telemetry").glob("spans-*.jsonl")) for s in jl(p) if s["trace_id"] == tid]


def lineage(run: dict, sd: Path) -> list[list]:
    rel = lambda p: str(p.relative_to(run["dir"]))  # noqa: E731
    rows = [["Input · preregistration", "observability_governance_poc/experiments/preregistration.toml", "1", "scenarios, injected faults, expectations, predictions (digest frozen in manifest.json)"],
            ["Input · world, control plane, policies", "observability_governance_poc/config/*.toml", str(len(list((POC / "config").glob("*.toml"))) + 2),
             "the incident, agent configs and prompt templates, policies v41/v42, principals, data scopes, retention"],
            ["Scenario spec", rel(sd / "spec.json"), "1", "the preregistered case resolved against the defaults"]]
    for comp in ("agent", "model-gateway", "policy-decisions", "approval-service", "tool-gateway", "deploy-api"):
        p = sd / "logs" / f"{comp}.log"
        rows.append([f"L0/L1 · {comp}.log", rel(p), str(len(jl(p))), "the component's own log; trace ids removed for L0"])
    sp = sorted((sd / "telemetry").glob("spans-*.jsonl"))
    rows.append(["L1 · spans", rel(sd / "telemetry"), str(sum(len(jl(p)) for p in sp)), f"OpenTelemetry spans from {len(sp)} processes"])
    rows.append(["L2 · evidence", rel(sd / "evidence" / "audit-events.jsonl"), str(len(jl(sd / "evidence" / "audit-events.jsonl"))), "hash-chained events of both executions"])
    rows.append(["L2 · witness", rel(sd / "witness" / "anchors.jsonl"), str(len(jl(sd / "witness" / "anchors.jsonl"))), "chain heads anchored at each completion"])
    rows.append(["Truth · deployment API", rel(sd / "world" / "external-transactions.json"), str(len(json.loads((sd / "world" / "external-transactions.json").read_text()))),
                 "every request the API received, with its outcome (ground truth)"])
    rows.append(["Truth · world", rel(sd / "world" / "after.json"), "1", "deployments and every revision created"])
    rows.append(["Model tape", rel(sd / "tape"), str(sum(len(jl(p)) for p in (sd / "tape").glob("*/model_tape.jsonl"))), "recorded model answers, replayable"])
    rows.append(["Processes", rel(sd / "procs"), str(len(list((sd / "procs").glob("*-*.log")))), "one log per agent process; supervisor.json has exit codes"])
    rows += [["Ground truth", rel(sd / "truth.json"), "13", "answers from the systems of record"],
             ["Reconstruction", rel(sd / "reconstruction.json"), "39", "each layer's 13 answers, verdicts, sources and joins"],
             ["Scenario result", rel(sd / "result.json"), "1", "outcome, changes, attempts, processes, scores"],
             ["Run aggregate", "facts.json · reports/", "—", "every published number"]]
    return rows
