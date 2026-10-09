"""The agent runtime: one execution of incident-agent-prod, as a durable workflow, in its own process.

    python -m lineage.runtime <scenario-dir> <target|background>     (started by the harness, restarted after a SIGKILL)

Steps, each checkpointed in state/workflow.db before the next begins:

    trigger -> context -> model -> policy -> approval -> tool -> verify -> complete

The same execution writes three things, which is the point of the experiment:

  application logs   logs/agent.log, model-gateway.log, policy-decisions.log, tool-gateway.log (plus approval-service.log and
                     deploy-api.log written by those services): what each component would log anyway, with its own ids
  telemetry          OpenTelemetry spans and metrics, standard semantic conventions, context propagated over HTTP
  evidence           governance events in the hash-chained evidence store, keyed by execution_id / action_id / attempt_id

A restarted process reads its checkpoint, records workflow.resumed, continues the same trace from the saved context, and
resolves any attempt that was in flight when it died by asking the deployment API what happened under that idempotency key,
instead of sending the action again.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from opentelemetry import trace
from opentelemetry.trace import Link, SpanKind

from . import approval as appr
from . import crash, model, policy
from . import semconv as sc
from .common import AppLog, action_id, execution_id, load, now_iso, sha
from .evidence import EvidenceStore
from .gateway import TOOL_IDENTITY, Gateway
from .telemetry import current_ids, dump_metrics, remote_parent, setup

WORLD = load("world.toml")
CP = load("control_plane.toml")
DATA = load("data.toml")
STEPS = ["trigger", "context", "model", "policy", "approval", "tool", "verify", "complete"]
SIM_TIME = {"target": "14:09 UTC", "background": "14:10 UTC"}      # fixed, so the prompt is byte-identical in a replay


class Runtime:
    def __init__(self, sdir: Path, role: str) -> None:
        self.sdir, self.role = sdir, role
        self.spec = json.loads((sdir / "spec.json").read_text())
        self.x = self.spec["executions"][role]
        inc = WORLD["incident"] if role == "target" else WORLD["background"]
        self.inc = {**inc, "severity": self.x["severity"]}
        self.incident = inc["id"]
        self.agent_id = CP["agent"]["id"]
        self.exec_id = execution_id(self.spec["scenario"], self.incident)
        self.workflow_id = f"wf-remediate-{self.incident.lower()}"
        (sdir / "state").mkdir(exist_ok=True)
        self.wf = sqlite3.connect(sdir / "state" / "workflow.db", timeout=30, isolation_level=None)
        self.wf.executescript("""
        CREATE TABLE IF NOT EXISTS executions (execution_id TEXT PRIMARY KEY, role TEXT, trace_id TEXT, root_span_id TEXT, pid INTEGER, started_at TEXT);
        CREATE TABLE IF NOT EXISTS steps (execution_id TEXT, step TEXT, status TEXT, data TEXT, updated_at TEXT, PRIMARY KEY (execution_id, step));
        """)
        self.store = EvidenceStore(sdir / "state" / "evidence.db", sdir / "witness" / "anchors.jsonl")
        self.log = AppLog(sdir, "agent", f"{self.agent_id} {CP['agent']['version']}")
        self.mlog = AppLog(sdir, "model-gateway", "model-gateway 1.6.0")
        self.plog = AppLog(sdir, "policy-decisions", "policy-engine 0.9.4")
        self.tlog = AppLog(sdir, "tool-gateway", "tool-gateway 3.2.0")
        self.approvals = appr.ApprovalService(sdir)
        port = int((sdir / "deploy" / "port").read_text())
        run = self.spec["run"]
        self.gw = Gateway(self, port, self.x["idempotency"] == "on", run["client_timeout_s"], run["max_attempts"])
        self.pins = {"policy": self.x["policy"], "agent_config": self.x["agent_config"], "tool_catalog": CP["published"]["tool_catalog"]}
        self.cfg = model.config(self.x["agent_config"])
        self.tracer, self.meter = setup(sdir, f"agent-{role}", self.agent_id, CP["agent"]["version"], seed_key=f"{self.spec['scenario']}/{role}/{os.environ.get('LINEAGE_INCARNATION', '1')}")
        self.m_exec = self.meter.create_counter("lineage.executions", description="agent executions by outcome")
        self.m_attempts = self.meter.create_counter("lineage.tool.attempts", description="tool attempts by capability and result")
        self.m_policy = self.meter.create_counter("lineage.policy.decisions", description="policy decisions by decision and policy version")
        self.m_approval = self.meter.create_counter("lineage.approvals", description="approval decisions")
        self.m_unknown = self.meter.create_counter("lineage.tool.unknown_outcomes", description="attempts whose outcome was not known when they ended")
        self.m_unverified = self.meter.create_counter("lineage.effects.unverified", description="actions whose effect was not observed")
        self.m_tokens = self.meter.create_histogram(sc.M_TOKEN_USAGE, unit="{token}", description="tokens per model call")
        self.m_dur = self.meter.create_histogram(sc.M_OP_DURATION, unit="s", description="model call duration")

    # ---- recording -------------------------------------------------------------------------------------------------------
    def evidence(self, event_type: str, payload: dict, action_id: str | None = None, attempt_id: str | None = None) -> dict:
        tid, sid = current_ids()
        return self.store.append(event_type, execution_id=self.exec_id, trace_id=tid, span_id=sid, workflow_id=self.workflow_id,
                                 principal=f"{self.agent_id} for {self.inc['on_behalf_of']}", agent_id=self.agent_id, payload=payload,
                                 action_id=action_id, attempt_id=attempt_id)

    def metric_attempt(self, capability: str, result: str) -> None:
        self.m_attempts.add(1, {"capability": capability, "result": result})
        if result in ("TIMEOUT", "CONNECTION_ERROR"):
            self.m_unknown.add(1, {"capability": capability})

    def step_data(self, step: str) -> tuple[str | None, dict]:
        row = self.wf.execute("SELECT status, data FROM steps WHERE execution_id=? AND step=?", (self.exec_id, step)).fetchone()
        return (row[0], json.loads(row[1] or "{}")) if row else (None, {})

    def save(self, step: str, status: str, data: dict) -> None:
        self.wf.execute("INSERT OR REPLACE INTO steps VALUES (?,?,?,?,?)", (self.exec_id, step, status, json.dumps(data), now_iso()))

    # ---- the execution ---------------------------------------------------------------------------------------------------
    def run(self) -> None:
        row = self.wf.execute("SELECT trace_id, root_span_id, pid FROM executions WHERE execution_id=?", (self.exec_id,)).fetchone()
        resumed = row is not None
        attrs = {sc.OP: "invoke_agent", sc.AGENT_NAME: self.agent_id, sc.AGENT_ID: self.agent_id, sc.AGENT_VERSION: CP["agent"]["version"]}
        if resumed:
            ctx, links = remote_parent(row[0], row[1]), [Link(trace.SpanContext(int(row[0], 16), int(row[1], 16), True), {"lineage.link": "resumed_from"})]
        else:
            ctx, links = None, []
        with self.tracer.start_as_current_span(f"invoke_agent {self.agent_id}", context=ctx, links=links, kind=SpanKind.INTERNAL, attributes=attrs) as root:
            tid, sid = current_ids()
            if not resumed:
                self.wf.execute("INSERT INTO executions VALUES (?,?,?,?,?,?)", (self.exec_id, self.role, tid, sid, os.getpid(), now_iso()))
            else:
                done = [s for s in STEPS if self.step_data(s)[0] == "DONE"]
                nxt = next((s for s in STEPS if s not in done), "complete")
                inflight = [f"{a}.a{n}" for a, n in self.wf.execute("SELECT action_id, n FROM attempts WHERE status='IN_FLIGHT'").fetchall()] \
                    if self.wf.execute("SELECT name FROM sqlite_master WHERE name='attempts'").fetchone() else []
                self.log("WARN", "runtime restarted, resuming", incident=self.incident, session=self.session(), from_step=nxt)
                self.evidence("workflow.resumed", {"from_step": nxt, "previous_pid": row[2], "restored_trace": row[0], "in_flight": inflight})
            state: dict = {}
            for step in STEPS:
                status, data = self.step_data(step)
                if status == "DONE":
                    state[step] = data
                    if data.get("halt"):
                        break
                    continue
                with self.tracer.start_as_current_span(f"step {step}", attributes={"lineage.step": step}):
                    data = getattr(self, f"s_{step}")(state, data)
                self.save(step, "DONE", data)
                state[step] = data
                if data.get("halt"):
                    break
        dump_metrics()

    def session(self) -> str:
        return f"sess-{os.getpid()}"          # the agent framework's own session id: one per process, as frameworks do

    def finish(self, outcome: str, reason: str, mitigated: bool, attempts: int = 0, mutations: int | None = None, profile: str = "common") -> dict:
        self.evidence("execution.completed", {"outcome": outcome, "reason": reason, "mitigated": mitigated, "attempts": attempts,
                                              "mutations_observed": mutations})
        self.store.anchor(self.exec_id)
        self.m_exec.add(1, {"outcome": outcome})
        self.log("INFO" if mitigated else "WARN", "incident mitigated" if mitigated else "escalating to on-call", incident=self.incident,
                 session=self.session(), outcome=outcome, reason=reason, profile=profile)
        return {"halt": True, "outcome": outcome}

    # ---- steps -----------------------------------------------------------------------------------------------------------
    def s_trigger(self, st, d) -> dict:
        trig = {"type": "monitor_alert", "source": self.inc["source"], "alert_id": self.inc["alert_id"]}
        self.log("INFO", "execution started", incident=self.incident, session=self.session(), invoked_by=self.inc["source"],
                 alert_id=self.inc["alert_id"], severity=self.inc["severity"], service=self.inc["service"])
        pins = {**self.pins, "prompt_template": self.cfg["prompt_template"], "model": self.cfg["model"],
                "policy_digest": policy.document(self.pins["policy"])[1], "agent_config_digest": self.cfg["config_digest"],
                "prompt_template_digest": self.cfg["prompt_template_digest"]}
        self.evidence("execution.started", {"trigger": trig, "invoker": self.inc["source"], "on_behalf_of": self.inc["on_behalf_of"],
                                            "incident": self.incident, "severity": self.inc["severity"], "service": self.inc["service"],
                                            "agent_version": CP["agent"]["version"], "workload": CP["agent"]["workload"], "pins": pins,
                                            "background": self.role == "background"})
        return {"trigger": trig}

    def s_context(self, st, d) -> dict:
        wanted = [f"runbooks.{self.inc['service']}", "deployments.history"]
        if self.role == "target" and self.x.get("context_request"):
            wanted.append(self.x["context_request"])
        scopes = DATA["agent_scopes"][self.agent_id]
        allowed = []
        for ds in wanted:
            meta = DATA["datasets"][ds]
            ok = meta["classification"] in scopes
            self.evidence("context.accessed", {"dataset": ds, "classification": meta["classification"], "decision": "ALLOW" if ok else "DENY",
                                               "reason": "within the agent's data scopes" if ok else f"{meta['classification']} is outside the agent's scopes {scopes}",
                                               "content_digest": "sha256:" + sha(meta["content"]) if ok else None, "requested_by": "context-assembler"})
            if ok:
                allowed.append(ds)
            else:
                self.log("WARN", "data access denied", incident=self.incident, dataset=ds, session=self.session())
        return {"datasets": allowed}

    def context_text(self, datasets: list[str]) -> str:
        s = self.inc["signals"]
        dep = next(x for x in WORLD["deployments"] if x["service"] == self.inc["service"])
        lines = [f"Time: {SIM_TIME[self.role]}.",
                 f"Incident {self.incident} ({self.inc['severity']}, open): {self.inc['service']} alert from {self.inc['source']}.",
                 f"Production deployment of {dep['service']}: running {dep['version']}; release history {', '.join(dep['history'])}.",
                 f"Error rate now: {s['error_rate']} (before the release: {s['error_rate_before']}).",
                 f"Logs: {s['log_excerpt']}", f"Staging: {s['staging']}", f"Previous good release: {s['previous_good']}"]
        for ds in datasets:
            if ds.startswith("runbooks."):
                lines.append(f"Runbook: {DATA['datasets'][ds]['content']}")
        if self.role == "target" and self.x.get("annotation"):
            lines.append(f"Alert annotation: {self.x['annotation']}")
        return "\n".join(lines)

    def s_model(self, st, d) -> dict:
        text = self.context_text(st["context"]["datasets"])
        agent = {"id": self.agent_id}
        out = model.propose(self.cfg, text, caller=f"{self.role}", agent=agent)
        p, m = out["proposal"], out["meta"]
        self.m_tokens.record(m["input_tokens"], {sc.OP: "chat", sc.REQ_MODEL: self.cfg["model"], sc.TOKEN_TYPE: "input"})
        self.m_tokens.record(m["output_tokens"], {sc.OP: "chat", sc.REQ_MODEL: self.cfg["model"], sc.TOKEN_TYPE: "output"})
        self.m_dur.record(m["latency_ms"] / 1000, {sc.OP: "chat", sc.REQ_MODEL: self.cfg["model"]})
        digest = model.model_digest(self.cfg["model"], caller=f"{self.role}-tags")
        self.mlog("INFO", "completion", request_id="mgw-" + m["input_digest"][7:19], model=m["model"], input_tokens=m["input_tokens"],
                  output_tokens=m["output_tokens"], duration_ms=m["latency_ms"], status="ok")
        self.evidence("model.invoked", {"provider": m["provider"], "model": m["model"], "model_digest": digest,
                                        "prompt_template": self.cfg["prompt_template"], "prompt_template_digest": self.cfg["prompt_template_digest"],
                                        "agent_config": self.cfg["ref"], "options": m["options"], "input_digest": m["input_digest"],
                                        "input_tokens": m["input_tokens"], "output_tokens": m["output_tokens"], "latency_ms": m["latency_ms"],
                                        "finish_reason": m["finish_reason"], "replayed": m["replayed"],
                                        "structured_output": {k: p[k] for k in ("capability", "service", "environment", "to_version")}})
        source = "model"
        if self.role == "target" and self.x.get("planner_override"):
            o = self.x["planner_override"]
            p = {"capability": o["capability"], "service": o["service"], "environment": o["environment"], "to_version": "",
                 "rationale": o["reason"], "replicas": o.get("replicas")}
            source = "planner override (SIMULATED compromised plan)"
        act = {k: p.get(k, "") for k in ("capability", "service", "environment", "to_version")}
        self.log("INFO", "model proposed action", incident=self.incident, session=self.session(), model=m["model"], capability=act["capability"],
                 service=act["service"], to_version=act["to_version"], rationale=p["rationale"][:200])
        self.evidence("decision.proposed", {"capability": act["capability"], "target": act["service"],
                                            "arguments": {"environment": act["environment"], "to_version": act["to_version"], **({"replicas": p["replicas"]} if p.get("replicas") is not None else {})},
                                            "rationale_summary": p["rationale"][:280], "action_digest": "sha256:" + sha(act), "source": source})
        if act["capability"] == "noAction":
            return {**self.finish("NO_ACTION", "the model proposed no action", False), "action": act}
        return {"action": act, "rationale": p["rationale"][:280]}

    def s_policy(self, st, d) -> dict:
        act = st["model"]["action"]
        pe = policy.evaluate(self.x["policy"], act, {"agent": self.agent_id, "severity": self.inc["severity"]}, self.exec_id)
        pe_digest = appr.action_digest(act, self.incident, pe["policy_evaluation_id"])
        self.plog("INFO", "decision", decision_id="dec-" + pe["policy_evaluation_id"][3:], policy=pe["policy_id"],
                  bundle_revision=f"v{pe['policy_version']}", input={"agent": self.agent_id, "incident": self.incident, **pe["attributes"]},
                  result=pe["decision"], obligations=pe["obligations"])
        self.evidence("policy.evaluated", {**pe, "action_digest": pe_digest})
        self.m_policy.add(1, {"decision": pe["decision"], "policy_version": str(pe["policy_version"])})
        self.log("INFO", "policy decision", incident=self.incident, session=self.session(), decision=pe["decision"])
        if pe["decision"] == "DENY":
            if self.role == "target" and self.x.get("direct_gateway_call"):
                # the compromised plan goes around the workflow and calls the gateway itself (SIMULATED)
                reason = self.gw.authorize(act, self.pins["tool_catalog"], None, False, "direct")
                self.gw.deny(act, self.pins["tool_catalog"], reason or "refused", None, "direct call from the runtime, no policy evaluation")
            return {**self.finish("DENIED", f"policy {pe['policy_id']}@{pe['policy_version']} denied {act['capability']}", False), "pe": pe}
        return {"pe": pe, "digest": pe_digest}

    def s_approval(self, st, d) -> dict:
        pe, digest, act = st["policy"]["pe"], st["policy"]["digest"], st["model"]["action"]
        if pe["decision"] != "ALLOW_WITH_APPROVAL":
            return {"required": False, "approval_ids": [], "ok": True}
        if not d.get("approval_id"):
            req = self.approvals.request(self.exec_id, self.incident, act, digest, pe["obligations"], pe["policy_evaluation_id"], self.agent_id)
            d = {"approval_id": req["approval_id"]}
            self.save("approval", "WAITING", d)
            self.evidence("approval.requested", {"approval_id": req["approval_id"], "action_digest": digest, "scope": req["action_text"],
                                                 "eligible_roles": pe["obligations"]["approver_roles"], "quorum": pe["obligations"]["quorum"],
                                                 "expires_at": f"+{pe['obligations']['expires_in_s']}s", "policy_evaluation_id": pe["policy_evaluation_id"]})
            self.log("INFO", "waiting for approval", incident=self.incident, session=self.session(), approval_id=req["approval_id"])
        aid = d["approval_id"]
        crash.hit("awaiting_approval")
        deadline = time.time() + 60
        while self.approvals.state(aid) == "PENDING" and time.time() < deadline:
            time.sleep(0.1)
        state = self.approvals.state(aid)
        decs = self.approvals.decisions(aid)
        ok_all = True
        for dec in decs:
            chk = appr.check(dec, digest)
            ok_all &= chk["signature_valid"] and chk["digest_match"]
            self.evidence("approval.decided", {"approval_id": aid, "approver": dec["approver"], "role": dec["role"], "decision": dec["decision"],
                                               "reason": dec["reason"], "decided_at": dec["decided_at"], **chk})
            self.m_approval.add(1, {"decision": dec["decision"]})
        self.log("INFO", "approval received", incident=self.incident, session=self.session(), approval_id=aid, state=state,
                 approvers=[x["approver"] for x in decs])
        if state != "APPROVED" or not ok_all:
            return {**self.finish("REJECTED" if state == "REJECTED" else "APPROVAL_INVALID", f"approval {aid} {state.lower()}", False),
                    "approval_id": aid, "required": True}
        return {"required": True, "approval_ids": [aid], "ok": True, "approval_id": aid}

    def s_tool(self, st, d) -> dict:
        act, pe = st["model"]["action"], st["policy"]["pe"]
        digest = st["policy"]["digest"]
        aid = action_id(self.exec_id, "tool", digest)
        if not d.get("before"):
            before = self.gw.get(f"/v1/deployments/{act['service']}")
            d = {"before": before, "action_id": aid}
            self.save("tool", "RUNNING", d)
            refusal = self.gw.authorize(act, self.pins["tool_catalog"], pe, st["approval"].get("ok", False), "workflow")
            if refusal:
                self.gw.deny(act, self.pins["tool_catalog"], refusal, pe["policy_evaluation_id"], "workflow")
                return {**self.finish("DENIED", refusal, False), **d}
            self.evidence("action.authorized", {"capability": act["capability"], "target": act["service"],
                                                "arguments": {"environment": act["environment"], "to_version": act["to_version"]},
                                                "catalog": self.pins["tool_catalog"], "tool_identity": TOOL_IDENTITY, "credential_audience": "deploy-api",
                                                "idempotency_key": aid if self.gw.idempotency else None, "policy_evaluation_id": pe["policy_evaluation_id"],
                                                "approval_ids": st["approval"].get("approval_ids", []), "action_digest": digest}, action_id=aid)
            self.log("INFO", "executing", incident=self.incident, session=self.session(), capability=act["capability"], service=act["service"],
                     to_version=act["to_version"])
        # an attempt left in flight by a killed process: find out what happened before doing anything again
        for n, rid in self.gw.in_flight(aid):
            txs = self.gw.get(f"/v1/transactions?idempotency_key={aid}")["transactions"] if self.gw.idempotency else []
            done = [t for t in txs if t["state"] == "DONE"]
            res = "COMMITTED" if done else "NOT_FOUND"
            self.wf.execute("UPDATE attempts SET status=? WHERE action_id=? AND n=?", (f"RECONCILED_{res}", aid, n))
            self.evidence("attempt.reconciled", {"attempt": n, "result": res, "external_transaction_id": done[0]["txn_id"] if done else None,
                                                 "method": "GET /v1/transactions?idempotency_key"}, action_id=aid, attempt_id=f"{aid}.a{n}")
            self.tlog("INFO", "in-flight call reconciled", incident=self.incident, request_id=rid, result=res)
            if done:
                d["result"] = {"result": "COMMITTED", "txn": done[0]["txn_id"], "reconciled": True}
        if not d.get("result"):
            d["result"] = self.gw.invoke(act, aid)
        # What a runtime that trusts the tool response concludes, and logs.  The governed runtime reads the world back in the
        # next step; L0 and L1 see this line, L2 does not use logs at all (see investigate.py).
        ok = d["result"]["result"] in ("COMMITTED", "REPLAYED")
        self.log("INFO" if ok else "WARN", "tool call succeeded, incident mitigated" if ok else "tool call failed, escalating to on-call",
                 incident=self.incident, session=self.session(), outcome="MITIGATED" if ok else "FAILED", profile="baseline")
        if self.role == "target" and self.x.get("redeliver_step") == "tool.invoke" and not d.get("redelivery"):
            # at-least-once delivery: the step's completion was not acknowledged, so the queue delivers it again (SIMULATED)
            self.log("WARN", "step delivered again by the queue", incident=self.incident, session=self.session(), step="tool")
            d["redelivery"] = self.gw.invoke(act, aid)
        return d

    def s_verify(self, st, d) -> dict:
        act, tool = st["model"]["action"], st["tool"]
        before, aid = tool["before"], tool["action_id"]
        after = self.gw.get(f"/v1/deployments/{act['service']}")
        health = self.gw.get(f"/v1/deployments/{act['service']}/health")
        txs = self.gw.get(f"/v1/transactions?idempotency_key={aid}")["transactions"] if self.gw.idempotency else []
        delta = after["revision"] - before["revision"]
        verified = after["version"] == act["to_version"] and delta >= 1 and health["healthy"]
        self.evidence("effect.verified", {"verified": verified, "expected": {"version": act["to_version"], "revision_delta": 1},
                                          "observed_before": {k: before[k] for k in ("version", "revision")},
                                          "observed_after": {k: after[k] for k in ("version", "revision")}, "revision_delta": delta,
                                          "transactions_for_key": [t["txn_id"] for t in txs], "source": "deploy-api GET /v1/deployments (read-back)",
                                          "observed_at": now_iso(), "health": {k: health[k] for k in ("healthy", "error_rate")}}, action_id=aid)
        if not verified:
            self.m_unverified.add(1, {"capability": act["capability"]})
        res = tool["result"]["result"]
        attempts = self.wf.execute("SELECT COUNT(*) FROM attempts WHERE action_id=?", (aid,)).fetchone()[0]
        if verified:
            reason = "rollback observed and service healthy" + (f"; {delta} rollouts observed for one action" if delta > 1 else "")
            return self.finish("MITIGATED", reason, True, attempts, delta, profile="governed")
        if res in ("COMMITTED", "REPLAYED"):
            return self.finish("EFFECT_NOT_OBSERVED", f"the deploy API reported {tool['result'].get('claimed_status') or res}; the deployment still runs {after['version']}", False, attempts, delta, profile="governed")
        return self.finish("FAILED_NO_EFFECT", f"tool call ended {res}; deployment unchanged ({after['version']}, revision {after['revision']})", False, attempts, delta, profile="governed")

    def s_complete(self, st, d) -> dict:
        return {"halt": True}


def main() -> None:
    sdir, role = Path(sys.argv[1]), sys.argv[2]
    Runtime(sdir, role).run()


if __name__ == "__main__":
    main()
