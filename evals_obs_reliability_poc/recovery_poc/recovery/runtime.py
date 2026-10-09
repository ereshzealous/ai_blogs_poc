"""The support agent's runtime: one worker process.  Three recovery layers over the same agent.

    python -m recovery.runtime --run-dir D --scenario S09 --arm A2 --port P --worker 1 [--crash in_flight:issue_credit]
                               [--mutant X1] [--clock-offset-s 90000] [--model-change scripted-v2]

The workflow (orchestration graph, fixed):

    retrieve -> lookup -> decide (model) -> validate -> authorize -> credit -> ticket -> notify -> answer

A0 (naive)            any exception at a step: re-run the step (2 retries), then fail the run.
A1 (idempotent-retry) A0 + a stable operation id per write, sent as Idempotency-Key; the trace survives resume.
A2 (classified)       observe -> classify -> execution certainty -> recovery matrix -> act -> record, at every failure.

Exit codes: 0 finished (any terminal status), 75 fail-stop (RESUME: a fresh worker continues from the journal),
-9 when the scenario SIGKILLs the worker.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path

from . import gates
from .classify import CERTAINTY_BASIS, FailureEvent, classify_call, gate_failure
from .common import canon, det_id, hex_id, matrix, scenarios, sha256, tools, world_config, write_json
from .journal import Journal, JournalWriteError
from .policy import Decision, decide, situation
from .taxonomy import EXECUTED, LAYER, NOT_EXECUTED, UNKNOWN
from .telemetry import Tracer, redact
from .toolclient import Client

STEPS = ["retrieve", "lookup", "decide", "validate", "authorize", "credit", "ticket", "notify", "answer"]
WRITE = {"credit": "issue_credit", "ticket": "create_ticket", "notify": "send_notification"}
PRIMARY, FALLBACK = "scripted-v1", "scripted-fallback"
LIVE_PRIMARY, LIVE_FALLBACK = "qwen3:8b", "llama3.1:latest"     # the real-model end-to-end run (record-live)
FAIL_STOP = 75


class Stop(Exception):
    """End the workflow with a terminal status (ESCALATE, ABORT, or a baseline arm's FAILED)."""

    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status, self.reason = status, reason


class FailStop(Exception):
    """RESUME: this worker cannot continue safely; exit and let a fresh worker resume from the journal."""


class Runtime:
    def __init__(self, run_dir: Path, scenario: dict, arm: str, port: int, worker: int, crash: str | None = None,
                 mutant: str | None = None, clock_offset_s: int = 0, model_change: str | None = None, live: bool = False):
        self.dir, self.sc, self.arm, self.worker, self.crash, self.mutant = run_dir, scenario, arm, worker, crash, mutant
        self.clock_offset_s = clock_offset_s
        self.cfg, self.tools, self.m = world_config(), tools(), matrix()
        self.case = next(c for c in self.cfg["cases"] if c["id"] == scenario["case"])
        self.run_id = det_id("run", scenario["id"], arm, mutant or "base", model_change or "")
        self.wid = f"w{worker}"
        first = worker == 1
        jf = {f.split(":")[1] + ":" + f.split(":")[2] for f in scenario["faults"] if f.startswith("journal:")} if first else set()
        self.j = Journal(run_dir / "journal.db", jf)
        refused: dict[str, set] = {}
        if first:
            for f in scenario["faults"]:
                if f.startswith("tool:") and ":refused" in f:
                    t = f.split(":")[1]
                    refused.setdefault(f"tool:{t}", set()).add(int(f.split("@")[1]))
        self.client = Client(port, self.cfg["client_timeout_ms"], self.cfg["request_deadline_ms"], refused)
        self.policy = gates.Policy()
        self.volatile: dict = {"pid": os.getpid()}
        self.live = live
        self.primary, self.fallback = (LIVE_PRIMARY, LIVE_FALLBACK) if live else (PRIMARY, FALLBACK)
        self.model = self.primary
        self.counters: dict[str, dict] = {}
        self.repairs = 0
        self.calls: dict[str, int] = {}
        r = self.j.open_run(self.run_id, scenario["id"], arm, self.case["id"], None, self.m["version"])
        self.resumed = r["workers"] > 1
        split_trace = arm == "A0" or mutant == "X4"
        trace = hex_id(16, self.run_id, self.wid) if split_trace else (r["trace_id"] or hex_id(16, self.run_id))
        if not r["trace_id"] or split_trace:
            self.j.set_run(self.run_id, trace_id=trace)
        self.prev = (r["trace_id"], r["last_span"]) if self.resumed else None
        self.tr = Tracer(run_dir / "telemetry" / "spans.jsonl", trace, self.wid, self.volatile, redaction=True)

    # ---- small helpers ------------------------------------------------------------------------------------------------
    def ev(self, _kind: str, _step: str, **data) -> None:
        data.pop("step", None)
        data.pop("run_id", None)
        self.j.event(self.run_id, self.wid, _kind, _step, **redact(data))

    def attempt_id(self, step: str) -> str:
        n = self.calls[step] = self.calls.get(step, 0) + 1
        return det_id("att", self.run_id, step, self.wid, n)

    def maybe_crash(self, point: str, tool: str) -> None:
        if self.crash == f"{point}:{tool}":
            self.ev("crash.injected", point, tool=tool)
            os.kill(os.getpid(), signal.SIGKILL)

    def contract(self, step: str) -> dict:
        return self.tools.get(WRITE.get(step) or {"retrieve": "search_kb", "lookup": "lookup_charges"}.get(step, ""), {})

    def op_id(self, step: str) -> str:
        return det_id("op", self.run_id, step)

    def advance(self, nxt: str, ctx: dict, tool: str | None = None) -> None:
        """The step-complete checkpoint: position plus the step outputs (every arm keeps these)."""
        self.j.checkpoint(self.run_id, nxt, {"ctx": ctx}, tool=tool, kind="result" if tool and self.arm != "A2" else None)
        if self.arm != "A0":
            self.j.set_run(self.run_id, last_span=self.tr.last_span, last_worker=self.wid)

    # ---- observations (shared by every arm): each returns (output, None) or (None, FailureEvent) --------------------------
    def retrieve(self, ctx):
        with self.tr.span("retrieval search_kb", **{"gen_ai.operation.name": "retrieval", "recovery.step": "retrieve"}) as sp:
            ev = self.client.call("kb:search", "POST", "/kb/search", {"query": self.case["message"], "k": 3}, self.attempt_id("retrieve"))
            fe = self.classify("retrieve", "kb", ev, self.contract("retrieve"), sp)
            if fe:
                return None, fe
            docs = ev.body["documents"]
            sp.set(**{"recovery.retrieval.document_ids": [d["id"] for d in docs], "recovery.retrieval.scores": [d["score"] for d in docs]})
            self.ev("retrieval", "retrieve", documents=[{"id": d["id"], "version": d["version"], "score": d["score"]} for d in docs])
            return docs, None

    def lookup(self, ctx):
        with self.tr.span("execute_tool lookup_charges", **{"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "lookup_charges"}) as sp:
            ev = self.client.call("tool:lookup_charges", "GET", f"/crm/charges?customer={self.case['customer']}", None, self.attempt_id("lookup"))
            fe = self.classify("lookup", "tool", ev, self.contract("lookup"), sp)
            if fe:
                return None, fe
            self.ev("tool.read", "lookup", tool="lookup_charges", charges=len(ev.body["charges"]))
            return ev.body["charges"], None

    def decide_call(self, ctx):
        with self.tr.span(f"chat {self.model}", **{"gen_ai.operation.name": "chat", "gen_ai.request.model": self.model,
                                                     "gen_ai.prompt.template_version": "support-decide@3"}) as sp:
            body = {"model": self.model, "case_id": self.case["id"], "charges": ctx["charges"], "documents": ctx["docs"],
                    "repair_hint": ctx.get("repair_hint")}
            ev = self.client.call("model:decide", "POST", "/model/decide", body, self.attempt_id("decide"),
                                  timeout_ms=300_000 if self.live else None)
            fe = self.classify("decide", "model", ev, {"effect": "NONE", "pre_execution": [400, 422]}, sp)
            if fe:
                return None, fe
            u = ev.body.get("usage", {})
            sp.set(**{"gen_ai.response.model": ev.body.get("model"), "gen_ai.usage.input_tokens": u.get("input_tokens"),
                      "gen_ai.usage.output_tokens": u.get("output_tokens")})
            self.ev("model.call", "decide", model=self.model, usage=u)
            try:
                p = gates.parse(ev.body["content"])
            except gates.GateError as g:
                fe = gate_failure(self.run_id, "decide", "model:decide", g.cls, g.detail, generic=self.mutant == "X8")
                self.mark(sp, fe)
                return None, fe
            self.ev("model.proposal", "decide", tool=p["tool"], arguments=p["arguments"], citations=p["citations"], proposal=sha256(canon(p))[:12])
            return p, None

    def validate(self, ctx):
        with self.tr.span("gate validate", **{"recovery.step": "validate"}) as sp:
            try:
                gates.validate(ctx["proposal"], ctx["charges"])
            except gates.GateError as g:
                fe = gate_failure(self.run_id, "validate", f"proposal:{ctx['proposal']['tool']}", g.cls, g.detail,
                                  self.tools.get("issue_credit"), generic=self.mutant == "X8")
                self.mark(sp, fe)
                self.ev("gate.validate", "validate", ok=False, failure_class=fe.failure_class, detail=g.detail, proposal=sha256(canon(ctx["proposal"]))[:12])
                return None, fe
            self.ev("gate.validate", "validate", ok=True, proposal=sha256(canon(ctx["proposal"]))[:12])
            return True, None

    def authorize(self, ctx):
        p = ctx["proposal"]
        with self.tr.span("policy authorize", **{"recovery.step": "authorize"}) as sp:
            n = self.calls["authorize"] = self.calls.get("authorize", 0) + 1
            d = self.policy.authorize(self.run_id, f"{self.wid}.{n}", p["tool"], p["arguments"], self.case["customer"], ctx["charges"])
            sp.set(**{"recovery.policy.decision_id": d["decision_id"], "recovery.policy.effect": d["effect"],
                      "recovery.policy.version": d["policy_version"], "recovery.policy.rule": d["rule"]})
            self.ev("policy.decision", "authorize", **d, proposal=sha256(canon(p))[:12])
            if d["effect"] == "DENY":
                cls = "TOOL_UNAVAILABLE" if self.mutant == "X2" else "AUTHORIZATION_DENIED"
                fe = gate_failure(self.run_id, "authorize", f"tool:{p['tool']}", cls, d["reason"], self.tools.get(p["tool"]),
                                  generic=self.mutant == "X8")
                self.mark(sp, fe)
                return None, fe
            return d, None

    def write(self, step: str, ctx: dict):
        """One attempt at a write step: intent, dispatch, outcome, result.  Returns (result, None) or (None, failure)."""
        tool = WRITE[step]
        c = self.tools[tool]
        op = self.op_id(step)
        att = self.attempt_id(step)
        key = None if self.arm == "A0" else (att if self.mutant == "X7" else op)
        body, path = self.request(step, op)
        self.maybe_crash("before_dispatch", tool)
        with self.tr.span(f"execute_tool {tool}", **{"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": tool,
                                                     "recovery.operation_id": op if self.arm != "A0" else None,
                                                     "recovery.attempt_id": att, "recovery.idempotency_key": key,
                                                     "recovery.side_effect": c["effect"]}) as sp:
            try:
                if self.arm == "A2":
                    self.j.record_intent(self.run_id, step, tool, op, key, time.time() * 1000 + self.cfg["request_deadline_ms"],
                                         {"path": path, "body": redact(body)}, self.tr.trace_id)
                else:
                    self.j.checkpoint(self.run_id, step, {"in_progress": step, "operation_id": op if self.arm == "A1" else None,
                                                          "ctx": self.ctx}, tool=tool, kind="intent")
            except JournalWriteError as e:
                fe = gate_failure(self.run_id, step, f"tool:{tool}", "CHECKPOINT_WRITE_FAILED", str(e), c)
                self.mark(sp, fe)
                return None, fe
            ok = (ctx.get("allow") or {}).get("decision_id")
            self.ev("tool.dispatch", step, tool=tool, operation_id=op, attempt_id=att, idempotency_key=key, allow=ok,
                    proposal=sha256(canon(ctx["proposal"]))[:12] if step == "credit" else None)
            ev = self.client.call(f"tool:{tool}", "POST", path, body, att, op_id=op, key=key,
                                  on_sent=lambda: self.maybe_crash("in_flight", tool))
            fe = self.classify(step, "tool", ev, c, sp)
            if fe:
                return None, fe
            ext = ev.body.get("credit_id") or ev.body.get("ticket_id") or ev.body.get("message_id")
            sp.set(**{"recovery.external_id": ext, "recovery.replayed": ev.replayed})
            res = {"certainty": EXECUTED, "external_id": ext, "replayed": ev.replayed}
            if self.arm == "A2":
                try:
                    self.j.record_result(self.run_id, step, tool, op, EXECUTED, ext, ev.body, "C3")
                except JournalWriteError as e:
                    fe = gate_failure(self.run_id, step, f"tool:{tool}", "CHECKPOINT_WRITE_FAILED", str(e), c)
                    fe.execution_certainty, fe.certainty_rule, fe.certainty_basis = EXECUTED, "C3", CERTAINTY_BASIS["C3"]
                    fe.request_sent, fe.response_received = True, True
                    self.mark(sp, fe)
                    return None, fe
                self.maybe_crash("after_result", tool)
            return res, None

    def request(self, step: str, op: str) -> tuple[dict, str]:
        if step == "credit":
            a = self.ctx["proposal"]["arguments"]
            return {"charge_id": a["charge_id"], "amount": a["amount"], "reason": "duplicate_charge"}, "/credits"
        if step == "ticket":
            return {"case_id": self.case["id"], "reference": op, "summary": "duplicate charge credited"}, "/tickets"
        return {"case_id": self.case["id"], "channel": "email", "template": "credit_issued"}, "/notifications"

    # ---- classification and recording ---------------------------------------------------------------------------------
    def classify(self, step, kind, ev, contract, sp) -> FailureEvent | None:
        sp.set(**{"recovery.request_sent": ev.request_sent, "recovery.response_received": ev.response_received,
                  "recovery.transport": ev.transport, "http.response.status_code": ev.status})
        fe = classify_call(self.run_id, step, kind, ev, contract, generic=self.mutant == "X8",
                           unknown_as_failed=self.mutant == "X1", retry_terminal=self.mutant == "X2")
        if fe:
            fe.evidence.pop("deadline_ms", None)
            self.mark(sp, fe)
        else:
            sp.set(**{"recovery.execution_certainty": EXECUTED})
        return fe

    def mark(self, sp, fe: FailureEvent) -> None:
        sp.status = "ERROR"
        sp.set(**{"error.type": fe.failure_class, "recovery.failure_class": fe.failure_class, "recovery.layer": fe.layer,
                  "recovery.execution_certainty": fe.execution_certainty, "recovery.certainty_rule": fe.certainty_rule})

    def record(self, fe: FailureEvent | dict, d: Decision, sit: dict) -> None:
        f = fe.to_dict() if isinstance(fe, FailureEvent) else fe
        self.ev("failure", f["step"], **{k: v for k, v in f.items() if k != "evidence"}, evidence=f.get("evidence", {}))
        self.ev("decision", f["step"], failure_class=f["failure_class"], certainty=f["execution_certainty"], action=d.action,
                rule=d.rule, why=d.why, situation=sit, operation_id=f.get("operation_id"))
        with self.tr.span(f"recovery {d.action.lower()}", **{"recovery.failure_class": f["failure_class"],
                                                             "recovery.execution_certainty": f["execution_certainty"],
                                                             "recovery.action": d.action, "recovery.rule": d.rule,
                                                             "recovery.step": f["step"]}):
            pass

    # ---- the workflow ----------------------------------------------------------------------------------------------------
    def main(self) -> int:
        cp = self.j.last_checkpoint(self.run_id)
        self.ctx = cp.get("ctx", {}) if cp else {}
        start = cp["step"] if cp else "retrieve"     # the next step, or (A0/A1) the step that was in progress
        with self.tr.span("invoke_agent support-ops", **{"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": "support-ops",
                                                        "recovery.run_id": self.run_id, "recovery.arm": self.arm, "recovery.worker": self.wid,
                                                        "recovery.scenario": self.sc["id"], "recovery.resumed": self.resumed}) as root:
            if self.prev and self.prev[1] and self.arm != "A0" and self.mutant != "X4":
                root.link(self.prev[0], self.prev[1], "resumed after interruption")
            self.ev("worker.start", start, resumed=self.resumed, trace_id=self.tr.trace_id)
            try:
                status = self.flow(start)
            except FailStop as e:
                self.ev("worker.failstop", "-", reason=str(e))
                self.j.set_run(self.run_id, last_span=self.tr.last_span, last_worker=self.wid)
                root.set(**{"recovery.exit": "FAIL_STOP"})
                self.finish_volatile()
                return FAIL_STOP
            root.set(**{"recovery.status": status})
        self.j.set_run(self.run_id, status=status, last_span=self.tr.last_span)
        self.finish_volatile()
        return 0

    def finish_volatile(self) -> None:
        vp = self.dir / "volatile" / f"{self.wid}.json"
        write_json(vp, self.volatile)

    def flow(self, start: str) -> str:
        i = STEPS.index(start)
        status = "COMPLETED"
        resumed_here = self.resumed
        try:
            while i < len(STEPS):
                step = STEPS[i]
                if step == "answer":
                    break
                if self.arm == "A2":
                    nxt = self.a2_step(step, resumed_here)
                else:
                    nxt = self.baseline_step(step)
                resumed_here = False
                i = STEPS.index(nxt)
        except Stop as s:
            status = s.status
            self.ev("run.stop", "-", status=s.status, reason=s.reason)
        self.answer(status)
        return status

    def run_step(self, step: str):
        if step == "retrieve":
            return self.retrieve(self.ctx)
        if step == "lookup":
            return self.lookup(self.ctx)
        if step == "decide":
            return self.decide_call(self.ctx)
        if step == "validate":
            return self.validate(self.ctx)
        if step == "authorize":
            return self.authorize(self.ctx)
        return self.write(step, self.ctx)

    def store(self, step: str, out) -> None:
        key = {"retrieve": "docs", "lookup": "charges", "decide": "proposal", "authorize": "allow"}.get(step)
        if key:
            self.ctx[key] = out
        if step in WRITE:
            self.ctx.setdefault("results", {})[step] = out

    def next_of(self, step: str) -> str:
        if step == "validate" and self.mutant == "X5" and self.repairs > 0:
            return "credit"                          # X5: a repaired proposal goes straight to execution
        if step == "authorize" and self.ctx["proposal"]["tool"] != "issue_credit":
            raise Stop("REQUIRES_HUMAN", f"the model chose {self.ctx['proposal']['tool']}")
        return STEPS[STEPS.index(step) + 1]

    # ---- A0 / A1: catch -> re-run the step ------------------------------------------------------------------------------
    def baseline_step(self, step: str) -> str:
        last = None
        for attempt in range(1 + self.m["retry_budget"]):
            try:
                out, fe = self.run_step(step)
                if fe:
                    raise RuntimeError(f"{fe.operation}: {fe.http_status or fe.transport or fe.detail}")
                self.store(step, out)
                nxt = self.next_of(step)
                self.advance(nxt, self.ctx, tool=WRITE.get(step))
                if step in WRITE:
                    self.maybe_crash("after_result", WRITE[step])
                return nxt
            except Stop:
                raise
            except Exception as e:           # the naive pattern: every failure is the same failure
                last = e
                self.ev("failure", step, failed=True, error=str(e)[:160], attempt=attempt + 1)
                if step in WRITE:
                    self.ctx.setdefault("attempted", {})[step] = True
        raise Stop("FAILED", f"agent_error at {step}: {last}")

    # ---- A2: observe -> classify -> certainty -> matrix -> act ----------------------------------------------------------
    def cnt(self, step: str) -> dict:
        return self.counters.setdefault(step, {"retries": 0, "repairs": self.repairs, "reconciles": 0})

    def a2_step(self, step: str, resumed_here: bool) -> str:
        if resumed_here:
            r = self.on_resume(step)
            if r:
                return r
        while True:
            out, fe = self.run_step(step)
            if fe is None:
                self.store(step, out)
                nxt = self.next_of(step)
                self.advance(nxt, self.ctx)
                return nxt
            act = self.act(step, fe)
            if act is not None:
                return act

    def situation_for(self, step: str, cls: str, cert: str) -> dict:
        c = self.contract(step)
        fresh = False
        if step in WRITE and c.get("idempotency") == "KEY":
            it = self.j.intent(self.op_id(step))
            if it and it["deadline_ms"]:
                elapsed_ms = time.time() * 1000 - (it["deadline_ms"] - self.cfg["request_deadline_ms"]) + self.clock_offset_s * 1000
                fresh = elapsed_ms < c.get("idempotency_ttl_s", 0) * 1000
        cn = self.cnt(step)
        cn["repairs"] = self.repairs
        return situation(cls, cert, c, dict(cn), key_fresh=fresh, fallback_available=self.model != self.fallback)

    def act(self, step: str, fe: FailureEvent) -> str | None:
        """Decide and apply.  Returns the next step, or None to attempt this step again."""
        sit = self.situation_for(step, fe.failure_class, fe.execution_certainty)
        d = decide(sit, self.m)
        self.record(fe, d, sit)
        return self.apply(step, d, fe)

    def apply(self, step: str, d: Decision, fe: FailureEvent | dict | None) -> str | None:
        cn = self.cnt(step)
        if d.action == "RETRY":
            cn["retries"] += 1
            return None
        if d.action == "REPAIR":
            self.repairs += 1
            self.ctx["repair_hint"] = (fe.detail if isinstance(fe, FailureEvent) else "")[:120]
            return "decide"
        if d.action == "FALLBACK":
            self.model = self.fallback
            cn["retries"] = 0
            return "decide" if step != "decide" else None
        if d.action == "RESUME":
            raise FailStop(d.why)
        if d.action == "ESCALATE":
            self.ctx.setdefault("unknown", {})[step] = (fe.execution_certainty if isinstance(fe, FailureEvent) else fe["execution_certainty"]) == UNKNOWN
            raise Stop(d.status or "REQUIRES_HUMAN", d.why)
        if d.action == "ABORT":
            raise Stop(d.status or "FAILED", d.why)
        if d.action == "RECONCILE":
            return self.reconcile(step)
        if d.action == "CONTINUE":
            return self.adopt(step)
        raise Stop("REQUIRES_HUMAN", f"no handler for {d.action}")

    def adopt(self, step: str) -> str:
        """Continue from a confirmed result (recorded, or recovered by reconciliation) without dispatching again."""
        r = self.j.result(self.op_id(step))
        self.store(step, {"certainty": EXECUTED, "external_id": r["external_id"] if r else None, "replayed": False})
        nxt = self.next_of(step)
        self.advance(nxt, self.ctx)
        return nxt

    def on_resume(self, step: str) -> str | None:
        """A fresh worker at the interrupted step: the journal says what is known about it."""
        if step not in WRITE:
            fe = {"run_id": self.run_id, "step": step, "operation": step, "failure_class": "PROCESS_INTERRUPTED",
                  "layer": LAYER["PROCESS_INTERRUPTED"], "execution_certainty": NOT_EXECUTED, "certainty_rule": "C9",
                  "certainty_basis": CERTAINTY_BASIS["C9"], "operation_id": None}
        else:
            op = self.op_id(step)
            it, res = self.j.intent(op), self.j.result(op)
            if self.mutant == "X3":
                it = res = None                         # the step-only checkpoint: nothing about the operation survived
            cert, rule = (EXECUTED, "C8") if res else ((UNKNOWN, "C7") if it else (NOT_EXECUTED, "C9"))
            if self.mutant == "X1" and cert == UNKNOWN:
                cert = NOT_EXECUTED
            fe = {"run_id": self.run_id, "step": step, "operation": f"tool:{WRITE[step]}", "failure_class": "PROCESS_INTERRUPTED",
                  "layer": LAYER["PROCESS_INTERRUPTED"], "execution_certainty": cert, "certainty_rule": rule,
                  "certainty_basis": CERTAINTY_BASIS[rule], "operation_id": op, "side_effect": self.contract(step).get("effect"),
                  "evidence": {"intent_recorded": bool(it), "result_recorded": bool(res)}}
        sit = self.situation_for(step, "PROCESS_INTERRUPTED", fe["execution_certainty"])
        d = decide(sit, self.m)
        self.record(fe, d, sit)
        if d.action == "RESUME":
            return None                                 # run the step normally
        return self.apply(step, d, fe) or None

    def reconcile(self, step: str) -> str | None:
        """Ask the system of record about our operation, after its deadline; feed the answer back to the matrix."""
        tool = WRITE[step]
        c = self.tools[tool]
        op = self.op_id(step)
        it = self.j.intent(op)
        cn = self.cnt(step)
        cn["reconciles"] += 1
        if it and it["deadline_ms"]:
            wait = it["deadline_ms"] / 1000 - time.time()
            if wait > 0:
                time.sleep(wait + 0.05)
        path = f"/credits/by-operation/{op}" if c["status_query"] == "BY_OPERATION_ID" else f"/tickets?reference={op}"
        with self.tr.span(f"reconcile {tool}", **{"recovery.operation_id": op, "recovery.step": step, "recovery.status_query": c["status_query"]}) as sp:
            ev = self.client.call(f"status:{tool}", "GET", path, None, self.attempt_id(f"reconcile-{step}"), deadline=False)
            if not ev.response_received or ev.status != 200:
                cls, cert, found = "RECONCILE_FAILED", UNKNOWN, None
            else:
                found = ev.body.get("credits") if "credits" in ev.body else ev.body.get("tickets")
                cls, cert = ("RECONCILED", NOT_EXECUTED) if not found else (("RECONCILED", EXECUTED) if len(found) == 1 else ("DUPLICATE_EFFECT", EXECUTED))
            sp.set(**{"recovery.reconcile.result": cls, "recovery.execution_certainty": cert,
                      "recovery.reconcile.found": None if found is None else len(found)})
        self.ev("reconcile", step, operation_id=op, result=cls, certainty=cert, found=None if found is None else len(found),
                http_status=ev.status, transport=ev.transport)
        fe = {"run_id": self.run_id, "step": step, "operation": f"status:{tool}", "failure_class": cls, "layer": LAYER.get(cls, "reconciliation"),
              "execution_certainty": cert, "certainty_rule": "C10" if cls != "RECONCILE_FAILED" else "C6",
              "certainty_basis": CERTAINTY_BASIS["C10" if cls != "RECONCILE_FAILED" else "C6"], "operation_id": op,
              "side_effect": c["effect"], "evidence": {"found": None if found is None else len(found)}}
        if cls == "RECONCILED" and cert == EXECUTED:
            ext = found[0].get("credit_id") or found[0].get("ticket_id")
            self.j.record_result(self.run_id, step, tool, op, EXECUTED, ext, found[0], "C10")
        sit = self.situation_for(step, cls, cert)
        d = decide(sit, self.m)
        self.record(fe, d, sit)
        if d.action == "COMPENSATE":
            keep, extra = found[0], found[1:]
            for t in extra:
                cev = self.client.call(f"comp:{c['compensation']}", "POST", f"/tickets/{t['ticket_id']}/void", {}, self.attempt_id(f"comp-{step}"))
                self.ev("compensate", step, voided=t["ticket_id"], status=cev.status)
            self.j.record_result(self.run_id, step, tool, op, EXECUTED, keep["ticket_id"], keep, "C10")
            return self.adopt(step)
        return self.apply(step, d, fe)

    # ---- the final answer ------------------------------------------------------------------------------------------------
    def answer(self, status: str) -> None:
        claims = {}
        for step in WRITE:
            if self.arm == "A2":
                r = self.j.result(self.op_id(step))
                unknown = (self.ctx.get("unknown") or {}).get(step)
                if r and r["certainty"] == EXECUTED:
                    claims[step] = "done"
                elif unknown:
                    claims[step] = "done" if self.mutant == "X6" else "unknown"
                else:
                    claims[step] = "not_done"
            else:
                done = step in (self.ctx.get("results") or {})
                claims[step] = "done" if done else ("failed" if (self.ctx.get("attempted") or {}).get(step) else "not_done")
        confirmed = {s: bool(self.arm == "A2" and (self.j.result(self.op_id(s)) or {}).get("certainty") == EXECUTED) for s in WRITE}
        words = {"done": "done", "not_done": "not done", "failed": "failed", "unknown": "outcome unknown, a colleague will check"}
        text = (f"Status {status}. Credit: {words[claims['credit']]}. Ticket: {words[claims['ticket']]}. "
                f"Notification: {words[claims['notify']]}.")
        with self.tr.span("answer", **{"recovery.status": status, "recovery.claims": canon(claims)}):
            pass
        self.ev("answer", "answer", status=status, claims=claims, confirmed=confirmed, text=text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--worker", type=int, default=1)
    ap.add_argument("--crash")
    ap.add_argument("--mutant")
    ap.add_argument("--clock-offset-s", type=int, default=0)
    ap.add_argument("--model-change")
    ap.add_argument("--live", action="store_true")
    o = ap.parse_args()
    sc = next(s for s in scenarios() if s["id"] == o.scenario)
    rt = Runtime(Path(o.run_dir), sc, o.arm, o.port, o.worker, o.crash, o.mutant, o.clock_offset_s, o.model_change, o.live)
    code = rt.main()
    rt.j.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
