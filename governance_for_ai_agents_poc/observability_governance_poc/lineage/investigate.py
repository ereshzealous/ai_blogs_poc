"""Three investigators, six hours later: answer Q1–Q13 about INC-4471's rollback from one observation layer each.

    L0  application logs     logs/*.log with trace_id/span_id removed, plus the approval service's database tables.
                             Only lines a runtime without lineage features would also write (profile common or baseline).
    L1  logs + traces        the same log lines with their trace_id/span_id, plus every OpenTelemetry span of every process.
    L2  execution lineage    the evidence events and the witness file; joined by key to the deployment API's transaction
                             lookup when it needs the system of record.

Rules every investigator follows (written before the recorded run, applied mechanically):
  * start from the incident id, the only thing the question gives ("the rollback on INC-4471");
  * a join on an identifier both sides recorded (incident id, request id, trace id, execution id, idempotency key) is a
    key join; a join on time proximity or matching content is a heuristic join, and is counted separately;
  * if a question has more than one candidate answer after the joins, the answer is AMBIGUOUS, never a guess;
  * if the layer does not record something, the answer for that part is None (the verdict is then INCOMPLETE or
    UNANSWERABLE), never inferred from other fields.

The investigators are generous to L0 on purpose: the baseline logs carry the incident id wherever the component knows it and
the tool gateway propagates X-Request-Id to the deployment API, as well-run services do.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .common import jl, load
from .evidence import verify

WORLD = load("world.toml")
INC = WORLD["incident"]["id"]


class Trail:
    def __init__(self) -> None:
        self.sources: set[str] = set()
        self.joins: list[dict] = []

    def use(self, src: str) -> None:
        self.sources.add(src)

    def join(self, a: str, b: str, on: str, kind: str) -> None:
        j = {"from": a, "to": b, "on": on, "kind": kind}
        if j not in self.joins:
            self.joins.append(j)

    def summary(self) -> dict:
        return {"sources": sorted(self.sources), "joins": self.joins, "key_joins": sum(1 for j in self.joins if j["kind"] == "key"),
                "heuristic_joins": sum(1 for j in self.joins if j["kind"] == "heuristic")}


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def logs(sdir: Path, component: str, with_trace: bool) -> list[dict]:
    out = []
    for r in jl(sdir / "logs" / f"{component}.log"):
        if r.get("profile") == "governed":
            continue
        if not with_trace:
            r = {k: v for k, v in r.items() if k not in ("trace_id", "span_id")}
        out.append(r)
    return out


def approval_tables(sdir: Path) -> tuple[list[dict], list[dict]]:
    db = sqlite3.connect(sdir / "state" / "approvals.db")
    rq = [dict(zip(("approval_id", "incident", "action_text", "state"), r)) for r in db.execute("SELECT approval_id, incident, action_text, state FROM requests")]
    dc = [dict(zip(("approval_id", "approver", "decision"), r)) for r in db.execute("SELECT approval_id, approver, decision FROM decisions ORDER BY approver")]
    db.close()
    return rq, dc


def one(values: list):
    vals = [v for i, v in enumerate(values) if v not in values[:i]]
    if not vals:
        return None
    return vals[0] if len(vals) == 1 else "AMBIGUOUS"


# ---- L0 and L1 ------------------------------------------------------------------------------------------------------------
def from_logs(sdir: Path, traced: bool) -> dict:
    T = Trail()
    L = {c: logs(sdir, c, traced) for c in ("agent", "model-gateway", "policy-decisions", "tool-gateway", "deploy-api", "approval-service")}
    spans = []
    if traced:
        for p in sorted((sdir / "telemetry").glob("spans-*.jsonl")):
            spans += jl(p)
    A = [r for r in L["agent"] if r.get("incident") == INC]
    T.use("agent.log")
    tids = {r["trace_id"] for r in A if r.get("trace_id")} if traced else set()
    ans: dict = {}

    start = [r for r in A if r["msg"] == "execution started"]
    ans["Q1"] = one([{"source": r["invoked_by"], "alert_id": r["alert_id"]} for r in start])
    ans["Q2"] = one([{"invoker": r["invoked_by"], "on_behalf_of": None} for r in start])
    ans["Q3"] = one([dict(zip(("agent", "version"), r["service.version"].split(" "))) for r in start])

    # Q4: the model.  L0: the agent's "model proposed action" line names the model; the model gateway's line (tokens, latency)
    # has no incident id, so it is matched by time.  L1: the chat span in the execution's trace.
    prop = [r for r in A if r["msg"] == "model proposed action"]
    if traced:
        chats = [s for s in spans if s["trace_id"] in tids and s["attributes"].get("gen_ai.operation.name") == "chat"]
        T.use("spans")
        T.join("agent.log", "spans", "trace_id", "key")
        ans["Q4"] = one([{"model": s["attributes"].get("gen_ai.response.model") or s["attributes"].get("gen_ai.request.model"),
                          "model_digest": None, "prompt_template": None, "agent_config": None} for s in chats])
    else:
        mg = []
        for p in prop:
            near = [m for m in L["model-gateway"] if 0 <= ts(p["ts"]) - ts(m["ts"]) <= 1.0]
            mg += near
        if mg:
            T.use("model-gateway.log")
            T.join("agent.log", "model-gateway.log", "timestamp within 1s", "heuristic")
        ans["Q4"] = one([{"model": p["model"], "model_digest": None, "prompt_template": None, "agent_config": None} for p in prop])

    # Q5/Q6: the policy decision log carries the incident id in its input (L0) and the trace id (L1).
    if traced:
        pol = [r for r in L["policy-decisions"] if r.get("trace_id") in tids]
        T.join("agent.log", "policy-decisions.log", "trace_id", "key")
    else:
        pol = [r for r in L["policy-decisions"] if r.get("input", {}).get("incident") == INC]
        T.join("agent.log", "policy-decisions.log", "incident id in the decision input", "key")
    T.use("policy-decisions.log")
    ans["Q5"] = one([{"policy": r["policy"], "version": int(r["bundle_revision"].lstrip("v"))} for r in pol])
    ans["Q6"] = one([r["result"] == "ALLOW_WITH_APPROVAL" for r in pol])

    # Q7: the approval service's tables, by incident id (neither the table nor the service log carries a trace id for decisions).
    rq, dc = approval_tables(sdir)
    T.use("approvals.db")
    T.join("agent.log", "approvals.db", "incident id", "key")
    mine = [r["approval_id"] for r in rq if r["incident"] == INC]
    decs = sorted([[d["approver"], d["decision"]] for d in dc if d["approval_id"] in mine])
    ans["Q7"] = decs or None

    # Q8–Q11: the tool gateway's calls for this incident, then the deployment API's lines for those request ids.
    if traced:
        calls = [r for r in L["tool-gateway"] if r.get("trace_id") in tids and r["msg"] == "calling deploy-api"]
        T.join("agent.log", "tool-gateway.log", "trace_id", "key")
    else:
        calls = [r for r in L["tool-gateway"] if r.get("incident") == INC and r["msg"] == "calling deploy-api"]
        T.join("agent.log", "tool-gateway.log", "incident id", "key")
    T.use("tool-gateway.log")
    rids = {r["request_id"] for r in calls}
    if traced:
        dl = [r for r in L["deploy-api"] if r.get("trace_id") in tids]
        T.join("tool-gateway.log", "deploy-api.log", "trace_id", "key")
    else:
        dl = [r for r in L["deploy-api"] if r.get("request_id") in rids]
        T.join("tool-gateway.log", "deploy-api.log", "X-Request-Id", "key")
    T.use("deploy-api.log")
    reached = [r for r in dl if r["msg"] == "request" and r["method"] == "POST"]
    ans["Q8"] = one([{"capability": c["capability"], "service": c["service"], "to_version": c["to_version"]} for c in calls
                     if c["request_id"] in {r["request_id"] for r in reached}])
    ans["Q9"] = len({r["request_id"] for r in reached})
    created = [r for r in dl if r["msg"] == "rollout created"]
    ans["Q10"] = len(created) > 0
    ans["Q11"] = len(created)

    # Q12: the last outcome the agent recorded for the incident.
    outs = [r for r in A if r.get("outcome")]
    ans["Q12"] = (outs[-1]["outcome"] == "MITIGATED") if outs else None
    ans["Q13"] = None          # no integrity mechanism: nothing to verify against
    return {"answers": ans, **T.summary()}


# ---- L2 -------------------------------------------------------------------------------------------------------------------
def from_lineage(sdir: Path) -> dict:
    T = Trail()
    rows = [dict(r, payload=json.loads(r["payload_json"])) for r in jl(sdir / "evidence" / "audit-events.jsonl")]
    T.use("evidence")
    starts = [r for r in rows if r["event_type"] == "execution.started" and r["payload"]["incident"] == INC]
    ans: dict = {}
    if len({r["execution_id"] for r in starts}) != 1:
        return {"answers": {q: "AMBIGUOUS" for q in (f"Q{i}" for i in range(1, 14))}, **T.summary()}
    xid = starts[0]["execution_id"]
    E = [r for r in rows if r["execution_id"] == xid]
    T.join("incident id", "evidence", "execution_id", "key")

    def ev(t: str) -> list[dict]:
        return [r["payload"] for r in E if r["event_type"] == t]

    s = starts[0]["payload"]
    ans["Q1"] = {"source": s["trigger"]["source"], "alert_id": s["trigger"]["alert_id"]}
    ans["Q2"] = {"invoker": s["invoker"], "on_behalf_of": s["on_behalf_of"]}
    ans["Q3"] = {"agent": starts[0]["agent_id"], "version": s["agent_version"]}
    ans["Q4"] = one([{"model": m["model"], "model_digest": m["model_digest"], "prompt_template": m["prompt_template"], "agent_config": m["agent_config"]}
                     for m in ev("model.invoked")])
    ans["Q5"] = one([{"policy": p["policy_id"], "version": p["policy_version"]} for p in ev("policy.evaluated")])
    ans["Q6"] = bool(ev("approval.requested"))
    ans["Q7"] = sorted([[d["approver"], d["decision"]] for d in ev("approval.decided")]) or None
    started = ev("attempt.started")
    auth = ev("action.authorized")
    ans["Q8"] = one([{"capability": a["capability"], "service": a["target"], "to_version": a["arguments"]["to_version"]} for a in auth]) if started else None
    ans["Q9"] = len({r["attempt_id"] for r in E if r["event_type"] == "attempt.started"})
    ver = ev("effect.verified")
    if ver:
        ans["Q10"] = ver[-1]["revision_delta"] > 0
        ans["Q11"] = ver[-1]["revision_delta"]
        if ver[-1]["transactions_for_key"]:
            T.use("deploy-api transaction lookup")
            T.join("evidence", "deploy-api transaction lookup", "idempotency key", "key")
    else:
        ans["Q10"], ans["Q11"] = (False, 0) if not started else (None, None)
    done = ev("execution.completed")
    ans["Q12"] = done[-1]["mitigated"] if done else None
    anchors = jl(sdir / "witness" / "anchors.jsonl")
    T.use("witness anchors")
    v = verify([{k: r[k] for k in r if k != "payload"} for r in rows], anchors)
    ans["Q13"] = v["intact"]
    return {"answers": ans, **T.summary()}


# ---- scoring --------------------------------------------------------------------------------------------------------------
def verdict(answer, truth) -> str:
    if answer == "AMBIGUOUS":
        return "AMBIGUOUS"
    if isinstance(truth, dict) and isinstance(answer, dict):
        known = {k: v for k, v in answer.items() if v is not None}
        if any(truth.get(k) != v for k, v in known.items()):
            return "WRONG"
        return "CORRECT" if len(known) == len(truth) else ("INCOMPLETE" if known else "UNANSWERABLE")
    if answer is None:
        return "CORRECT" if truth is None else "UNANSWERABLE"
    return "CORRECT" if answer == truth else "WRONG"


def investigate_all(sdir: Path, spec: dict, t: dict) -> dict:
    out = {}
    for layer, fn in (("L0", lambda: from_logs(sdir, False)), ("L1", lambda: from_logs(sdir, True)), ("L2", lambda: from_lineage(sdir))):
        r = fn()
        r["answers"] = {q: {"answer": a, "truth": t[q]["value"], "verdict": verdict(a, t[q]["value"])} for q, a in sorted(r["answers"].items(), key=lambda kv: int(kv[0][1:]))}
        out[layer] = r
    return out
