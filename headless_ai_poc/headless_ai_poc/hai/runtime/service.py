"""HeadlessRuntime: the facade every head reaches through ingress, and the durable orchestrator behind it.

It knows nothing about Slack, HTTP, Kafka or cron.  It receives an InvocationEnvelope that ingress has already
authenticated, validated and de-duplicated, establishes an execution identity, runs the incident-intelligence
workflow step by step with a checkpoint after each, pauses for approval when policy says so, and returns an
ExecutionView that any head can render.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from hai.capabilities.gateway import CallContext, CapabilityGateway
from hai.capabilities.registry import Registry
from hai.config import Clock, short_id
from hai.contracts import ApprovalDecision, Assessment, CapabilityCall, ExecutionIdentity, ExecutionView, InvocationEnvelope
from hai.control.approvals import Approvals
from hai.control.audit import AuditLog
from hai.control.identity import Directory
from hai.control.policy import PolicyEngine
from hai.control.telemetry import Telemetry
from hai.runtime.reasoner import EvidenceReasoner, Reasoner
from hai.store import connect
from hai.world import World

AGENT_FOR_INTENT = {"investigate_incident": "agent.incident-intel", "health_sweep": "agent.incident-intel", "release_check": "agent.incident-intel"}
TERMINAL = {"COMPLETED", "ESCALATED", "REJECTED", "FAILED"}
INCIDENT_CHANNEL = "#payments-incidents"


class Crash(Exception):
    """Raised by a crash point to simulate the worker dying between two steps."""


class HeadlessRuntime:
    def __init__(self, workdir: Path, world: World, clock: Clock, reasoner: Reasoner | None = None):
        workdir.mkdir(parents=True, exist_ok=True)
        self.workdir, self.world, self.clock = workdir, world, clock
        self.db = connect(workdir / "platform.db")
        self.directory = Directory(clock)
        self.registry = Registry()
        self.policy = PolicyEngine()
        self.audit = AuditLog(self.db, clock)
        self.tel = Telemetry(workdir / "traces.jsonl", clock)
        self.approvals = Approvals(self.db, self.directory, clock, self.policy.approval_ttl_s)
        self.gateway = CapabilityGateway(self.db, world, self.registry, self.policy, self.approvals, self.directory, self.audit, self.tel, clock)
        self.reasoner: Reasoner = reasoner or EvidenceReasoner()
        self.crash_after: str | None = None       # test hook: raise Crash after this step's checkpoint
        self.steps_run: list[tuple[str, str]] = []

    # ---- commands ------------------------------------------------------------------------------------------------------
    def start(self, env: InvocationEnvelope, execution_id: str) -> None:
        now = self.clock.now()
        state = {"envelope": env.model_dump(), "evidence": {}, "notes": []}
        self.db.execute("INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (execution_id, env.correlation_id, env.fingerprint, env.intent, env.channel, env.invoker, "ACCEPTED", "identity",
                         json.dumps(state), None, now, now))
        self.db.commit()

    def run(self, execution_id: str) -> ExecutionView:
        rec = self._load(execution_id)
        if rec["status"] in TERMINAL or rec["status"] == "WAITING_APPROVAL":
            return self.view(execution_id)
        steps = self._steps(rec["intent"])
        names = [n for n, _ in steps]
        i = names.index(rec["step"])
        with self.tel.span("run", rec["correlation_id"], rec["intent"], execution=execution_id, resumed_at=rec["step"]):
            self._set(execution_id, status="RUNNING")
            for name, fn in steps[i:]:
                rec = self._load(execution_id)
                if rec["status"] != "RUNNING":
                    break
                self.steps_run.append((execution_id, name))
                nxt = fn(execution_id, rec["state"])
                if nxt == "PAUSE":
                    break
                if nxt in TERMINAL:
                    self._set(execution_id, status=nxt, step=name)
                    break
                later = names[names.index(name) + 1] if names.index(name) + 1 < len(names) else None
                self._checkpoint(execution_id, later or name, "RUNNING" if later else "COMPLETED")
                if self.crash_after == name:
                    raise Crash(name)
        return self.view(execution_id)

    def decide(self, d: ApprovalDecision) -> tuple[bool, str, ExecutionView | None]:
        a = self.approvals.get(d.approval_id)
        if not a:
            return False, "no such approval request", None
        rec = self._load(a["execution_id"])
        ok, why = self.approvals.decide(d.approval_id, d.decided_by, d.approve, d.digest, rec["invoker"])
        self.audit.record("approval.decided", rec["id"], rec["correlation_id"], approval_id=d.approval_id, decided_by=d.decided_by,
                          approve=d.approve, accepted=ok, reason=why, digest=d.digest)
        with self.tel.span("approval", rec["correlation_id"], "decide", execution=rec["id"], accepted=ok, approve=d.approve):
            pass
        if not ok:
            return False, why, self.view(rec["id"])
        st = rec["state"]
        st["approval"] = {"id": d.approval_id, "status": "APPROVED" if d.approve else "REJECTED", "decided_by": d.decided_by}
        if d.approve:
            self._save(rec["id"], st, step="execute", status="RUNNING")
        else:
            st["outcome"] = "rejected by " + d.decided_by
            self._save(rec["id"], st, step="record", status="RUNNING")
        return True, why, self.run(rec["id"])

    def tick(self) -> list[ExecutionView]:
        """Housekeeping a scheduler would call: expire approvals nobody decided, and escalate their executions."""
        out = []
        for a in self.approvals.expire_due():
            rec = self._load(a["execution_id"])
            st = rec["state"]
            st["approval"] = {"id": a["id"], "status": "EXPIRED", "decided_by": None}
            st["outcome"] = "approval expired; escalated to a human, no action taken"
            self.audit.record("approval.expired", rec["id"], rec["correlation_id"], approval_id=a["id"])
            self._save(rec["id"], st, step="record", status="RUNNING")
            self.run(rec["id"])
            self._set(rec["id"], status="ESCALATED")
            out.append(self.view(rec["id"]))
        return out

    def recover(self) -> list[ExecutionView]:
        rows = self.db.execute("SELECT id FROM executions WHERE status IN ('RUNNING','ACCEPTED')").fetchall()
        return [self.run(r["id"]) for r in rows]

    # ---- the workflow --------------------------------------------------------------------------------------------------
    def _steps(self, intent: str) -> list[tuple[str, Callable[[str, dict[str, Any]], str | None]]]:
        analysis = [("identity", self._identity), ("health", self._read("getServiceHealth", "health")), ("logs", self._read("getLogs", "logs")),
                    ("traces", self._read("getTraceSummary", "traces")), ("deployments", self._read("getRecentDeployments", "deployments")),
                    ("known", self._known), ("assess", self._assess)]
        if intent == "investigate_incident":
            return analysis + [("incident", self._incident), ("recommend", self._recommend), ("approve", self._approve),
                               ("execute", self._execute), ("verify", self._verify), ("record", self._record), ("notify", self._notify)]
        if intent == "health_sweep":
            return analysis + [("notify", self._sweep_result)]
        return [("identity", self._identity), ("release_check", self._release_check)]

    def _ctx(self, xid: str, st: dict[str, Any]) -> CallContext:
        env = st["envelope"]
        return CallContext(execution_id=xid, correlation_id=env["correlation_id"], environment=env["subject"]["environment"],
                           identity=ExecutionIdentity(**st["identity"]))

    def _call(self, xid: str, st: dict[str, Any], cap: str, step: str, approval_id: str | None = None, **args: Any):
        return self.gateway.call(self._ctx(xid, st), CapabilityCall(capability=cap, arguments=args, step=step), approval_id)

    def _subject(self, st: dict[str, Any]) -> tuple[str, str]:
        s = st["envelope"]["subject"]
        return s["service"], s["environment"]

    def _identity(self, xid: str, st: dict[str, Any]) -> None:
        env = st["envelope"]
        ident = self.directory.exchange(env["invoker"], env["on_behalf_of"], AGENT_FOR_INTENT[env["intent"]], xid)
        st["identity"] = ident.model_dump()
        self._save(xid, st)
        self.db.execute("UPDATE executions SET identity=? WHERE id=?", (json.dumps(st["identity"]), xid))
        self.audit.record("execution.started", xid, env["correlation_id"], invoker=ident.invoker, on_behalf_of=ident.on_behalf_of,
                          agent=ident.agent, workload=ident.workload, scopes=ident.scopes, token_id=ident.token_id, channel=env["channel"],
                          source=env["source"], event_id=env["event_id"], causation_id=env["causation_id"], intent=env["intent"],
                          discoverable=[c["name"] for c in self.registry.discover(ident.scopes)])

    def _read(self, cap: str, key: str) -> Callable[[str, dict[str, Any]], None]:
        def step(xid: str, st: dict[str, Any]) -> None:
            svc, envn = self._subject(st)
            args = {"service": svc, "environment": envn} | ({"minutes": 30} if cap == "getLogs" else {})
            with self.tel.span("retrieval", st["envelope"]["correlation_id"], key, execution=xid):
                r = self._call(xid, st, cap, key, **args)
            st["evidence"][key] = r.output if r.status == "ok" else None
            if r.status != "ok":
                st["notes"].append(f"{cap}: {r.status} {r.error or (r.decision.rule if r.decision else '')}")
            self._save(xid, st)
        return step

    def _known(self, xid: str, st: dict[str, Any]) -> None:
        svc, _ = self._subject(st)
        logs = st["evidence"].get("logs") or []
        sig = "TokenVaultTimeout" if any("TokenVaultTimeout" in l["line"] for l in logs) else None
        r = self._call(xid, st, "getKnownIncidents", "known", service=svc, **({"signature": sig} if sig else {}))
        st["evidence"]["known"] = r.output if r.status == "ok" else []
        self._save(xid, st)

    def _assess(self, xid: str, st: dict[str, Any]) -> str | None:
        ev = st["evidence"]
        if not ev.get("health") or ev.get("logs") is None or not ev.get("deployments"):
            st["outcome"] = "not enough evidence: " + "; ".join(st["notes"])
            self._save(xid, st)
            return "FAILED"
        with self.tel.span("reasoning", st["envelope"]["correlation_id"], getattr(self.reasoner, "name", "reasoner"), execution=xid):
            a = self.reasoner.assess({**ev, "traces": ev.get("traces") or {}, "alert_at": self.world_alert()})
        st["assessment"] = a.model_dump()
        self._save(xid, st)
        return None

    @staticmethod
    def world_alert() -> float:
        from hai.world import T0
        return T0

    def _incident(self, xid: str, st: dict[str, Any]) -> None:
        svc, envn = self._subject(st)
        a = Assessment(**st["assessment"])
        r = self._call(xid, st, "createIncident", "incident", service=svc, environment=envn, severity="SEV2",
                       title=f"{svc} error rate {st['evidence']['health']['error_rate'] * 100:.0f}% ({envn})",
                       correlation_id=st["envelope"]["correlation_id"])
        if r.status == "ok":
            st["incident_id"] = r.output["incident_id"]
            self._call(xid, st, "postIncidentUpdate", "incident", incident_id=st["incident_id"], text="Assessment: " + a.summary)
        self._save(xid, st)

    def _recommend(self, xid: str, st: dict[str, Any]) -> None:
        svc, envn = self._subject(st)
        r = self._call(xid, st, "suggestRollback", "recommend", service=svc, environment=envn)
        plan = r.output if r.status == "ok" else None
        st["proposals"] = [c.model_dump() for c in self.reasoner.propose(Assessment(**st["assessment"]), plan)]
        st["assessment"]["recommendation"] = plan
        self._save(xid, st)

    def _approve(self, xid: str, st: dict[str, Any]) -> str | None:
        st["gate"] = []
        pending = None
        for p in st.get("proposals", []):
            r = self._call(xid, st, p["capability"], "approve", **p["arguments"])
            st["gate"].append({"capability": p["capability"], "arguments": p["arguments"], "status": r.status,
                               "rule": r.decision.rule if r.decision else None, "approval_id": r.approval_id})
            if r.status == "approval_required" and pending is None and p["capability"] == "rollbackDeployment":
                pending = {"approval_id": r.approval_id, "call": p}
            if r.status == "ok":
                st.setdefault("executed", []).append(p)
        if pending:
            a = self.approvals.get(pending["approval_id"])
            st["pending"] = pending | {"digest": a["digest"], "required_role": a["required_role"], "expires": a["expires"]}
            if st.get("incident_id"):
                self._call(xid, st, "postIncidentUpdate", "approve", incident_id=st["incident_id"],
                           text=f"Awaiting approval ({a['required_role']}): {pending['call']['capability']} {json.dumps(pending['call']['arguments'], sort_keys=True)}")
            self._save(xid, st, step="execute", status="WAITING_APPROVAL")
            with self.tel.span("approval", st["envelope"]["correlation_id"], "requested", execution=xid, approval=pending["approval_id"]):
                pass
            return "PAUSE"
        st["outcome"] = st.get("outcome") or "no action proposed"
        self._save(xid, st, step="record")
        return None

    def _execute(self, xid: str, st: dict[str, Any]) -> str | None:
        apr = st.get("approval") or {}
        if apr.get("status") != "APPROVED":
            return None
        ident = ExecutionIdentity(**st["identity"])
        if not self.directory.valid(ident):   # the pause outlived the short-lived token: re-exchange, never extend
            new = self.directory.refresh(ident, xid)
            st["identity"] = new.model_dump()
            self.audit.record("identity.refreshed", xid, st["envelope"]["correlation_id"], old_token=ident.token_id, new_token=new.token_id,
                              scopes=new.scopes)
        p = st["pending"]["call"]
        r = self._call(xid, st, p["capability"], "execute", approval_id=apr["id"], **p["arguments"])
        st["action"] = {"capability": p["capability"], "arguments": p["arguments"], "status": r.status, "output": r.output,
                        "authorized_by": apr["decided_by"], "approval_id": apr["id"], "error": r.error}
        st["outcome"] = f"{p['capability']} {r.status}" + (f" (approved by {apr['decided_by']})" if r.status == "ok" else f": {r.error}")
        self._save(xid, st)
        return None

    def _verify(self, xid: str, st: dict[str, Any]) -> None:
        if (st.get("action") or {}).get("status") != "ok":
            return
        svc, envn = self._subject(st)
        r = self._call(xid, st, "getServiceHealth", "verify", service=svc, environment=envn)
        st["verification"] = {"error_rate": r.output["error_rate"], "p95_ms": r.output["p95_ms"],
                              "within_slo": r.output["error_rate"] <= r.output["slo_error_rate"]} if r.status == "ok" else None
        self._save(xid, st)

    def _record(self, xid: str, st: dict[str, Any]) -> None:
        if st.get("incident_id"):
            v = st.get("verification")
            text = f"Outcome: {st.get('outcome')}" + (f"; error rate now {v['error_rate'] * 100:.1f}%" if v else "")
            self._call(xid, st, "postIncidentUpdate", "record", incident_id=st["incident_id"], text=text)

    def _notify(self, xid: str, st: dict[str, Any]) -> str | None:
        a = st.get("assessment") or {}
        text = f"[{st.get('incident_id', 'no incident')}] {a.get('summary', '')} Outcome: {st.get('outcome')}"
        self._call(xid, st, "notifyChannel", "notify", channel=INCIDENT_CHANNEL, text=text)
        return "REJECTED" if (st.get("approval") or {}).get("status") == "REJECTED" else None

    def _sweep_result(self, xid: str, st: dict[str, Any]) -> None:
        a = st["assessment"]
        h = st["evidence"]["health"]
        st["verdict"] = {"healthy": h["error_rate"] <= h["slo_error_rate"], "leading": a["leading"], "summary": a["summary"]}
        # a sweep may read everything and change nothing: prove it by trying to open an incident
        r = self._call(xid, st, "createIncident", "notify", service=a["service"], environment=a["environment"], severity="SEV3",
                       title="sweep finding", correlation_id=st["envelope"]["correlation_id"])
        st["verdict"]["write_attempt"] = {"capability": "createIncident", "status": r.status, "rule": r.decision.rule if r.decision else None}
        self._save(xid, st)

    def _release_check(self, xid: str, st: dict[str, Any]) -> None:
        """Another consumer of the same intelligence: reuse the open investigation's assessment for this service."""
        svc, envn = self._subject(st)
        row = self.db.execute("SELECT id, state FROM executions WHERE intent='investigate_incident' AND fingerprint=? ORDER BY created DESC LIMIT 1",
                              (f"degradation:{svc}:{envn}",)).fetchone()
        src = json.loads(row["state"]) if row else {}
        a = src.get("assessment")
        lead = next((h for h in a["hypotheses"] if h["id"] == a["leading"]), None) if a else None
        cand = st["envelope"]["subject"]["signal"].get("candidate")
        block = bool(lead and lead["id"] != "H0" and lead["confidence"] == "high" and not (src.get("verification") or {}).get("within_slo"))
        st["verdict"] = {"release": cand, "decision": "BLOCK" if block else "ALLOW", "based_on": row["id"] if row else None,
                         "reason": (f"open investigation {row['id']}: {lead['statement']}" if block else "no open high-confidence finding")}
        self._save(xid, st)

    # ---- persistence ---------------------------------------------------------------------------------------------------
    def _load(self, xid: str) -> dict[str, Any]:
        r = self.db.execute("SELECT * FROM executions WHERE id=?", (xid,)).fetchone()
        return dict(r) | {"state": json.loads(r["state"])}

    def _save(self, xid: str, st: dict[str, Any], step: str | None = None, status: str | None = None) -> None:
        sets, vals = ["state=?", "updated=?"], [json.dumps(st, default=str), self.clock.now()]
        if step:
            sets.append("step=?"); vals.append(step)
        if status:
            sets.append("status=?"); vals.append(status)
        self.db.execute(f"UPDATE executions SET {', '.join(sets)} WHERE id=?", (*vals, xid))
        self.db.commit()

    def _set(self, xid: str, status: str | None = None, step: str | None = None) -> None:
        self._save(xid, self._load(xid)["state"], step=step, status=status)

    def _checkpoint(self, xid: str, next_step: str, status: str) -> None:
        rec = self._load(xid)
        if rec["status"] == "WAITING_APPROVAL":
            return
        self._save(xid, rec["state"], step=next_step, status=status)
        self.db.execute("INSERT INTO checkpoints (execution_id, step, status, t) VALUES (?,?,?,?)", (xid, next_step, status, self.clock.now()))
        self.db.commit()

    # ---- queries -------------------------------------------------------------------------------------------------------
    def view(self, xid: str, joined: bool = False) -> ExecutionView:
        r = self._load(xid)
        s = r["state"]
        pend = s.get("pending")
        return ExecutionView(execution_id=xid, correlation_id=r["correlation_id"], intent=r["intent"], status=r["status"], step=r["step"],
                             invoker=r["invoker"], channel=r["channel"], assessment=Assessment(**s["assessment"]) if s.get("assessment") else None,
                             incident_id=s.get("incident_id"),
                             approval=({"approval_id": pend["approval_id"], "digest": pend["digest"], "required_role": pend["required_role"],
                                        "call": pend["call"]} | ({"status": s["approval"]["status"], "decided_by": s["approval"]["decided_by"]}
                                                                 if s.get("approval") else {"status": "PENDING"})) if pend else None,
                             action=s.get("action"), verdict=s.get("verdict"), joined=joined)

    def open_execution(self, fingerprint: str, intent: str, since: float) -> str | None:
        r = self.db.execute("SELECT id FROM executions WHERE fingerprint=? AND intent=? AND created>=? AND status NOT IN "
                            "('COMPLETED','ESCALATED','REJECTED','FAILED') ORDER BY created DESC LIMIT 1", (fingerprint, intent, since)).fetchone()
        return r["id"] if r else None

    def new_execution_id(self, env: InvocationEnvelope) -> str:
        return short_id("exe", env.source, env.event_id)
